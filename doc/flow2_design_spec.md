# 流程② pyslang 解析与信息提取 — Design Spec

> 定位:4 流程流水线第 2 级,将流程①输出的 `.sv` 文件清单一次性编译并提取为
> **纯数据**解析信息集合,作为流程③(sqlite 落库)的输入。
> 与 `doc/structure.md` §流程② 对应,本规格更细,可作为重建实现的行为契约。
> 算法原理与实例推演见 `doc/ref.md` §3(读/写判定)与 §5(赋值级依赖算法),
> pyslang API 用法见 pyslang skill(pybind11 防御性访问、id(symbol) 去重等约定)。
> 日志统一经 loguru 打印(错误 `logger.error` / 告警 `logger.warning`)。
> 2026-08-23 按 doc/review.md 评审意见修订:§2.1/§2.2 契约矛盾定稿(block_id
> 指向 port_connection 块;port/内部变量同 full_path 合并为一行),
> §3.1 isCompound/自增自减、§3.2 数组 Select、§3.3 port_connection 归属、
> §3.4 共享编译私有层均已按实测落实。

## 1. 输入 / 输出

- **输入**:流程①的输出 — `.sv` 文件**绝对路径**列表 `list[str]`
  (含 `-v`/`-y` 引入的库文件;空列表是合法输入)
- **输出**:`ParseResult`(dataclass),纯数据、不含任何 pyslang AST 对象
  (`Compilation`/`Symbol`/`SourceManager` 生命周期止于流程②内部),含四组信息:
  - `instances`: 实例层次树(见 §1.1)
  - `signals`:   信号(变量/网络/参数/端口/struct 字段,见 §1.2)
  - `blocks`:    完整赋值语句块(见 §1.3)
  - `dep_edges`: 依赖边(见 §1.4)
- **一级函数**:`extract_design(sv_files: list[str]) -> ParseResult`
  (同时公开四个分组提取函数,供单独复用,见 §3)

### 1.1 InstanceInfo(实例层次树)

```python
@dataclass
class PortInfo:
    name: str                      # 端口名,如 'clk'
    direction: str                 # 'input'/'output'/'inout'/'ref'
    bit_width: int                 # port.type.bitWidth(无类型时 0)

@dataclass
class InstanceInfo:
    path: str                      # 层次路径,如 'alu_system.u_core'(顶层为模块名,其后为实例名)
    name: str                      # 实例名(顶层即模块名),如 'u_core'
    module_name: str               # 模块类型名,如 'alu_core'(inst.definition.name)
    depth: int                     # 层次深度(顶层为 1)
    file: str                      # 模块定义文件绝对路径(inst.definition.location → SourceManager)
    ports: list[PortInfo]          # 端口列表(body.portList,按声明序)
```

- 层次遍历:对 `root.topInstances` 逐个 `visit()`,收集 `SymbolKind.Instance`
  符号(DFS 前序);`inst.hierarchicalPath` 直接满足路径格式要求
- 多顶层、同名模块多处实例化 → 每处实例化一条 InstanceInfo
- 缺失子模块定义 → 符号退化为 `SymbolKind.UninstantiatedDef`,**不**产出 InstanceInfo
  (告警见 §7);`depth` 由 `hierarchicalPath` 段数计算

### 1.2 SignalInfo(信号)

```python
@dataclass
class SignalInfo:
    instance_path: str             # 所在实例层次路径
    full_path: str                 # 完整信号路径,如 'alu_system.u_core.add_sum' 或
                                   # 'csr_system.u_regfile.cfg_reg.baud.div'
    name: str                      # 末段名,如 'div'
    type_name: str                 # str(symbol.type) 或 str(field.type),无类型时 '<unknown>'
    bit_width: int                 # type.bitWidth(无则 0)
    kind: str                      # 'variable'/'net'/'parameter'/'port'/'field'/...
    is_port: bool                  # 是否端口信号(端口专属,默认为 False)
    direction: str                 # 端口方向 'input'/'output'/'inout'/'ref',非端口为空串
    definition_file: str           # 定义位置文件绝对路径(SourceManager 映射)
    definition_line: int           # 定义位置行号(1 起)
```

