# 流程④ API 查询 — Design Spec

> 定位:4 流程流水线最后一级,以流程③产出的 sqlite 库为输入,只读查询服务
> 四大功能(变量信息 / 赋值语句块 / trace load / trace driver)。
> 与 `doc/structure.md` §流程④ 对应,本规格更细,可作为重建实现的行为契约。
> 表结构与索引见 `doc/flow3_design_spec.md` §4(6 表 5 索引,定稿);表元数据
> 定义于 `src/schema.py`,本流程复用同一份 Table 对象构建查询,不手写表名/
> 列名/SQL 字符串。数据语义依赖 `doc/flow2_design_spec.md`(依赖边两通道、
> 端口连接边方向 §6.2、base↔field 合并提示 §6.4);`doc/ref.md` §7.2 为查询
> 初稿,本规格 §4/§5 为定稿语义。
> 2026-09-06 初稿:基于 flow2/flow3 定稿后的数据模型编写;定稿两个
> flow2/flow3 预留的语义决策 —— 端口连接边的查询方向映射(§5.1)与
> base↔field 层级合并规则(§5.2)。

## 1. 输入 / 输出

### 1.1 总览

```
流程③输出(sqlite 数据库路径 db_path)   +   查询参数 var_path(信号层次路径)
   │                                           如 'alu_system.u_core.add_sum'
   ▼
查询函数(§1.2) ── 只读连接 + 依 §4 SQL 查询 ──▶  四大功能结果(§1.3)
   │                                            变量信息 SignalInfo
   │                                            赋值语句块 list[BlockInfo]
   │                                            load / driver:list[str](full_path)
   ▼
(每次调用独立建引擎、查完 dispose;不写库、不重新解析 SV)
```

- **输入**:`db_path: str`(流程③输出的数据库文件路径)+ `var_path: str`
  (信号层次路径,即 `signals.full_path`,如 `alu_system.u_core.add_sum`)
- **输出**:四大功能结果(§1.3),纯数据 dataclass 或字符串列表
- 流程④**功能**:只读查询 sqlite,把同一张边表双向复用为 driver/load 两个
  方向的答案(structure.md §3),并执行两个查询语义规则(§5)

### 1.2 公开函数清单(4 个)

| 函数(签名) | 输入 | 输出 | 功能 |
|---|---|---|---|
| `get_variable_info(db_path: str, var_path: str) -> SignalInfo` | db 路径 + 信号路径 | SignalInfo(精确匹配行) | **变量信息**:路径、类型、位宽、符号种类、方向、定义位置(§4.1) |
| `get_assignment_blocks(db_path: str, var_path: str) -> list[BlockInfo]` | 同上 | 完整赋值该变量的语句块列表 | **赋值语句块**:块类型、源文本、所在文件与起止行号(§4.2) |
| `trace_load(db_path: str, var_path: str) -> list[str]` | 同上 | load 信号 full_path 列表(升序) | **trace load**(fan-out):读取该变量的赋值所驱动的信号(§4.3) |
| `trace_driver(db_path: str, var_path: str) -> list[str]` | 同上 | driver 信号 full_path 列表(升序) | **trace driver**(fan-in):驱动该变量的赋值所读的信号(§4.4) |

- 实现于 `src/query.py`,基于 SQLAlchemy Core 复用 `src/schema.py` 的 Table
  元数据(flow3 §6 约定);依赖 `sqlalchemy>=2.0`
- 结果类型复用流程②的 `SignalInfo` / `BlockInfo`(定义于 `src/datatypes.py`),
  **本流程不新增自定义类型**(types.md 同 flow3 记"未新增")
- 三个基于依赖边的查询(赋值块/load/driver)适用 §5 的两条语义规则;
  `get_variable_info` 精确匹配,不适用合并规则

### 1.3 输出类型

- `get_variable_info` → `SignalInfo`(flow2 §1.5 类型的 DB 行反序列化:
  `instance_path` 取自 instances 表 join;`is_port` 由 Integer 0/1 转 bool)
- `get_assignment_blocks` → `list[BlockInfo]`(flow2 §1.6 类型的 DB 行
  反序列化:`index = blocks.id - 1`(flow3 §4.3 显式 id 契约的逆映射),
  `instance_path` 取自 instances 表 join)
- `trace_load` / `trace_driver` → `list[str]`(结果信号 full_path,去重,
  按 full_path 升序;含条件读与端口连接边结果,§5.3)
- 信号存在但无匹配依赖边 → 空列表(合法结果);`var_path` 本身不存在于
  signals 表 → ValueError(§7),**不**静默返回空列表

