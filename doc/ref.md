# pyslang 信号 load（fan-out）追踪参考文档

> 本文档汇总"如何使用 pyslang 追踪一个信号的 load（下游扇出）"的完整技术知识：
> 现有实现原理、已知缺陷、修复设计（赋值级算法）、数据库存储设计。
> 所有 pyslang API 均已在 pyslang 11.0.0 上实测验证。

## 0. 状态总览

| 内容 | 状态 | 位置 |
|---|---|---|
| 一级 fan-out 追踪（现有实现） | ✅ 已实现 | `src/trace_var_driver.py` |
| fan-in 追踪（driver 侧） | ✅ 已实现 | `src/trace_var.py` |
| 赋值级算法修复（消除误报） | ✅ 已实现 | `src/extract.py`（两通道单遍建边，行为契约 doc/flow2_design_spec.md §6） |
| SQLite 落库（便于查询） | 📋 已设计，未实现 | 本文档 §7 |

## 1. 概念与术语

- **load（fan-out / 下游扇出）**：谁读取/消费这个信号 = 信号驱动了谁。例：`if (a) b <= c;` 中 **`b` 是 `a` 的 load**（a 在条件中被读，块输出 b）
- **driver（fan-in / 上游）**：谁赋值给这个信号，赋值的 RHS/条件读了谁。例：`b` 的赋值块读取了 `a`、`c`（**`a` 是 `b` 的赋值输入，不是 load**——方向容易混淆）

**工具映射**（注意命名误导）：

| 工具 | 方向 | 输出 |
|---|---|---|
| `trace_var.py` 的 `trace_variable()` | fan-in（谁赋值，赋值读了谁） | `{variable, assignment, related_variables}` |
| `trace_var_driver.py` 的 `trace_var_driver()` | fan-out（变量驱动了谁 = load） | `{variable, driven_variables, fan_out_count}` |

> `trace_var_driver.py` 名字带 "driver"，实际实现的是"变量作为驱动者，驱动了谁"（fan-out / load），与 `trace_var.py` 互补。

## 2. 现有实现：`trace_var_driver.py`（一级扇出）

### 2.1 调用

```bash
python src/trace_var_driver.py <filelist_path> <var_path>   # CLI
# 程序化: from trace_var_driver import trace_var_driver
```

### 2.2 数据流

```
parse_filelist(filelist)        # hierarchy.py:40  — 解析 .f 文件列表
  → extract_hierarchy(sv_files) # hierarchy.py:74  — 一次性编译全部文件，构建 InstanceSymbol 树
  → find_hierarch_var(...)      # hierarchy_var.py:63 — 定位变量（body.find + struct 字段展开）
  → _is_port(body, var_name)    # 分类：内部变量 / 输入端口 / 输出端口
  → 分发到对应追踪函数
  → _build_result(...)          # {variable, driven_variables, fan_out_count}
```

### 2.3 三类信号分发（trace_var_driver.py:96）

```python
port = body.findPort(var_name)   # 必须用 findPort()，find() 查不到端口
is_input  = port.direction == ast.ArgumentDirection.In
is_output = port.direction == ast.ArgumentDirection.Out

if is_output:
    symbols = _trace_output_port(hierarchy, inst_path, var_name)  # 情况3: 回溯父模块
else:
    symbols = _trace_in_module(body, member_path)                 # 情况1/2: 模块内追踪
```

### 2.4 模块内追踪（情况 1/2，_trace_in_module:120）

**A. 块扇出（_find_block_fanout:161）— 引用计数平衡法**：

对每个直接块（`ProceduralBlock`/`ContinuousAssign`，用 `parentScope.containingInstance is target_ci` 过滤子实例穿透）：