- 信号来源两处:
  1. 实例体成员:遍历 `body.syntax.members` 的声明类节点,对每个声明名用
     `body.find(name)` 取 AST 符号 → 类型/位宽/位置;`body.portList` 每端口一条
     (`kind='port'`,方向/`is_port` 取自 PortSymbol)
  2. struct 字段展开:变量类型 `canonicalType` 为 struct 时,对类型 scope
     `visit()` 收集 `SymbolKind.Field` 符号,每个字段一条 (`kind='field'`,
     类型/位宽取字段自身 `type`);嵌套 struct 字段递归展开
     (如 `cfg_reg.baud.div` 的三级字段)
- `full_path` 拼接规则:**`instance_path + '.' + 基名 + 各字段名`**
  (注意:FieldSymbol 的 `hierarchicalPath` 指向类型定义处
  — 如 `csr_pkg.baud` — 不可直接使用,必须拼接构造)
- 基变量与字段**都**是一条信号行(整 struct 赋值 `cfg_reg <= '0` 的
  被驱动信号就是基变量行)
- 同 `full_path` 的 port 行与 variable 行**合并为一行**(ANSI 同名端口的
  常态,端口名 = 内部变量名):`kind='port'`、`is_port=True`、`direction`
  取端口方向,`name`/`type_name`/`bit_width` 取变量符号;端口名与内部
  变量名不同(非 ANSI 端口)时 full_path 不同,如实产出两行
- **信号表按 `full_path` 唯一**:流程③直接依赖此保证(UNIQUE 约束与
  外键解析均无二义),重复 full_path 由本流程合并,不推给流程③
- 枚举默认值 (`EnumValue`)、genvar 等非信号符号不展开

### 1.3 BlockInfo(赋值语句块)

```python
@dataclass
class BlockInfo:
    instance_path: str             # 所属实例层次路径
    index: int                     # 全局块序号(全列表序 0 起,唯一,作为流程③的 block 键)
    block_type: str                # 'always_comb'/'always_ff'/'always_latch'/'always'/
                                   # 'initial'/'final'/'assign'/'port_connection'
    source_file: str               # 源文件绝对路径
    start_line: int                # 起始行号(1 起,含)
    end_line: int                  # 结束行号(1 起,含)
    source_text: str               # 该行范围的原始源文本
```

- 每实例枚举:`body.visit()` 收集 `ProceduralBlock` / `ContinuousAssign`,
  用 `parentScope.containingInstance` 过滤子实例块,只留本实例直接块
  (实测:块的 `parentScope` 是 `Scope`,`parentScope.containingInstance`
  返回 `InstanceBodySymbol`,以 `is` 比较过滤)
- `block_type`:ProceduralBlock 按 `procedureKind` 映射;ContinuousAssign → `'assign'`;
  每处模块实例化语句(`inst.syntax.parent`)产出一条 `'port_connection'` 块
  (源文本即实例化语句,供跨模块依赖边引用)
- `instance_path` 归属:普通块 = 块所在模块实例;`port_connection` 块 =
  **父实例**(实例化语句位于父模块)。dep 边的 `block_instance_path` 与
  块同键同规则(§6.2)
- 行范围与源文本:`ast_symbol.syntax.sourceRange` → SourceManager 行号;
  `ContinuousAssign.syntax` 实测为 `AssignmentExpression`,其 `sourceRange`
  已覆盖完整 `assign ...;` 语句;行号 1-indexed,截取为含首尾行的文本
- `index` 为全局稳定序号(全列表遍历序,自 0 递增),`dep_edges` 以
  `(block_instance_path, index)` 引用块,不引用流程③才分配的数据库 id;
  流程③可将 `index` 直接用作 blocks 表行 id(见 §9)

### 1.4 DepEdge(依赖边)

```python
@dataclass
class DepEdge:
    driven_signal: str             # 被驱动信号 full_path(即 LHS)
    read_signal: str               # 被读取信号 full_path(即 RHS/条件)
    block_instance_path: str       # 边所在块(或端口连接)的实例路径,与 BlockInfo.instance_path
                                   # 同规则(port_connection 边取父实例)
    block_index: int               # 所在块的全局 index(port_connection 边引用其块 index)
    is_condition: bool             # 门控条件读(通道2);RHS 读(通道1)为 False
    is_port_conn: bool             # 跨模块端口连接边;块内依赖边为 False
```