### 1.4 完整示例

以 flow3 §1.4 的 mini 库(mini.sv 的 4 信号 / 2 块 / 4 边)推演
(实现后以 pytest 固化于 `tests/test_flow4.py`):

- `get_variable_info('/tmp/mini.db', 'mini.b')` →

  ```python
  SignalInfo(instance_path='mini', full_path='mini.b', name='b',
             type_name='logic[3:0]', bit_width=4, kind='variable',
             is_port=False, direction='', definition_file='/abs/path/mini.sv',
             definition_line=7)
  ```

- `get_assignment_blocks('/tmp/mini.db', 'mini.b')` →

  ```python
  [BlockInfo(instance_path='mini', index=1, block_type='always_ff',
             source_file='/abs/path/mini.sv', start_line=10, end_line=10,
             source_text='    always_ff @(posedge clk) b <= a;')]
  ```

- `trace_load('/tmp/mini.db', 'mini.a')` → `['mini.b', 'mini.y']`(边 3/1)
- `trace_driver('/tmp/mini.db', 'mini.b')` → `['mini.a', 'mini.clk']`
  (边 3/4,**含条件读 clk**,§5.3)

跨模块端口连接方向的推演见 §5.1,struct 合并推演见 §5.2。

## 2. 整体处理流程

```
(db_path, var_path)
   │
   ▼
任意查询函数:
   ├─ 校验 db_path 存在(os.path.isfile)──不存在──▶ FileNotFoundError(§7)
   ├─ _create_engine:create_engine('sqlite:///<db_path>')(每次调用独立建引擎)
   ├─ with engine.connect() as conn:(只读连接,§6 规则 2)
   │    ├─ _get_signal_row:signals 精确行查询(JOIN instances 取 instance_path)
   │    │    无行 ──▶ ValueError(f"变量不存在: {var_path}")(§7)
   │    │    有行:(get_variable_info 直接反序列化返回,到此结束)
   │    ├─ _matching_ids:构造 var_path 匹配行 id 子查询(§5.2 合并规则)
   │    └─ 依功能执行 §4 的 SQL,反序列化返回
   └─ engine.dispose()
        │
        ▼
结果(§1.3)→ 调用方
```

- 无缓存、无连接池、无事务 —— 每次调用一条连接完成查询;库只读,
  无需 PRAGMA(不写库)
- 四个函数共享 `_get_signal_row`(存在性校验 + 行反序列化)与
  `_matching_ids`(合并匹配子查询);`get_variable_info` 不构造合并子查询

## 3. 子函数规划

| 函数 | 输入 | 输出 | 功能 |
|---|---|---|---|
| `get_variable_info`(公开) | `db_path: str, var_path: str` | `SignalInfo` | 精确行查询 + 反序列化(§4.1) |
| `get_assignment_blocks`(公开) | 同上 | `list[BlockInfo]` | 赋值块查询(§4.2,合并匹配) |
| `trace_load`(公开) | 同上 | `list[str]` | load 双向查询(§4.3,合并匹配) |
| `trace_driver`(公开) | 同上 | `list[str]` | driver 双向查询(§4.4,合并匹配) |
| `_create_engine`(私有) | `db_path: str` | `sqlalchemy.Engine` | `create_engine('sqlite:///<db_path>')` |
| `_get_signal_row`(私有) | `conn, var_path: str` | `Row` | signals 精确行查询(JOIN instances 取 instance_path);无行 → ValueError |
| `_matching_ids`(私有) | `conn, var_path: str` | `Select` | 合并匹配 id 子查询(§5.2):var_path 自身 + 祖先前缀 + 转义 LIKE 后裔;三个边查询复用 |
| `_escape_like`(私有) | `text: str` | `str` | 转义 `\` `%` `_`(§5.2:信号名可含下划线) |
| `_row_to_signal`(私有) | `Row` | `SignalInfo` | 行 → SignalInfo(is_port 0/1 → bool) |
| `_rows_to_blocks`(私有) | `list[Row]` | `list[BlockInfo]` | 行 → BlockInfo(index = id - 1) |

**设计依据**:每个子函数单一职责、输入/输出类型明确;主函数只做编排
(校验 → 建引擎 → 查询 → 反序列化 → dispose)。复用 `src/schema.py` 的
Table 元数据构建查询(与流程③共享表名/列名的单一来源),SQLAlchemy Core
表达式,不手写 SQL 字符串;四个公开函数签名统一 `(db_path, var_path)`,
与 structure.md §流程④ 一致。

## 4. SQL 查询模式

> 本节 SQL 为实现语义(经 `src/schema.py` Table 元数据构建;`(:ids)` 为
> §5.2 合并匹配 id 子查询 `_matching_ids` 的引用)。示例推演以 flow3 §1.4
> 的 mini 库为准。flow3 §6 的 SQL 模式为语义初稿,本规格 §4 为定稿:
> 补端口连接边方向映射(§5.1)与合并匹配(§5.2)。

### 4.1 变量信息(get_variable_info)

```sql
SELECT s.full_path, s.name, s.type_name, s.bit_width, s.kind, s.is_port,
       s.direction, s.definition_file, s.definition_line,
       i.path AS instance_path
