---
name: trace_with_slang
description: This skill should be used when developing or refactoring the trace_with_slang project itself — the SystemVerilog trace analysis tool (pyslang parse → sqlite → API). Covers the project's architecture design (4-flow pipeline with strict input/output chaining), the four core features (variable info, assignment blocks, trace load, trace driver), doc structure, and coding conventions. Triggers on phrases like "trace_with_slang", "本项目", "本库", "架构设计", "重构", "开发本项目" or when planning work in src/.
version: 1.0.1
---

# trace_with_slang — 项目知识与架构设计

本项目用 pyslang 解析 SystemVerilog filelist，落库到 sqlite，并提供 API 访问。

> **自动更新机制**：项目架构或开发要求变化时，**必须**更新本文档对应章节，并递增 `version` 的 patch 号。

---

## 1. 项目目标（四大功能）

1. **变量信息**：给定变量路径 → 变量路径、类型、位宽、定义位置
2. **赋值语句块**：给定变量路径 → 该变量被完整赋值的语句块（完整 always 块或 assign 语句，含源文本）
3. **trace load**：给定变量路径 → load 信号 list
4. **trace driver**：给定变量路径 → driver 信号 list

## 2. 整体架构（4 流程流水线）

系统分解为 4 个流程，流程间严格串联：**流程 N 的输入 = 流程 N-1 的输出**，输入输出精确到路径层级（传路径，不传文件对象）。

```
① filelist 解析 ──▶ ② pyslang 解析与信息提取 ──▶ ③ sqlite 落库 ──▶ ④ API 查询
```

### 流程 ① filelist 解析

- **输入**：filelist 文件**路径**（字符串）
- **输出**：`.sv` 文件绝对路径列表
- **功能**：读取 filelist，跳过注释行与空行，相对路径基于 filelist 所在目录解析；缺失的 `.sv` 文件告警并跳过，filelist 本身缺失时报错退出
- **一级函数**：`parse_filelist(filelist_path: str) -> list[str]`

### 流程 ② pyslang 解析与信息提取

- **输入**：流程①的输出（`.sv` 文件绝对路径列表）
- **输出**：解析信息集合
  - 实例层次树：模块名、实例层次路径、端口（方向/位宽）
  - 变量信息：变量层次路径、类型、位宽、符号种类、定义位置（文件/行号）
  - 完整赋值语句块：always 块（always_comb/always_ff 等）或 assign 语句，含块类型、源文本、所在文件与起止行号
  - 依赖信息：块内读写变量关系、跨模块端口连接关系
- **功能**：pyslang 编译（Compilation + 语法/诊断检查），基于 elaborated AST 分析提取上述信息
- **一级函数**：`extract_hierarchy(sv_files) -> hierarchy`，以及变量信息、赋值语句块、依赖信息的提取函数

### 流程 ③ sqlite 落库

- **输入**：流程②的输出（解析信息集合）
- **输出**：sqlite 数据库**路径**（数据库文件）
- **功能**：将实例、信号、赋值语句块、依赖边一次性持久化入库（表设计详见 doc/ref.md §7），此后所有查询只读该库，无需重新解析
- **一级函数**：`build_db(解析信息, db_path) -> None`

### 流程 ④ API 查询

- **输入**：流程③的输出（sqlite 数据库路径）+ 变量层次路径查询参数（如 `alu_system.u_core.add_sum`）
- **输出**：四大功能结果（见 §1）
- **功能**：只读查询 sqlite，服务四大需求
- **一级函数**：变量信息查询 / 赋值块查询 / trace_load / trace_driver，均以 `db 路径 + var_path` 为输入

## 3. 关键语义定义

- **load（fan-out）**：读取该变量的赋值块所驱动的信号
- **driver（fan-in）**：驱动该变量的赋值块内被读的信号
- load 与 driver 是依赖关系的两面：同一组依赖边（driven/read）分别从两个方向查询，落库时一次性建立，查询时双向复用

## 4. 文档体系（doc/）

- doc/structure.md — 整体架构设计（本 skill §2 的源头；两者改动需同步）
- doc/ref.md — 技术参考：算法说明、实现流程、sqlite 表设计（§7）、已知限制（§4）与语句级修复设计（§5）
- doc/readme.md — 暴露的 API 和使用方法
- doc/types.md — 记录所有自定义类型，标注功能
- doc/flow1_design_spec.md — 流程①（filelist 解析）行为规格：输入/输出、处理流程、子函数规划、错误处理与边界情况

## 5. 开发规范（claude.md 要点）

- 禁止单个函数超过 100 行；禁止过度 try，让错误直接爆出
- 所有函数必须标注输入/输出类型，必须提供 docstring
- 有聚合在一起共同语义的变量打包成 dataclass
- 目录约定：`src/` = 目标代码目录（功能全部重构至此）；`ref/` = 参考实现，**禁止抄袭**；`test/` = SV 测试文件；`tests/` = pytest 单元测试
- python 环境使用 `.venv`
- 禁止虚构不存在的 API：有不清楚的自行探索 / 搜索 web / 询问用户
- 使用 plan 时用中文描述，并标注需要修改的内容；基于最小修改，不动无关代码

## 6. 关联 skill

- **pyslang** — pyslang 库 API 参考（CST/AST、符号遍历、类型/位宽、源码位置映射、已验证/禁止用法）
- **gen-sv-test** — 生成多级层次 SV 测试数据（theme 表、结构化测试场景 S1–S5）