- 依赖边是 driver/load 的共同数据源(§6.4),三个来源:
  1. **块内赋值**:赋值级算法两通道(见 §6.1,`is_condition=False/True`)
  2. **输入端口连接**:父模块信号 → 子模块输入端口内部信号
     (`is_port_conn=True`,见 §6.2)
  3. **输出端口连接**:子模块输出端口内部信号 → 父模块被驱动信号
     (`is_port_conn=True`,见 §6.2)
- 边的两端引用信号 `full_path`(流程③再解析为信号 id)

## 2. 整体处理流程

```
.sv 绝对路径列表(流程①输出)
   │
   ▼
┌─ 空列表检查 ──为空──▶ 返回空 ParseResult(instances=[] 等)
│        │ 非空
│        ▼
│  _build_compilation:单次 Compilation 编译全部文件,getRoot() 触发 elaboration
│        │   (实例树在 elaboration 后已完整构建)
│        ▼
│  _report_diagnostics:统计诊断并打印(§5),存在 ERROR 时告警提示提取可能不完整
│        │   (在 getRoot() 之后收集,覆盖语法+语义阶段诊断)
│        │
│        ├─▶ extract_hierarchy    ──▶ list[InstanceInfo]
│        │
│        ├─▶ extract_signals      ──▶ list[SignalInfo]  (含 struct 字段展开)
│        │
│        ├─▶ extract_blocks       ──▶ list[BlockInfo]   (含 port_connection 块)
│        │
│        └─▶ extract_dep_edges    ──▶ list[DepEdge]     (赋值级 + 端口连接)
│                    │
│                    ▼
│  组装 ParseResult(instances / signals / blocks / dep_edges)
└────────┼─────────────────────
         ▼
流程③(build_db)的输入
```

顺序要求:层次/信号/块先行(依赖边需要 `(instance_path, index)` 块键与
信号 full_path 映射);`extract_design` 内部调用**共享编译的私有实现**
`_extract_*_impl`(§3),只编译一次;公开 `extract_*` 各自独立编译,
见 §3 设计依据。

## 3. 子函数规划

| 函数 | 输入 | 输出 | 功能 |
|---|---|---|---|
| `extract_design`(一级,公开) | `sv_files: list[str]` | `ParseResult` | 总流程编排(§2);空列表 → 空结果 |
| `extract_hierarchy`(公开) | `sv_files: list[str]` | `list[InstanceInfo]` | 编译 + visit 收集实例树,组装 InstanceInfo |
| `extract_signals`(公开) | `sv_files: list[str]` | `list[SignalInfo]` | 成员声明 + 端口 + struct 字段展开 |
| `extract_blocks`(公开) | `sv_files: list[str]` | `list[BlockInfo]` | 直接过程块/连续赋值 + 实例化语句 |
| `extract_dep_edges`(公开) | `sv_files: list[str]` | `list[DepEdge]` | 赋值级依赖 + 端口连接依赖 |
| `_extract_hierarchy_impl`(私有) | `root, sm` | `list[InstanceInfo]` | 层次提取实现(共享编译,公开版内部调用) |
| `_extract_signals_impl`(私有) | `root, sm` | `list[SignalInfo]` | 信号提取实现(共享编译) |
| `_extract_blocks_impl`(私有) | `root, sm` | `list[BlockInfo]` | 块提取实现(共享编译) |
| `_extract_dep_edges_impl`(私有) | `root, sm, blocks, signals` | `list[DepEdge]` | 依赖提取实现(共享编译,依赖块键与信号表) |
| `_build_compilation`(私有) | `sv_files: list[str]` | `(Compilation, RootSymbol, SourceManager)` | 单次编译全部文件并 elaborate |
| `_report_diagnostics`(私有) | `Compilation` | `None` | 统计 ERROR/WARNING 计数并 log |
| `_collect_instances`(私有) | `RootSymbol` | `list[InstanceSymbol]` | visit 收集 InstanceSymbol(DFS 前序) |
| `_extract_ports`(私有) | `InstanceBodySymbol` | `list[PortInfo]` | portList → PortInfo(direction 枚举映射) |
| `_source_of`(私有) | `ast_symbol, SourceManager` | `(file, start, end, text)` | syntax.sourceRange → 行范围 + 源文本 |
| `_collect_direct_blocks`(私有) | `InstanceBodySymbol` | `list[tuple[Symbol, str]]` | 本实例直接块(containingInstance 过滤) |
| `_classify_block`(私有) | `Symbol` | `str` | procedureKind / ContinuousAssign → block_type |
| `_enum_struct_fields`(私有) | `Type` | `list[FieldSymbol]` | canonicalType.visit 收集 Field 符号 |
| `_signal_full_path`(私有) | `instance_path, segments` | `str` | 拼接实例路径 + 基名 + 字段名 |
| `_collect_member_chain`(私有) | `Expression` | `list[Symbol]` | LHS 链符号收集(NamedValue / MemberAccess) |
| `_reads_signal`(私有) | `Expression, segments` | `bool` | RHS/条件是否读取目标(基名匹配/全链匹配) |
| `_broadcast_conditions`(私有) | `stmt, conditions, ...` | `None` | 条件向分支子树内全部赋值广播(§6.1) |
| `_build_block_edges`(私有) | `Symbol(块), ...` | `list[DepEdge]` | 单块内两通道赋值级依赖提取 |
| `_build_port_conn_edges`(私有) | `InstanceSymbol, ...` | `list[DepEdge]` | 端口连接跨模块边(In/Out,§6.2) |
| `_dedup_edges`(私有) | `list[DepEdge]` | `list[DepEdge]` | 按 (driven, read, 块键, flags) 元组去重 |