1. 遍历 `ExpressionKind.Assignment` 节点：`_collect_member_chain(node.left)` 收集 LHS 链符号；LHS 匹配目标时 `var_lhs_count += len(chain)`（按链长计数——struct 字段链在 visit 中产生多个节点，需同步抵消）
2. 遍历 `NamedValue`（基名匹配）+ `MemberAccess`（`_match_variable` 完整字段链匹配）累计 `var_total_count`
3. **`var_total_count > var_lhs_count` → 目标变量在 RHS/条件中被读取 → 块内全部 LHS 就是它的 load**

**B. 子模块端口扇出（_find_input_port_fanout:246）**：
遍历直接子 `InstanceSymbol.portConnections`，筛选 `direction == In`，在 `conn.expression` 中 visit 查找匹配 `NamedValue` → 命中取 **`port.internalSymbol`**（子模块内部接收信号的变量，跨模块边界的关键 API）。

**C. 输出端口回溯（_trace_output_port:310）**：
输出端口的 load 在父模块。按 `inst_path` 切出父模块 + 实例名，在父 body 中找匹配实例（`containingInstance` 过滤），输出端口连接表达式是 `ExpressionKind.Assignment`，`.left.symbol` 即父模块被驱动 wire。**只回溯一跳**（顶层输出端口 → `[]`）。

### 2.5 端口连接表达式结构（关键行为）

| 端口方向 | `conn.expression.kind` | 变量在哪 |
|---|---|---|
| `In` | `ExpressionKind.NamedValue` | `.symbol` = 父模块驱动变量 |
| `Out` | `ExpressionKind.Assignment` | `.left.symbol` = 父模块被驱动变量 |

## 3. 核心算法原理（AST 视角）

`always_ff @(posedge clk) if (a) b <= c;` 的 AST（实测 dump）：

```
ProceduralBlock
└── Timed                    StatementKind.Timed          @(posedge clk)
    ├── TimingControlKind.SignalEvent
    │   └── NamedValue(clk)
    └── Block                StatementKind.Block
        └── Conditional      StatementKind.Conditional    if
            ├── NamedValue(a)      ← 条件（读）
            └── Block
                └── ExpressionStatement
                    └── Assignment  ExpressionKind.Assignment
                        ├── .left:  NamedValue(b)   ← 写侧
                        └── .right: NamedValue(c)   ← 读侧
```

**关键**：读/写在 AST 里都是 `NamedValue` 节点、长得一样，只能靠位置（`Assignment.left` 之内 = 写侧）区分。这就是"两本账"计数的原因：

| 计数器 | 何时 +1 | 含义 |
|---|---|---|
| `var_total_count` | 任意位置出现（NamedValue 基名 / MemberAccess 链匹配） | 总出现次数 |
| `var_lhs_count` | 出现在 `Assignment.left` 链上 | 写侧次数 |

**判定**：`total > lhs` ⟺ 变量在写侧以外（RHS/条件）出现过 ⟺ 被读取 → 块内所有 LHS 是它的 load。

### 实例推演（`if (a) b <= c`，实测结果一致）

| 追踪目标 | total | lhs | 判定 | 结果 |
|---|---|---|---|---|
| `a`（条件） | 1 | 0 | 1>0 读取 | load = {b} |
| `c`（RHS） | 1 | 0 | 1>0 读取 | load = {b} |
| `b`（LHS） | 1 | 1 | 1>1 否 | load = {} |

### struct 字段链为什么要按链长计数

`cfg_reg.baud.div <= new_val;` 的 LHS 是链（3 个节点：两个 `MemberAccess` + 链底 `NamedValue`），visit 会给 total 记 3 笔，LHS 侧必须同样 `+= len(chain)=3` 才能抵消（否则 `3>1` 误判"读取了 cfg_reg"）。

## 4. 已知问题：块级粒度的误报

### 4.1 实测确认

```systemverilog
always_comb begin
    a = b;
    c = d;
end
```

```
trace_var_driver(twoout.b) → loads: [a, c]   ← c 是误报！c = d 与 b 无关
trace_var_driver(twoout.d) → loads: [c, a]   ← a 是误报！
```