FROM signals s JOIN instances i ON i.id = s.instance_id
WHERE s.full_path = :var_path
```

- 无行 → ValueError(§7);恰一行(full_path 唯一,flow2 §1.5)
- 不适用 §5.2 合并规则:变量信息就是该行的全部字段

### 4.2 赋值语句块(get_assignment_blocks)

```sql
SELECT DISTINCT b.id, i.path AS instance_path, b.block_type, b.source_file,
                b.start_line, b.end_line, b.source_text
FROM dep_edges e
JOIN blocks b ON b.id = e.block_id
JOIN instances i ON i.id = b.instance_id
WHERE (e.is_port_conn = 0 AND e.driven_signal_id IN (:ids))
   OR (e.is_port_conn = 1 AND e.read_signal_id   IN (:ids))
ORDER BY b.id
```

- 语义:块内边以 driven 为"被赋值侧";端口连接边以 read 为"被驱动侧"(§5.1)
- `e.block_id` 为 NULL 的边经 JOIN 自然丢弃(无块行可查,§8)
- DISTINCT:同一块驱动该变量的多条边(多次赋值)→ 一行;同一块驱动多个
  信号(多输出 always)时仍返回整块(块是完整语句块,flow2 §1.6)

### 4.3 trace load

```sql
SELECT s.full_path
FROM dep_edges e JOIN signals s ON s.id = e.driven_signal_id
WHERE e.read_signal_id IN (:ids) AND e.is_port_conn = 0
UNION
SELECT s.full_path
FROM dep_edges e JOIN signals s ON s.id = e.read_signal_id
WHERE e.driven_signal_id IN (:ids) AND e.is_port_conn = 1
ORDER BY full_path
```

### 4.4 trace driver

```sql
SELECT s.full_path
FROM dep_edges e JOIN signals s ON s.id = e.read_signal_id
WHERE e.driven_signal_id IN (:ids) AND e.is_port_conn = 0
UNION
SELECT s.full_path
FROM dep_edges e JOIN signals s ON s.id = e.driven_signal_id
WHERE e.read_signal_id IN (:ids) AND e.is_port_conn = 1
ORDER BY full_path
```

- UNION 天然去重;跨 UNION 统一 `ORDER BY full_path`
- 条件读(is_condition=1)与端口连接边**一律包含**(§5.3),不提供过滤参数

## 5. 查询语义(核心)

> flow2/flow3 均把这两个决策留给本流程(flow3 §6:is_condition/
> is_port_conn 可按需过滤、base↔field 层级合并规则在 flow4 spec 明确;
> flow2 §6.4:base↔field 合并提示)。本节定稿。

### 5.1 端口连接边的方向映射

端口连接边按**数据流方向**存储(flow2 §6.2 定稿,测试固化):driven =
驱动端,read = 接收端 —— 与块内边(driven = LHS 被驱动侧,read = RHS
驱动源)方向**相反**:

| 边类型 | 存储方向 | 例(flow2 测试 fixture) |
|---|---|---|
| 块内边(is_port_conn=0) | driven = 被驱动信号(LHS),read = 驱动源(RHS/条件) | 边 `(mini.b, mini.a)` |
| In 端口连接边 | driven = 父模块信号,read = 子模块输入端口内部信号 | `(alu_system.opcode, alu_system.u_core.opcode)` |
| Out 端口连接边 | driven = 子模块输出端口内部信号,read = 父模块被驱动信号 | `(alu_system.u_core.result, alu_system.core_result)` |

因此两个方向的查询按边类型分别取列(§4.3/§4.4):

| 功能 | 块内边 | 端口连接边 |
|---|---|---|
| driver(X) | 取 driven=X 边的 read | 取 read=X 边的 driven |
| load(X) | 取 read=X 边的 driven | 取 driven=X 边的 read |

推演(flow2 测试 fixture alu):

- `trace_load('alu_system.opcode')` → In 边 `(alu_system.opcode,
  alu_system.u_core.opcode)` 取 read 侧 → 结果含
  `'alu_system.u_core.opcode'`(父信号穿过输入端口驱动子模块内部信号)
- `trace_driver('alu_system.u_core.opcode')` → 同边取 driven 侧 → 结果含
  `'alu_system.opcode'`(子模块输入端口内部信号的驱动者是父信号)
- `trace_load('alu_system.u_core.result')` → Out 边
  `(alu_system.u_core.result, alu_system.core_result)` 取 read 侧 → 结果含
  `'alu_system.core_result'`;`trace_driver('alu_system.core_result')` →
  结果含 `'alu_system.u_core.result'`
- 与旧参考实现 trace_var_driver 的端口穿透行为一致(ref.md §2.4)

### 5.2 base↔field 层级合并规则

flow2 只存事实边:整 struct 赋值驱动基行、字段写驱动叶子行(flow2 §6.4)。
本流程定稿:三个边查询的匹配行集 = **var_path 自身 + 祖先信号行 + 全部
后裔字段行**(整 struct 读/写与字段读/写均算作该变量的依赖):

```
匹配行集 M(var_path) = { full_path = var_path }                      -- 自身(基行或字段行)
                     ∪ { full_path = var_path 的各级 '.' 前缀 }       -- 祖先(仅信号行命中;
                     ∪ { full_path 以 var_path + '.' 为前缀 }         --  instance 路径前缀天然不命中)
                                                                      -- 后裔(全部字段行,含嵌套)