**设计依据**:公开 extract_* 独立调用时各自编译一次(独立复用优先,代价是
重复 elaboration,大设计勿误用);`extract_design` 只编译一次,内部依次调用
`_extract_*_impl` 私有实现(`extract_design` **不得**调用公开 extract_*,
否则重复编译 4 次)。单一职责、输入/输出类型明确;主函数只做编排。

## 4. 数据模型(ParseResult)

```python
@dataclass
class ParseResult:
    instances: list[InstanceInfo]  # 实例层次树
    signals:   list[SignalInfo]    # 全部信号行(含 struct 字段展开)
    blocks:    list[BlockInfo]     # 赋值语句块(含 port_connection)
    dep_edges: list[DepEdge]       # 依赖边
```

- 四组信息都按**确定顺序**产出:instances 按 DFS 前序;signals 按实例序 →
  成员声明序 → struct 字段序;blocks 按实例序 → 遍历序 → port_connection
  **列最后**;dep_edges 按块序,端口连接边最后(保证结果可复现)
- 流程③以此四列表为输入建库(表设计 doc/ref.md §7.1):
  `instances` 表 ← `ParseResult.instances`(parent_id 由流程③按 path 前缀推导);
  `signals` 表 ← `ParseResult.signals`(instance_id 按 instance_path 解析);
  `blocks` 表 ← `ParseResult.blocks`(instance_id 按 instance_path 解析,
  id 与 index 对应);`dep_edges` 表 ← `ParseResult.dep_edges`
  (信号 id 按 full_path 解析,block_id 按 `(instance_path, index)` 解析)

## 5. 处理规则

1. 空 `sv_files` → 返回空 `ParseResult`(四列表均为 `[]`),不报错
2. 编译:单个 `ast.Compilation()` 加入全部文件(必一次性编译,否则缺失定义的
   子模块退化为 UninstantiatedDef),`getRoot()` 触发 elaboration
3. 诊断:`comp.getAllDiagnostics()` 统计 ERROR/WARNING 条数,`logger.error` /
   `logger.warning` 输出计数汇总;单条诊断按 DEBUG 级别输出;
   **存在 ERROR 时** `logger.warning` 提醒"错误恢复可能清空过程块,
   提取结果可能不完整"(doc/ref.md §6 实测现象),继续提取
4. 层次:对每个 `root.topInstances` 执行 `visit()`,只收 `SymbolKind.Instance`
   (DFS 前序);`path = inst.hierarchicalPath`;`module_name = inst.definition.name`;
   `depth` = 路径段数;`file` 取 `inst.definition.location`(定义位置,
   非 `inst.location` 实例化位置)经 `SourceManager.getFullPath` 得绝对路径
5. 信号:声明遍历用 CST(`body.syntax.members`),符号解析用 AST(`body.find` /
   `body.portList`);端口的 `direction` 按 ArgumentDirection 枚举映射为
   'input'/'output'/'inout'/'ref';`bit_width` 一律取 `type.bitWidth`
   属性(无 `getBitstreamWidth()` 之类方法);`definition_file/line` 取
   符号 `location` 经 SourceManager 映射(字段行例外,见规则 6);
   同 `full_path` 的 port 行与 variable 行合并为一行(规则见 §1.2),
   信号表按 `full_path` 唯一
