# 整体架构设计

## 1. 系统总览

系统将 SystemVerilog 设计从 filelist 解析为可查询的依赖信息，按流水线分解为 4 个流程，流程间严格串联：**后一流程的输入即前一流程的输出**。

```
① filelist 解析 ──▶ ② pyslang 解析与信息提取 ──▶ ③ sqlite 落库 ──▶ ④ API 查询
```

## 2. 流程分解

### 流程 ① filelist 解析

- **输入**：filelist 文件路径（字符串）
- **输出**：`.sv` 文件绝对路径列表
- **功能**：读取 filelist，跳过注释行与空行，相对路径基于 filelist 所在目录解析；缺失的 `.sv` 文件告警并跳过，filelist 本身缺失时报错退出
- **一级函数**：`parse_filelist(filelist_path: str) -> list[str]`

### 流程 ② pyslang 解析与信息提取

- **输入**：流程①的输出（`.sv` 文件绝对路径列表）
- **输出**：解析信息集合
  - 实例层次树：模块名、实例层次路径、端口（方向/位宽）
  - 变量信息：变量层次路径、类型、位宽、符号种类、定义位置（文件/行号）
  - 完整赋值语句块：always 块（always_comb/always_ff 等）或 assign 语句，含块类型、源文本、所在文件与起止行号
  - 依赖信息：赋值块内读写变量关系、跨模块端口连接关系
- **功能**：调用 pyslang 编译（Compilation + 语法/诊断检查），基于 elaborated AST 分析并提取上述信息
- **一级函数**：`extract_design(sv_files: list[str]) -> ParseResult`（一次编译提取四组信息，实现于 `src/extract.py`，数据模型定义于 `src/datatypes.py`）；另有分组函数 `extract_hierarchy` / `extract_signals` / `extract_blocks` / `extract_dep_edges`（各自独立编译，独立复用优先）

### 流程 ③ sqlite 落库

- **输入**：流程②的输出（解析信息集合）
- **输出**：sqlite 数据库路径（数据库文件）
- **功能**：将实例、信号、赋值语句块、依赖边一次性持久化入库（表设计定稿见 `doc/flow3_design_spec.md` §4，初稿 `doc/ref.md` §7.1），此后所有查询只读该库，无需重新解析
- **一级函数**：`build_db(parse_result: ParseResult, db_path: str) -> None`（基于 SQLAlchemy Core，表元数据定义于 `src/schema.py`；行为契约见 `doc/flow3_design_spec.md`）

### 流程 ④ API 查询

- **输入**：流程③的输出（sqlite 数据库路径）+ 变量层次路径查询参数（如 `alu_system.u_core.add_sum`）
- **输出**：四大功能结果
  | 功能 | 结果 |
  |---|---|
  | 变量信息 | 变量路径、类型、位宽、定义位置 |
  | 赋值语句块 | 该变量被完整赋值的 always 块或 assign 语句（含源文本） |
  | trace load | load 信号列表（fan-out：读取该变量的赋值块所驱动的信号） |
  | trace driver | driver 信号列表（fan-in：驱动该变量的赋值块内被读的信号） |
- **功能**：只读查询 sqlite，服务上述四大需求
- **一级函数**：变量信息查询 / 赋值块查询 / trace_load / trace_driver，均以 `db 路径 + var_path` 为输入

## 3. 数据流

```
filelist.f 路径
   │ ① parse_filelist
   ▼
.sv 文件路径列表
   │ ② pyslang 编译 + AST 分析
   ▼
解析信息集合（层次树 / 变量 / 赋值块 / 依赖）
   │ ③ build_db
   ▼
sqlite 数据库
   │ ④ 查询 API（db 路径 + 变量路径）
   ▼
变量信息 / 赋值块 / load 列表 / driver 列表
```