```

- 实现:`full_path IN (:var_path, :前缀1, :前缀2, ...) OR
  full_path LIKE :escaped || '.%' ESCAPE '\'`(前缀列表由 Python 按 '.'
  切分生成,`_matching_ids`)
- **LIKE 必须转义**:`\` `%` `_` 逐个前置 `\`(`_escape_like`)。信号名可含
  下划线(`clk_2`),不转义时 `_` 匹配任意单字符,会误匹配 `clkX2.field`
  之类路径
- 后裔匹配用 `var_path + '.'` 前缀而非裸前缀:不误伤兄弟信号
  (`mini.b` 不会匹配 `mini.bc`,后者不以 `mini.b.` 开头)
- 对普通信号(无字段行)合并自动退化为精确匹配;对 struct 基变量聚合全部
  字段行,对字段行聚合整 struct 赋值(祖先侧)
- 依据:flow2 §1.5 保证字段行 full_path = 基行 full_path + '.' + 字段名,
  层级关系与行一一对应

推演(合成示例,实现后以 pytest 固化):

```systemverilog
// s.sv
module s;
  typedef struct packed { logic [3:0] div; logic en; } cfg_t;
  cfg_t cfg_reg, other_cfg;
  logic en_in, y;
  assign cfg_reg = other_cfg;        // 块 0:整 struct 赋值,驱动基行
  always_comb cfg_reg.en = en_in;    // 块 1:字段写,驱动字段行
  assign y = cfg_reg.div;            // 块 2:字段读