6. struct 字段展开:`canonicalType`(带 `isStruct` 判定)经 `visit()` 收集
   `SymbolKind.Field` 直接字段;字段类型本身为 struct 时递归展开
   (嵌套 struct,如 csr_pkg 的 `csr_cfg_t.baud.div`);字段行
   `definition_file/line` 继承基变量定义位置(字段符号的 location 指向
   类型定义处,不作信号定义位置)
7. 块:每实例 `body.visit()` 收集直接块,过滤条件
   `parentScope.containingInstance is 本实例 body`(visit 会穿透子实例,
   必须过滤);`index` 为全列表递增序号;源文本行范围见 §1.3
8. `port_connection` 块:按父实例枚举(遍历父实例的直接子 `InstanceSymbol`
   时产出,归属父实例,§1.3),行范围取 `inst.syntax.parent.sourceRange`
   (`inst.syntax.parent` 可能为 None — 如无源语法的实例,跳过);
   块排在所属(父)实例块列表末尾,index 连续
9. 依赖边按 §6 规则提取;`dep_edges` 两端必须引用已产出的信号 `full_path`
   (信号不在信号表中的边丢弃并 `logger.debug` 记录);LHS 无法解析为
   信号行(§6.3 全部规则不命中)时不产 driven 边,同样 `logger.debug` 记录
10. 确定性:所有遍历按 pyslang 自然顺序;边按 (driven_signal, read_signal,
    block_instance_path, block_index, is_condition, is_port_conn) 元组去重

## 6. 依赖提取(核心)

> 详见 doc/ref.md §5(两通道算法、条件广播、行为对照表)。
> 关键决策:**按赋值级(语句级)提取依赖,不复用旧块级计数法**
> (块级会把同块内无关语句的输出误报为 load,见 ref.md §4 实测)。
> `is_condition` 列专为两通道区分预留。

### 6.1 块内赋值依赖(两通道)

块 = `ProceduralBlock` 或 `ContinuousAssign`,`visit()` 可同时遍历语句节点
与表达式节点。**实现策略**:每个块只遍历一次,一次建出块内全部边
(复杂度 O(块内节点数),**禁止**对每个信号逐一遍历整个设计)。读取信号经
§6.3 的匹配/拼接规则解析为 full_path;解析失败(无信号行)的边丢弃。

- **通道 1(RHS 读 + 隐式读)**:对块内每个 `ExpressionKind.Assignment` 节点,
  收集读取信号:`node.right` 全子树 + LHS 的 `ElementSelect` 下标表达式
  (`visit()` 中出现的 `NamedValue` 与 `MemberAccess` 链,含三元运算符
  `a ? b : c` 的三个操作数——visit 自然穿透),为每个读取信号产生一条边:
  `driven = node.left 解析为 full_path`(LHS 规则见 §6.3),
  `read = 读取信号 full_path`,`is_condition=False`。
  - **复合赋值**(`isCompound=True`,如 `a += b`):实测 AST 不 desugar,
    `node.right` 只含显式 RHS——**额外**把 LHS 基变量链计入读取
    (隐式读自身,产生自依赖边 `a → a`)
  - **自增/自减**(`i++`/`++i`/`i--`/`--i`):实测是 `UnaryOp`
    (Preincrement/Postincrement/Predecrement/Postdecrement),
    **不是 Assignment**——单独规则:操作数计入隐式读并作为 driven,
    产生自依赖边(driven=read=操作数信号,`is_condition=False`)
- **通道 2(门控条件读)**:对块内每个条件类语句节点,把条件表达式广播给
  分支子树内**全部**赋值:
  - `StatementKind.Conditional`:`cond = [c.expr for c in node.conditions]`,
    分支 `node.ifTrue` / `node.ifFalse`
  - `StatementKind.Case`:`cond = [node.expr] + item.expressions`(分支
    `item.stmt`)、`cond = [node.expr]`(分支 `node.defaultCase`)
  - `StatementKind.ForLoop`:`cond = [node.stopExpr]`,分支 `node.body`
  - `StatementKind.Timed`:`cond = [node.timing]`,分支 `node.stmt`
  - 广播实现:对分支语句 `visit()`,每遇 `Assignment`,收集其条件表达式中
    读取的全部信号,对 (条件读取信号 × LHS 信号) 逐一产生边
    (`driven = LHS 链 full_path`,`is_condition=True`)。
  - **嵌套条件自动累积**:外层 if 的分支子树包含内层 if,外层广播命中内层
    分支的赋值,内层再广播一次 → 一笔赋值对每个命中条件各产生一条边
    (语义正确,ref.md §5.4)
