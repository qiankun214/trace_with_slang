# flow2_design_spec 评审意见

> 评审对象:[flow2_design_spec.md](flow2_design_spec.md)(流程② pyslang 解析与信息提取 — Design Spec)
> 评审方式:与 `doc/ref.md`、`doc/flow1_design_spec.md`、`doc/structure.md`、pyslang skill 的实测结论、
> `src/filelist.py` 现状交叉核对。

## 1. 总体评价

整体质量高,基本可以直接作为实现契约开工:

- 纯数据 `ParseResult` 隔离 pyslang 生命周期,`Compilation`/`RootSymbol`/`SourceManager` 止于流程②内部,接口干净
- 两通道赋值级算法与 `ref.md` §5 完全对齐,嵌套条件自动累积、自依赖等语义正确
- 实测坑均已落成规格:`id(表达式节点)` 不稳定、`parentScope.containingInstance` 过滤子实例穿透、
  FieldSymbol `hierarchicalPath` 指向类型定义处不可直接使用、错误恢复清空过程块
- §9 与流程③的接口契约、§4 的顺序确定性设计明确,可复现
- 错误处理表、边界情况、非目标章节完整

但有 **2 个契约矛盾需要先定稿**(直接影响流程③),若干语义缺口建议明确后再实现。

## 2. 必须修(契约矛盾)

### 2.1 `dep_edges.block_id` 的 NULL 语义与 ref.md 冲突

- flow2 §1.4 / §6.2:端口连接边引用 `port_connection` 块的全局 `index`,
  `block_id` 非 NULL,靠 `is_port_conn` 列区分
- `ref.md` §7.1:`dep_edges.block_id` 注释为 `NULL=端口连接边`
- flow2 §9 又声称表结构见 `ref.md` §7.1 —— 直接矛盾

建议:以 flow2 为准(block_id 指向 port_connection 块,is_port_conn 区分),同步修改 ref.md §7.1 的注释。

### 2.2 信号 `full_path` 重复行 vs 数据库 UNIQUE 约束

- flow2 §1.2:`input clk` 会同时产出 port 行 + 内部 variable 行(同 `full_path`),
  "去重/合并属流程③职责"
- `ref.md` §7.1:`signals.full_path` 为 `NOT NULL UNIQUE`
- flow2 §9:流程③按 `full_path` 解析信号 id

同 `full_path` 两行会让流程③建库 UNIQUE 冲突、外键解析二义。两种解法二选一:

1. flow2 直接合并 port/内部变量为一行(推荐,`kind` 中保留 port 信息)
2. 在 §9 明确流程③的合并优先级(如 variable 行优先)

## 3. 建议明确(实现前处理)

### 3.1 复合赋值/自增自减的隐式读 LHS

`a += b`、`i++` 语义上会读 LHS。通道 1 只收集 `node.right` 的读取;
§6.1 只写了"`i++` 是普通 Assignment 通道 1",未提及 `isCompound`。

需要实测确认 slang AST 的 `right` 是否已 desugar 进隐式读;若未包含,
通道 1 应补充"`isCompound` 时 LHS 也计入读取",否则自依赖边缺失。

### 3.2 信号数组(Select)写侧静默丢边

- `s[i] <= d` 的 LHS 是 `ElementSelect`,`_collect_member_chain` 收集不到
  → 数组元素写入完全不产生边,且只走 §5.9 的 debug 路径,无告警
- `a[i] = b` 中 LHS 下标 `i` 的读,通道 1 也收集不到
- 读侧 `x = mem[addr]` 经 visit 可命中 `mem`/`addr` 的 NamedValue,读侧其实可用

SV 中 mem/regfile 很常见,建议:

1. 将 Select 的 value 链解出映射到基信号行(推荐)
2. 或明确列入 §10 非目标,并把丢边行为从 debug 提升为 warning,避免静默丢数据

### 3.3 `port_connection` 块的 `instance_path` 归属

实例化语句位于父模块,但 §1.3/§6.2 未写明该块的 `instance_path` 记父实例还是子实例。
dep 边与块必须使用同一个 `(instance_path, index)` 键,否则流程③解析失败。

建议明确:记父实例路径。

### 3.4 公开 `extract_*` 重编译的成本

§3 的"独立复用重编译(简易优先)"取舍合理,但两点建议:

- 注明独立复用会重复 elaboration,避免大设计误用
- 说明 `extract_design` 内部复用的是共享编译的私有版本(子函数表未列这层,
  防止实现时在 `extract_design` 内直接调用四个公开函数而重复编译 4 次)

## 4. 文档补全

- `doc/types.md` 不存在,但 flow2 定义了 `PortInfo / InstanceInfo / SignalInfo /
  BlockInfo / DepEdge / ParseResult` 六个 dataclass,按文档体系应补 `types.md`
- 为流程④预留提示:基行/字段行分离(整 struct 赋值驱动基行、字段写驱动叶子行)
  意味着 base↔field 的 load/driver 合并需在流程④完成,SQL 侧要有字段层级合并规则,
  建议在 flow4 spec 规划时明确

## 5. 确认一致的部分

- 空列表合法、`-v/-y` 库文件输入与 flow1 spec 和 `src/filelist.py` 实现一致
- 诊断处理(ERROR 继续提取并告警)、错误恢复清空块的提醒符合 ref.md §6 实测
- 数组实例/接口实例、多顶层、struct 嵌套等边界情况和非目标清单清晰
- 顺序确定性、`index` 作为块键的设计合理,与流程③插入顺序契约闭合

## 6. 结论

可以按本 spec 开工,建议按优先级处理:

1. 定稿 §2 的两个契约矛盾(直接决定流程③表结构与解析逻辑)
2. 实现时实测确认 §3.1(isCompound)与 §3.2(Select)的行为并补进规格
3. 补 `doc/types.md` 与 §3.3 的归属说明