### 4.2 根因

[trace_var_driver.py:235-236](src/trace_var_driver.py#L235-L236) 两步解耦：
1. 判定"块内任意位置读到 X"（块级）
2. 收集**整个块**的全部 LHS（不区分哪条语句读了 X）

任何"一个块驱动多个独立输出"的写法都会中招（如多输出 always_comb）。

## 5. 修复设计：赋值级（statement-level）算法

### 5.1 语义模型

```
dep(A) = A 的 RHS 变量 ∪ 门控 A 的所有条件变量
X 的 load = ∪ { collect_member_chain(A.left) : X ∈ dep(A) }
```

### 5.2 已验证的 pyslang API（语句节点属性）

| 语句类型 | 门控条件 | 分支/主体 |
|---|---|---|
| `StatementKind.Conditional`（if/else if） | `.conditions[i].expr` | `.ifTrue` / `.ifFalse` |
| `StatementKind.Case`（case/casez） | `.expr` + `.items[i].expressions` | `.items[i].stmt` / `.defaultCase` |
| `StatementKind.ForLoop`（for，**无** Loop 枚举） | `.stopExpr` | `.body` |
| `StatementKind.Timed`（`@(...)`） | `.timing`（事件表达式） | `.stmt` |
| `ExpressionKind.Assignment` | — | `.left`（LHS）/ `.right`（RHS） |
| `ExpressionKind.ConditionalOp` | 三元运算符，visit 会穿透到三个操作数 | — |

### 5.3 算法结构（两条通道）

**通道 1：RHS 读**——对每个 `Assignment` 节点，`_expr_reads_target(node.right, var_segments)` 命中 → LHS 链加入 loads。三元运算符（`d = a ? b : c`）嵌在 RHS 子树内，`visit()` 穿透 `ConditionalOp` 自然覆盖，**零特殊代码**。

**通道 2：门控条件读**——对每个条件节点，把条件广播到分支子树内的所有赋值：

```python
def _broadcast(stmt, conds, var_segments, loads):
    """把 conds 广播给 stmt 子树内的所有赋值：条件命中目标 → LHS 链加入 loads"""
    def hit(n):
        if n.kind == ast.ExpressionKind.Assignment:
            if any(_expr_reads_target(c, var_segments) for c in conds):
                loads.extend(_collect_member_chain(n.left))
    stmt.visit(hit)      # 分支语句也有 visit()

def _expr_reads_target(expr, var_segments):
    """NamedValue 基名匹配 / MemberAccess 完整链匹配（复用 _match_variable）"""
    found = False
    def check(node):
        nonlocal found
        if found: return
        if node.kind == ast.ExpressionKind.NamedValue:
            s = node.symbol if hasattr(node, 'symbol') else None
            if s is not None and s.name == var_segments[0]:
                found = True
        elif node.kind == ast.ExpressionKind.MemberAccess:
            if _match_variable(node, var_segments):
                found = True
    expr.visit(check)
    return found

def _find_assignment_fanout(block, var_segments):
    loads = []
    # 通道 1: RHS 读
    def on_assign(node):
        if node.kind == ast.ExpressionKind.Assignment:
            if _expr_reads_target(node.right, var_segments):
                loads.extend(_collect_member_chain(node.left))
    block.visit(on_assign)
    # 通道 2: 门控条件读
    def on_cond(node):
        if node.kind == ast.StatementKind.Conditional:
            conds = [c.expr for c in node.conditions]
            for branch in (node.ifTrue, node.ifFalse):
                if branch is not None:
                    _broadcast(branch, conds, var_segments, loads)
        elif node.kind == ast.StatementKind.Case:
            sel = [node.expr]
            for item in node.items:
                _broadcast(item.stmt, sel + list(item.expressions), var_segments, loads)
            if node.defaultCase is not None:
                _broadcast(node.defaultCase, sel, var_segments, loads)
        elif node.kind == ast.StatementKind.ForLoop:
            _broadcast(node.body, [node.stopExpr], var_segments, loads)
        elif node.kind == ast.StatementKind.Timed:
            _broadcast(node.stmt, [node.timing], var_segments, loads)
    block.visit(on_cond)
    # 去重（id(symbol)，符号身份稳定；不能按 name）
    seen, result = set(), []
    for s in loads:
        if id(s) not in seen:
            seen.add(id(s)); result.append(s)
    return result
```

### 5.4 为什么不用"遍历带条件栈"（步骤 2 的设计依据）

- `visit()` 是前序 DFS、**没有退出回调**，条件表达式深度不定（`a && b`、`f(a)`），前序流没有"条件结束/分支开始"的边界标记
- 改为**属性直取 + 子树广播**：条件节点直接暴露条件表达式（`conditions[i].expr` 等），向分支子树内所有赋值广播
- **嵌套自动累积**：外层 if 的分支子树包含内层 if 的分支 → 外层广播能命中内层分支的赋值，内层再广播一次 → 一笔赋值累计全部祖先条件（语义正确：`else if (d)` 分支的赋值同时依赖外层条件 a 和内层条件 d）
- **实现坑**：不要用 `id(赋值节点)` 做条件关联字典的键——pybind11 每次访问会新建 Python wrapper，两次遍历中同一 C++ 节点 `id()` 不同，关联会静默失败。方案：广播时直接携带目标变量做判定（上面的代码），或用 **LHS 链符号的 `id()`** 做键（Symbol 身份稳定）

### 5.5 行为对照表（修复前后）

| 场景 | 现状（块级） | 修复后（赋值级） |
|---|---|---|
| `a = b; c = d;` 中 b 的 load | `{a, c}` ✗ 误报 | `{a}` ✓ |
| `if (a) b <= c` 中 a 的 load | `{b}` ✓ | `{b}` ✓（条件进 dep） |
| `if (a) b <= c; d <= e;` 中 a 的 load | `{b, d}` ✗ 过宽 | `{b}` ✓ |
| `if (a) b <= c; else b <= d;` 中 a 的 load | `{b}` ✓ | `{b}` ✓ |
| `b = b + 1` 中 b 的 load | `{b}` ✓ | `{b}` ✓（自依赖） |
| `assign a = b;` 中 b 的 load | `{a}` ✓ | `{a}` ✓ |
| `if (a) if (b) x = y` 中 a/b 的 load | `{x}` ✓ | `{x}` ✓（嵌套广播累积） |
| `case (sel) ... endcase` 中 sel 的 load | 分支所有 LHS | 各分支 LHS ✓ |
| `for (i=0; i<n; i++) s[i] <= d` 中 n 的 load | `{s}` | `{s}` ✓（stopExpr 门控 body） |
| `@(posedge clk) b <= c` 中 clk 的 load | `{b}` ✓ | `{b}` ✓（Timed 事件作门控） |
| struct 字段赋值 `cfg_reg.baud.div <= x` 中 cfg_reg 的 load | `{}` ✓ | `{}` ✓（写字段≠读） |

### 5.6 边界情况

- 三元运算符：RHS 内（通道 1 覆盖）/ if 条件内（通道 2 覆盖）/ 嵌套三元（visit 递归穿透）——全部实测验证，零特殊代码
- `?:` 三个操作数都算读取（语义正确：`d = a ? b : c` 依赖 a、b、c）
- 数组 LHS `s[i] <= d`：本节 §5.3 代码未处理 `Select`（既有局限）；flow2_design_spec §6.3 已定稿——沿 `.value` 链剥离 Select 得基信号行、下标计入读取，实现以 flow2 为准
- 循环头 `i=0` 是普通 Assignment，通道 1 处理；`i++` 实测是 UnaryOp（Postincrement）而非 Assignment，走隐式读+写自身的自依赖规则（flow2_design_spec §6.1）；`i<n` 是 stopExpr，通道 2 广播给循环体
- 条件表达式里不会嵌 Assignment（SV 条件必须是布尔表达式），广播不会误命中
- `posedge`/`negedge` 是 `TimingControlKind` 非 NamedValue，`_expr_reads_target` 自然忽略

### 5.7 回归测试要点

- 现有 `test_trace_var_driver.py` 的端口穿透断言（`opcode`→`u_core.opcode`、`result`→`core_result`）走 `_find_input_port_fanout`/`_trace_output_port`，不受影响
- `alu_system.u_core.opcode` 的 5 个 load 需对照 `test/with_instance/alu_core.sv` 源文逐条重算
- 新增测试：`a=b; c=d` 防误报；`if(a) b<=c; d<=e` 条件精确性；else 双分支；case 多分支；struct 字段 RHS

## 6. 调试注意

- **未声明标识符会清空块内容**：编译报 `UndeclaredIdentifier` ERROR 时，错误恢复会把过程块清空，结果异常为空。排查先看 `comp.getAllDiagnostics()`（工具打印的"编译诊断: N 条警告"里注意是否有 ERROR）
- 写实验 fixture 时所有信号必须声明完整（input/output 列表里写全）

## 7. 数据库设计：SQLite 落库（便于查询）

> 动机：每次查询都要重跑 pyslang elaboration；内存 dict 不持久、不能跨进程共享（VSCode 插件/Web 工具无法读取）。

**核心洞察**：driver 和 load 是同一张边表的两面——

```
drivers(X) = SELECT read_signal WHERE driven = X     -- 谁驱动了 X
loads(X)   = SELECT driven_signal WHERE read = X     -- X 驱动了谁
```

### 7.1 表结构（5 张表）

```sql
-- ① 层次：模块实例树
CREATE TABLE instances (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,      -- 'alu_system.u_core'
    name        TEXT NOT NULL,             -- 'u_core'（实例名）
    module_name TEXT NOT NULL,             -- 'alu_core'（模块类型名）
    parent_id   INTEGER REFERENCES instances(id),
    depth       INTEGER NOT NULL,
    file        TEXT NOT NULL              -- 定义文件
);

-- ② 信号：每个变量/struct 字段一行
CREATE TABLE signals (
    id          INTEGER PRIMARY KEY,
    instance_id INTEGER NOT NULL REFERENCES instances(id),
    name        TEXT NOT NULL,             -- 最后一段
    full_path   TEXT NOT NULL UNIQUE,      -- 'csr_system.u_regfile.cfg_reg.baud.div'
    type_name   TEXT,
    bit_width   INTEGER,
    kind        TEXT,                      -- variable/net/parameter/field/port
    is_port     INTEGER NOT NULL DEFAULT 0,
    direction   TEXT                       -- input/output/inout/ref
);

-- ③ 赋值块：driver 关系的"证据"
CREATE TABLE blocks (
    id          INTEGER PRIMARY KEY,
    instance_id INTEGER NOT NULL REFERENCES instances(id),
    block_type  TEXT NOT NULL,             -- always_comb/always_ff/assign/port_connection
    source_file TEXT,
    start_line  INTEGER,
    end_line    INTEGER,
    source_text TEXT
);

-- ④ 依赖边：核心表（一个表服务两个方向）
CREATE TABLE dep_edges (
    id               INTEGER PRIMARY KEY,
    driven_signal_id INTEGER NOT NULL REFERENCES signals(id),  -- LHS
    read_signal_id   INTEGER NOT NULL REFERENCES signals(id),  -- RHS/条件/端口
    block_id         INTEGER REFERENCES blocks(id),            -- 端口连接边指向其 port_connection 块
                                                               -- (flow2_design_spec 定稿);NULL 仅为无对应块的兜底
    is_condition     INTEGER NOT NULL DEFAULT 0,  -- 1=门控条件读（通道2），0=RHS 读
    is_port_conn     INTEGER NOT NULL DEFAULT 0,  -- 1=跨模块端口穿透边
    UNIQUE (driven_signal_id, read_signal_id, block_id, is_condition, is_port_conn)
);

-- ⑤ 索引
CREATE INDEX idx_signals_name ON signals(name);
CREATE INDEX idx_signals_inst ON signals(instance_id);
CREATE INDEX idx_edges_driven ON dep_edges(driven_signal_id);
CREATE INDEX idx_edges_read   ON dep_edges(read_signal_id);
```

### 7.2 查询示例

```sql
-- 信号信息（等价 find_hierarch_var）
SELECT * FROM signals WHERE full_path = 'alu_system.u_core.opcode';

-- driver（fan-in）
SELECT s.full_path FROM dep_edges e
JOIN signals s ON s.id = e.read_signal_id
WHERE e.driven_signal_id = (SELECT id FROM signals WHERE full_path = 'alu_system.u_core.result');

-- load（fan-out）
SELECT s.full_path FROM dep_edges e
JOIN signals s ON s.id = e.driven_signal_id
WHERE e.read_signal_id = (SELECT id FROM signals WHERE full_path = 'alu_system.opcode');

-- 多级递归 fan-out（SQLite WITH RECURSIVE，≥3.8.3）
WITH RECURSIVE fanout(id) AS (
    SELECT id FROM signals WHERE full_path = 'alu_system.opcode'
    UNION ALL
    SELECT e.driven_signal_id FROM dep_edges e JOIN fanout f ON e.read_signal_id = f.id
)
SELECT DISTINCT s.full_path FROM fanout JOIN signals s ON s.id = fanout.id;

-- 按名字全局搜索 / 按位宽 / 前缀查询 / 按文件
SELECT full_path, bit_width FROM signals WHERE name = 'opcode';
SELECT full_path FROM signals WHERE bit_width = 32;
SELECT full_path FROM signals WHERE full_path LIKE 'alu_system.u_core.%';
SELECT path FROM instances WHERE file LIKE '%alu_core.sv';
```

### 7.3 填充策略

建库脚本（如 `src/build_db.py`）复用现有管线，一次遍历填三件事：

1. **instances**：`extract_hierarchy()` 的 dict（path/module/file 都有；parent_id 用 `path.rsplit('.',1)` 反查）
2. **signals**：遍历每个 instance 的 `body.syntax.members`（CST 声明遍历）+ `portList`；struct 字段按 `member_path` 展开成行
3. **dep_edges**：按 flow2_design_spec §6 单遍块遍历 + 端口连接建边（赋值级，`is_condition` / `is_port_conn` 标志落库），批量 `executemany` + 事务

### 7.4 备选方案对比

| 方案 | 优点 | 缺点 | 适用 |
|---|---|---|---|
| **SQLite（推荐）** | 标准库零依赖、持久化、索引、递归 CTE、跨进程 | 源文件改动需重建 | 中大型设计、常驻查询 |
| 纯内存 dict（现状） | 简单 | 每次重跑 pyslang、不持久 | 一次性分析 |
| networkx | 多跳遍历舒服 | 不持久、按位宽/前缀查询不顺手 | 纯图算法场景 |
| JSON 全量导出 | 可交换 | 无索引，全量加载 | 小设计/快照 |
| Postgres / Neo4j | 功能全 | 基础设施过重 | 多人团队/大规模 |

## 8. 后续工作清单

- [ ] 实现赋值级算法（§5.3），替换 `_find_block_fanout`，补回归测试（§5.7）
- [ ] `_collect_member_chain` 支持 `Select`（数组 LHS）
- [ ] 实现 `src/build_db.py`（§7.3）+ 查询 API 封装
- [ ] 落库边表使用赋值级结果（is_condition / is_port_conn 两列已为它预留）