- 实现坑:条件关联**不得**以 `id(表达式节点)` 做键(pybind11 每次访问新建
  wrapper,id 不稳定);Symbol 的 `id()` 在单次 elaboration 内稳定,可用于
  符号级去重(见 pyslang skill「已验证的编码最佳实践」)
- 连续赋值(`ContinuousAssign`)只走通道 1(无语句条件),行为同过程块;
  循环头 `i=0` 是普通 Assignment(通道 1),`i<n` 是 stopExpr(通道 2),
  `i++` 走 UnaryOp 自依赖规则(见上)

### 6.2 跨模块端口连接依赖

对每个实例的 `portConnections`(方向结构差异见 pyslang skill §3.9.1.1):

| 端口方向 | `conn.expression` 结构 | 边方向 | 驱动端 | 读取端 |
|---|---|---|---|---|
| `In`(输入) | `NamedValue` | 父 → 子 | `expr.symbol.hierarchicalPath`(父信号) | `conn.port.internalSymbol.hierarchicalPath`(子模块内接收信号的变量) |
| `Out`(输出) | `Assignment` | 子 → 父 | `conn.port.internalSymbol.hierarchicalPath`(子模块内驱动输出的变量) | `expr.left.symbol.hierarchicalPath`(父模块被驱动变量) |
| `InOut`/`Ref` | 不在本次范围 | — | — | 告警跳过(见 §7) |

- 每条连接一条边,`is_port_conn=True`,`is_condition=False`,
  `(block_instance_path, block_index)` 指向该实例化语句的 `port_connection` 块
- 归属:`port_connection` 块的 `instance_path` 与边的 `block_instance_path`
  均记**父实例**路径(实例化语句位于父模块);子/父两侧信号 full_path
  各自按所属实例解析(§1.3)
- 连接表达式为 `NamedValue` 时取 `expr.symbol`(其 `hierarchicalPath` 实测为
  父实例内完整路径,可直接用);连接表达式为 `MemberAccess`(struct 端口字段)
  时按 §6.3 的 full_path 拼接规则解析
- `internalSymbol.hierarchicalPath` 实测为实例内完整路径(如
  `csr_system.u_regfile.baud_cfg_o`),直接可用
- 顶层模块端口无 portConnections → 无端口连接边(天然为空)
- 连接表达式为空(`EmptyArgument`)或符号缺失 → 跳过该连接并 `logger.debug`

### 6.3 读取匹配规则

- 目标信号以**实例内段路径**表示:基名 `['cfg_reg']` 或含字段
  `['cfg_reg', 'baud', 'div']`
- `NamedValue` 节点:其 `symbol.name` == 段[0] → 匹配
- `MemberAccess` 链:自顶向下收集成员名 + 链底基名,与目标段**完整相等** → 匹配;
  目标只有基名(整 struct 追踪)时,链首匹配基名即命中
- 命中后 `read_signal` = `instance_path + '.' + '.'.join(段)`(即 §1.2 的
  full_path 拼接规则)
- LHS 解析(`_collect_member_chain` 收集链后取驱动行):`NamedValue` LHS →
  驱动基变量行(整 struct 赋值 `cfg_reg <= '0` 即此情形,不扩展到字段,
  字段级关系属流程④职责);`MemberAccess` LHS → 驱动**完整链末端**字段行
  (如 `cfg_reg.baud.div <= x` 只驱动 `...cfg_reg.baud.div` 行,
  不驱动链上中间字段)
- LHS 为 `ElementSelect`(数组元素写,如 `s[i] <= d`):沿 `.value` 链剥离
  Select 得到基表达式,再按上述 NamedValue/MemberAccess 规则取驱动行
  (数组元素不单独成行,driven = 数组基信号行);LHS 的 `.selector` 下标
  表达式计入通道 1 读取(下标是读);混合链(`cfg_reg.baud.div[i] <= x`)
  剥 Select 后按 MemberAccess 链规则继续解析