endmodule
```

库(节选):signals 含 `s.cfg_reg`(基)/ `s.cfg_reg.div` / `s.cfg_reg.en`
(字段)等;边:`(s.cfg_reg, s.other_cfg, 块0)`、`(s.cfg_reg.en, s.en_in,
块1)`、`(s.y, s.cfg_reg.div, 块2)`。

| 查询 | 匹配行集 M | 结果 |
|---|---|---|
| `trace_driver('s.cfg_reg')` | {s.cfg_reg, s.cfg_reg.div, s.cfg_reg.en} | `['s.en_in', 's.other_cfg']` |
| `trace_driver('s.cfg_reg.div')` | {s.cfg_reg.div} ∪ 祖先{s.cfg_reg} | `['s.other_cfg']`(整 struct 赋值算字段的驱动) |
| `trace_load('s.cfg_reg')` | {s.cfg_reg, .div, .en} | `['s.y']`(字段读算基变量的 load) |
| `get_assignment_blocks('s.cfg_reg.div')` | 同 driver 匹配 | `[块0]`(整 struct 赋值完整赋值了字段) |

### 5.3 标志位处置

- `is_condition`(条件读):driver 结果**包含**(dep = RHS ∪ 条件,flow2 §6.1
  语义;mini 推演 `trace_driver('mini.b')` 含 `mini.clk`)
- `is_port_conn`:结果**包含**(跨模块依赖是事实依赖),方向按 §5.1 映射
- 结果仅返回 full_path 列表,不携带标志;需要按标志过滤的调用方可直接
  查库(schema 公开),本流程不提供过滤参数(§9)

## 6. 处理规则

1. 查询前校验 `os.path.isfile(db_path)`:不存在 → FileNotFoundError 直接
   爆出(不自动建库、不静默返回空;对齐 flow1 的显式校验风格)
2. 每次调用独立 `_create_engine` + `engine.connect()` 查询 +
   `engine.dispose()`;无连接池、无缓存、无事务(只读单查询,§2);
   不执行任何写语句,无需 PRAGMA
3. `var_path` 精确行不存在 → `ValueError(f"变量不存在: {var_path}")`
   (与 ref 参考实现一致);该检查先于合并查询,保证拼写错误立刻暴露
   而非静默返回空列表
4. 合并匹配子查询 `_matching_ids` 一次构造,三个边查询复用;LIKE 转义
   规则见 §5.2
5. load/driver 结果按 full_path 升序(UNION 后统一 ORDER BY);赋值块按
   b.id 升序;均去重 —— 同输入 → 同输出(确定性,继承 flow3 §5 规则 11)
6. 反序列化:`is_port` 0/1 → bool;`BlockInfo.index = b.id - 1`;
   `instance_path` 一律取自 instances 表 join,**不按 full_path 前缀切分**
   (信号末段本身可含 '.',如 struct 字段行,切分不可靠)
7. 查询本身不打日志;异常直接爆出(错误处理属调用方);不缓存结果、
   不保存连接
8. 所有查询基于 `src/schema.py` 的 Table 元数据构建(SQLAlchemy Core
   表达式);禁止手写 SQL 字符串 / 手写表名列名

## 7. 错误处理

| 情形 | 规格行为 |
|---|---|
| db_path 不存在 | FileNotFoundError 直接爆出(§6 规则 1) |
| db_path 是目录 / 非 sqlite 文件 | sqlalchemy/sqlite 异常直接爆出(不专门校验,禁止过度 try) |
| 库内无 signals 表(空库/错库) | sqlalchemy OperationalError 直接爆出(不专门校验) |
| var_path 不在 signals 表 | ValueError(`f"变量不存在: {var_path}"`),四个函数一致(§6 规则 3) |
| var_path 存在但无任何匹配依赖边 | 空列表(合法结果,非错误) |
| 多行同 full_path | 不可能(flow3 UNIQUE 约束;出现即程序错误,异常直接爆出) |

> 所有日志统一经 loguru 输出;sink/格式/级别配置属调用方职责,本流程不初始化。

## 8. 边界情况

- 空库(空 ParseResult 建成的 6 空表)→ 任意查询 ValueError(无信号行)
- 顶层模块信号(如 `mini.b`)→ 祖先前缀 `mini` 为实例路径、非信号行,
  自然不命中;合并退化为自身 + 后裔
- 信号名含 `_`(如 `clk_2`)→ LIKE 转义后精确匹配(§5.2)
- 自依赖边(driven == read)→ load(X)/driver(X) 均含 X 自身(事实边,
  不剔除;`b = b + 1` 的正确输出)
- 端口连接边 block 为 NULL(flow2 §5 规则 8)→ 赋值块查询 JOIN 自然丢弃
  该边;load/driver 不受影响(不查 blocks)
- 同一块多次赋值同一变量 → 赋值块查询 DISTINCT 返回一行
- var_path 为 struct 字段行 → 合并匹配含祖先(整 struct 赋值算数,§5.2)
- 变量仅被纯常量赋值(如 `cfg_reg = '0`,无读信号)→ flow2 不产边 →
  赋值块/load/driver 均空(数据模型决定,§9 已知限制)
- 单模块设计(无 is_port_conn 边)→ §4 的端口连接分支天然为空

## 9. 非目标(明确不做)

- 不做多级递归 load/driver(四大功能语义为一级,与 flow2 §10 一致;
  库 schema 公开,递归 CTE 可由调用方按 ref.md §7.2 自行构造)
- 不做按名/按位宽/按文件等通用搜索(ref.md §7.2 的示例查询不在四大功能内)
- 不提供过滤参数(排除条件读/排除端口连接边/携带标志的结果列表等;§5.3)
- 不提供 CLI 入口(仅库函数;CLI 属调用方职责)
- 不做查询缓存、连接池、并发优化
- 不修正"纯常量赋值不产边"的 flow2 数据模型(无读取信号的赋值不产依赖
  边,赋值块查询不含此类块 —— 数据模型决定,非本流程可修)
- 不校验 db 库版本 / schema 一致性(空库等异常直接爆出,§7)