- 读侧 `x = mem[addr]`:`visit()` 自然穿透 `ElementSelect` 命中
  `mem`/`addr` 的 NamedValue,无需特殊代码

### 6.4 语义

- driver(fan-in,X 的驱动者)= 以 X 为 driven 的边上的 read 集合
- load(fan-out,X 驱动了谁)= 以 X 为 read 的边上的 driven 集合
- 同一张边表两个方向查询,流程③落库一次、流程④双向复用
  (与 doc/structure.md §3 一致)
- 自依赖允许(`b = b + 1`:driven 与 read 同信号)
- **base↔field 合并提示(为流程④预留)**:整 struct 赋值驱动基行、字段写
  驱动叶子行,本流程只存事实边;流程④的 driver/load 查询需在 SQL 侧制定
  base↔field 层级合并规则(规划 flow4 spec 时明确)

## 7. 错误处理

| 情形 | 规格行为 |
|---|---|
| `sv_files` 为空列表 | 返回空 ParseResult,不报错 |
| 单个文件不可读 / 不存在 | 抛 IOError 直接爆出(流程①已过滤,此处出现即程序错误;禁止过度 try) |
| 编译存在 WARNING 诊断 | `logger.warning` 输出计数汇总,继续提取 |
| 编译存在 ERROR 诊断 | `logger.error` 输出计数汇总 + `logger.warning` 提醒提取可能不完整,继续提取 |
| 子模块定义缺失(UninstantiatedDef) | `logger.warning` 告警,该符号不进实例树,继续 |
| 端口连接表达式结构不识别 | `logger.warning`,跳过该连接,继续 |
| 依赖边引用的信号不在信号表中 | `logger.debug` 记录并丢弃该边(不告警,正常情形如迭代变量) |

> 所有日志统一经 loguru 输出;sink/格式/级别配置属调用方职责,本流程不初始化。

## 8. 边界情况

- 空文件列表 / 列表内文件均无模块定义 → 空 ParseResult(四列表 `[]`)
- 同一模块多处实例化 → 每处一条 InstanceInfo、一套 SignalInfo
  (full_path 前缀不同)
- 多顶层模块 → 每个顶层一棵子树,均收进 `instances`
- 仅含 package 的文件(如 csr_pkg.sv)→ 不产实例/信号/块,但其 struct 类型
  被实例化模块引用时正常展开字段
- struct 嵌套任意深度 → 字段递归展开为一行一字段
- 整 struct 赋值 / 整 struct 读 → 以基变量行参与依赖(字段级关系属流程④)
- 顶层模块端口(无 portConnections)→ 无端口连接边
- 循环头 `i=0`(普通赋值)、`i++`(UnaryOp 自依赖)、`i<n`(stopExpr)
  → 按 §6.1 各规则处理
- 数组实例 / 接口实例 / generate 生成的实例 → 均可收进实例树;其依赖提取
  规则未专门覆盖(见 §10 非目标)

## 9. 与流程③的接口契约

- 输出为纯数据 `ParseResult`:不含 pyslang 对象,流程③无需 import pyslang
- 四列表的确定顺序即流程③建库的插入顺序(§4);`blocks.index` 对应
  blocks 表的行 id(流程③保证 index 即自增 id,或自行维护映射)
- 依赖边引用信号 `full_path` 与块 `(instance_path, index)`,流程③据此解析
  外键,解析失败即告警;端口连接边同样引用 `port_connection` 块的
  `block_id`(非 NULL,`is_port_conn` 列区分边类型),ref.md §7.1 注释已按
  此同步
- 流程③表结构见 doc/ref.md §7.1(dep_edges 的 `is_condition` /
  `is_port_conn` 列由本流程的 `DepEdge` 标志填充)

## 10. 非目标(明确不做)

- 不做 sqlite 落库(流程③职责);不做查询 API(流程④职责)
- 不实现多级递归 fan-out/fan-in(由流程④以 SQL 递归完成)
- 不展开宏 / `include` / 不处理预处理器指令
- 不专门支持接口(modport/clocking block 语义)、数组实例元素的信号级追踪
- 不提取过程块内局部变量(仅模块级成员声明)
- 不做类型参数特化的符号级分析(elaboration 已展开部分,超出部分不承诺)
