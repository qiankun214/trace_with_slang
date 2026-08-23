---
name: pyslang
description: This skill should be used when writing Python scripts that parse, analyze, or extract information from SystemVerilog files using the pyslang library. Covers CST (syntax tree), AST (elaborated symbol tree), type resolution, port/variable extraction, and source location mapping. Triggers on phrases like "pyslang", "用pyslang", "扫描SV", "提取端口", "SystemVerilog解析", "slang python", or when working with .sv file analysis tools.
version: 1.4.3
---

# pyslang API Reference & Coding Guide

pyslang 是 [slang](https://sv-lang.com) 的 Python 绑定，用于解析和编译 SystemVerilog 代码。

> **自动更新机制**：如果在编码过程中发现新的 API 用法、现有 API 记录有误、或某个枚举值不存在，**必须**更新本文档对应章节，并递增 `version` 的 patch 号。

---

## 1. 核心概念：CST vs AST

| | CST (Concrete Syntax Tree) | AST (Elaborated Abstract Syntax Tree) |
|---|---|---|
| 入口 | `syntax.SyntaxTree.fromFile()` / `fromText()` | `ast.Compilation()` + `comp.addSyntaxTree()` + `comp.getRoot()` |
| 模块 | `pyslang.syntax` | `pyslang.ast` |
| 节点类型 | 语法节点（`*Syntax`），含所有 Token、空格、注释 | 符号节点（`*Symbol`），类型已推导、参数已展开 |
| 节点标识 | `SyntaxKind` 枚举 | `SymbolKind` 枚举 |
| Token | `Token` 节点（关键字、标点）属于 CST | AST 中不保留分隔 Token |
| 类型信息 | 语法级（`ImplicitTypeSyntax`、`LogicTypeSyntax` 等），未推导 | 语义级（`ScalarType`、`PackedArrayType`），已推导 |
| **何时使用** | 需要访问源码级结构、遍历声明列表 | 需要类型推导、位宽计算、符号查找 |

**核心原则**：优先使用 AST 获取类型/位宽信息；若 AST 不提供成员迭代器，用 CST 遍历 + AST `body.find()` 混合模式。

---

## 2. CST API

### 2.1 解析入口

```python
from pyslang import syntax

# 从文件解析
tree = syntax.SyntaxTree.fromFile('/path/to/file.sv')
# 从字符串解析
tree = syntax.SyntaxTree.fromText('module m; endmodule')

root = tree.root       # CST 根节点
members = root.members # 顶层成员列表
```

### 2.2 SyntaxKind 枚举

```python
SK = syntax.SyntaxKind

# 常用值（已验证存在于 pyslang ≥11.0.0）:
SK.ModuleDeclaration           # 模块定义
SK.ImplicitAnsiPort            # ANSI 隐式端口
SK.ExplicitAnsiPort            # ANSI 显式端口
SK.NetPortHeader               # 网络端口头部 (input wire ...)
SK.VariablePortHeader          # 变量端口头部 (output logic ...)
SK.DataDeclaration             # 变量声明 (logic x; reg y;)
SK.NetDeclaration              # 网络声明 (wire w; tri t;)
SK.ParameterDeclaration        # 参数声明节点
SK.ParameterDeclarationStatement # 参数声明的外层包装节点
SK.GenvarDeclaration           # genvar 声明
SK.SpecparamDeclaration        # specparam 声明
SK.UserDefinedNetDeclaration   # 用户自定义网络类型

# 类型节点
SK.LogicType, SK.RegType, SK.BitType, SK.ByteType
SK.ShortIntType, SK.LongIntType, SK.IntType, SK.IntegerType
SK.RealType, SK.ShortRealType, SK.RealTimeType, SK.TimeType
SK.StringType, SK.VoidType, SK.EventType
SK.StructType, SK.EnumType, SK.UnionType
SK.CHandleType, SK.VirtualInterfaceType
SK.ImplicitType, SK.NamedType
SK.SequenceType, SK.PropertyType

# 模块实例化
SK.HierarchyInstantiation      # 模块实例化语句（如 adder_8bit u_adder(...)）
```

### 2.3 Token 与 TokenKind

```python
from pyslang import parsing

TK = parsing.TokenKind

# 方向关键字
TK.InputKeyword    # input
TK.OutputKeyword   # output
TK.InOutKeyword    # inout
TK.RefKeyword      # ref

# 网络类型关键字
TK.WireKeyword, TK.TriKeyword, TK.TriAndKeyword
TK.TriOrKeyword, TK.TriRegKeyword, TK.Tri0Keyword, TK.Tri1Keyword
TK.WAndKeyword, TK.WOrKeyword, TK.UWireKeyword
TK.Supply0Keyword, TK.Supply1Keyword

# 分隔 Token（在 port 列表中）
TK.OpenParenthesis  # (
TK.CloseParenthesis # )
TK.Comma            # ,
TK.Semicolon        # ;

# Token 常用属性
token.kind       # TokenKind 枚举值
token.valueText  # 源码文本 (str)
token.value      # 值 (如 SVInt)
token.rawText    # 原始文本含空格
```

### 2.4 过滤 Token vs SyntaxNode

端口的 `header.ports` 列表包含 Token（括号、逗号）和 SyntaxNode 混在一起：

```python
import pyslang
from pyslang import parsing

# 方法 1：isinstance 过滤
if isinstance(port, parsing.Token):
    continue  # 跳过分隔 Token

# 方法 2：kind 比较（仅 SyntaxNode 有 SyntaxKind）
if port.kind == syntax.SyntaxKind.ImplicitAnsiPort:
    # 处理端口
```

### 2.5 模块成员遍历

模块的 CST 节点通过 `body.syntax` 获取：

```python
comp = ast.Compilation()
comp.addSyntaxTree(tree)
root = comp.getRoot()

for top_inst in root.topInstances:
    module_cst = top_inst.body.syntax  # ModuleDeclarationSyntax
    for member in module_cst.members:
        kind = member.kind
        # 检查各种声明类型:
        # DataDeclaration, NetDeclaration, ParameterDeclarationStatement,
        # GenvarDeclaration, ProceduralBlock, ContinuousAssign, etc.
```

### 2.6 端口头部类型

ANSI 端口头部有两种 CST 节点类型：

```python
# 网络端口：input wire [7:0] foo
if port_header.kind == SK.NetPortHeader:
    net_type_token = port_header.netType  # Token (WireKeyword, TriKeyword, ...)

# 变量端口：output logic [7:0] bar
elif port_header.kind == SK.VariablePortHeader:
    data_type = port_header.dataType      # 类型节点 (LogicTypeSyntax, ...)
    # 注意：VariablePortHeaderSyntax 没有 varKeyword 属性！
```

### 2.7 声明节点结构

```python
# DataDeclaration / NetDeclaration / ParameterDeclaration:
#   有 declarators 列表，每个 decl 有 decl.name.value (变量名)

# ParameterDeclarationStatement:
#   是包装节点，实际声明在 member.parameter (ParameterDeclarationSyntax)

# GenvarDeclaration:
#   有 identifiers 列表，每个 ident.identifier.valueText (genvar 名)

# HierarchyInstantiation (模块实例化):
#   有 instances 列表，每个 inst 是 InstanceNameSyntax
#   实例名通过 inst.name.valueText 获取（字符串）
#   端口连接通过 member.instances 对应的 AST InstanceSymbol.portConnections 获取
```

### 2.8 StatementKind 语句节点（AST 层，已验证 pyslang 11.0.0）

语句节点的 `.kind` 是 `StatementKind` 枚举（不是 SymbolKind！）。`visit()` 会遍历到
语句节点及嵌套的表达式节点。语句节点直接暴露结构属性，可用于"条件门控"分析：

```python
SK = ast.StatementKind

SK.Conditional   # if / else if / else
                 # 属性: .conditions (list[ConditionalStatement.Condition],
                 #       每个 Condition 有 .expr 条件表达式、.pattern)
                 #       .ifTrue / .ifFalse (分支语句，可为 None)
SK.Case          # case / casez / casex
                 # 属性: .expr (选择表达式)、.items (list[CaseItem]，
                 #       每个 CaseItem 有 .expressions 模式列表、.stmt 分支语句)、
                 #       .defaultCase (默认分支，可为 None)
SK.ForLoop       # for 循环（注意：没有 Loop 枚举，for 是 ForLoop！）
                 # 属性: .stopExpr (循环条件)、.body (循环体)、
                 #       .initializers / .steps / .loopVars
SK.Timed         # @(posedge clk) 等事件控制
                 # 属性: .timing (TimingControlKind，如 SignalEvent，内含事件表达式)、
                 #       .stmt (被门控的主体语句)
SK.Block         # begin...end 块
SK.ExpressionStatement  # 表达式语句（内嵌 Assignment 等）
```

**用途示例**：判断"赋值语句被哪些条件门控"——遍历语句树，对每个 `Conditional`/
`Case`/`ForLoop`/`Timed` 节点，把其条件表达式（`.conditions[i].expr` / `.expr` /
`.stopExpr` / `.timing`）广播给分支子树（`.ifTrue`/`.ifFalse`/`.items[i].stmt`/
`.body`/`.stmt`）内的所有 `Assignment` 节点。嵌套条件自动累积（外层分支子树包含
内层 if 的分支）。

**注意**：`visit()` 是前序 DFS 无退出回调，无法靠遍历顺序判断"当前在哪个分支里"；
必须用属性直取条件表达式。pybind11 每次访问表达式节点会新建 Python wrapper
（`id()` 不稳定），不要用 `id(表达式节点)` 做跨遍历关联的键（符号 Symbol 可以）。

---

## 3. AST API

### 3.1 编译与 Elaboration

```python
from pyslang import ast

comp = ast.Compilation()
comp.addSyntaxTree(tree)
root = comp.getRoot()  # RootSymbol

# 编译诊断
diags = comp.getAllDiagnostics()  # list[Diagnostic]
for d in diags:
    d.code       # DiagCode 枚举值（如 DiagCode(ArithOpMismatch)）
    d.isError()  # bool: 是否为错误（注意：是方法不是属性！）
    d.args       # list: 诊断参数（如类型名）
    d.location   # SourceLocation: 关联位置
    d.ranges     # list[SourceRange]: 关联源码范围
    d.symbol     # Symbol: 关联的符号
```

### 3.1.1 Elaboration 做了什么（为什么 visit() 能递归找到所有嵌套实例）

pyslang 的 elaboration 阶段（`comp.getRoot()` 触发）会完成以下工作，这些是 `visit()` 能自动发现所有嵌套实例的**前提**：

1. **解析模块实例化** — 将 CST 中的 `HierarchyInstantiation`（如 `adder_8bit u_adder(...)`）解析为 AST 中的 `InstanceSymbol`，挂到父 `InstanceBodySymbol` 的符号树下
2. **展开 generate 块** — 解析 `if/for/case` generate，为实际生成的实例创建对应的 `InstanceSymbol`
3. **展开 parameter** — 参数化模块的类型和位宽在 elaboration 后成为具体值
4. **解析 config / bind** — 建立 `config` 绑定关系和 `bind` 语句

这意味着：**在 elaboration 之后的 AST 中，所有实例化关系已经是一棵完整的树**。一个顶层模块 A 实例化了 B，B 实例化了 C，那么在 A 的 `InstanceBodySymbol` 的符号树中，B 是其直接子符号，而 C 出现在 B 的 `InstanceBodySymbol` 的符号树中。

`InstanceSymbol.visit(callback)` 遍历的正是这棵**已经构建好的树**——它不需要递归打开文件，不需要手动管理 `Compilation`，所有嵌套关系在 elaboration 时就已经确定了。

**如果缺少子模块定义**（未将某些 SV 文件加入 `Compilation`），elaboration 无法解析子模块，它们会退化为 `SymbolKind.UninstantiatedDef` 而非 `InstanceSymbol`。因此层次遍历**必须一次性编译所有源文件**。

### 3.2 顶层实例与模块查找

```python
# 方式 1：遍历所有顶层实例
for top_inst in root.topInstances:
    name = top_inst.name       # 模块名
    body = top_inst.body       # InstanceBodySymbol
    ports = body.portList      # list[PortSymbol]

# 方式 2：按名称查找
inst = root.lookupName("module_name")  # InstanceSymbol
body = inst.body
```

### 3.3 SymbolKind 枚举

```python
SK = ast.SymbolKind

# 已验证存在的值（pyslang ≥11.0.0）:
SK.Root            # 根
SK.Instance        # 模块/接口实例
SK.InstanceBody    # 实例体（含 portList）
SK.Port            # 端口
SK.Variable        # 变量
SK.Net             # 网络
SK.Parameter       # 参数
SK.Specparam       # specparam
SK.Genvar          # genvar
SK.Field           # struct/union 字段
SK.EnumValue       # 枚举值（不是 EnumMember!）
SK.ClockVar        # clocking 变量
SK.Modport         # modport
SK.ModportPort     # modport 端口
SK.ModportClocking # modport clocking
SK.TypeAlias       # typedef 别名
SK.TypeParameter   # 类型参数
SK.ClassProperty   # 类属性
SK.FormalArgument  # 函数/任务参数
SK.LocalAssertionVar # 局部断言变量
SK.PatternVar      # 模式变量
SK.Iterator        # 迭代变量
SK.LetDecl         # let 声明
SK.DefParam        # defparam
SK.ScalarType      # 标量类型
SK.PackedArrayType # 打包数组类型
SK.Definition      # 定义符号
SK.UninstantiatedDef # 未实例化的定义（缺少子模块定义时出现）
SK.ContinuousAssign  # 连续赋值 (assign)
SK.ProceduralBlock   # 过程块 (always_comb, always_ff, etc.)
SK.Subroutine        # 子例程 (function, task)

# ExpressionKind 枚举 — 用于 AST 级表达式分析
EK = ast.ExpressionKind
EK.Assignment        # 赋值（含阻塞 =、非阻塞 <=、复合 += 等）
                     # 属性: .left (LHS), .right (RHS), .isNonBlocking (bool), .isCompound (bool)
                     # 实测: 复合赋值(+= 等) AST 不 desugar——.right 只含显式 RHS,
                     # 隐式读 LHS 需自行补(isCompound=True 时把 LHS 基链计入读取)
EK.NamedValue        # 变量/信号引用
                     # 属性: .symbol → VariableSymbol/NetSymbol（已解析类型/位宽/路径）
EK.UnaryOp           # 一元运算
                     # 实测: 自增/自减(i++/++i/i--/--i)是 UnaryOp 而非 Assignment
                     # (UnaryOperator.Preincrement/Postincrement/Predecrement/Postdecrement),
                     # 语义为隐式读+写操作数
EK.BinaryOp          # 二元运算
EK.ElementSelect     # 数组元素选择（读写两侧均出现）: .value (基表达式), .selector (下标)
                     # LHS 数组写 s[i] <= d: 沿 .value 链剥离得到基信号行（元素不单独成行）;
                     # 下标是读: LHS 的 .selector 中的 NamedValue 计入读取
                     # 读侧 x = mem[addr]: visit() 自然穿透命中 mem/addr，无需特殊代码
EK.ConditionalOp     # 三元运算符 (a ? b : c)
                     # 属性: visit() 会穿透到三个操作数（选择符 + 两个分支）
EK.IntegerLiteral    # 整数常量
EK.Conversion        # 类型转换
EK.EmptyArgument     # 空参数（端口连接中输出端口 RHS 常见）

# ProceduralBlockKind 枚举 — 用于区分过程块类型
PBK = ast.ProceduralBlockKind
PBK.AlwaysComb       # always_comb
PBK.AlwaysFF         # always_ff
PBK.AlwaysLatch      # always_latch
PBK.Always           # always (通用)
PBK.Initial          # initial
PBK.Final            # final
```

### 3.4 PortSymbol（端口）

```python
port = body.portList[0]

port.name                 # str: 端口名
port.direction            # ArgumentDirection 枚举
port.isNetPort            # bool: 是否为网络端口
port.isAnsiPort           # bool: 是否为 ANSI 端口
port.type                 # Type: 推导后的类型对象

# 端口查找
body.findPort("port_name")   # 按名称查找端口，返回 PortSymbol 或 None
                             # 与 body.find() 不同：find() 查找变量/网络，findPort() 查找端口

# 端口对应的内部信号（用于跨模块扇出追踪）
port.internalSymbol       # Symbol: 端口模块内部的对应变量
                          # 输入端口：模块内部接收输入值的变量（如 input a → a）
                          # 输出端口：模块内部驱动输出值的变量
port.internalExpr         # Expression: 端口内部连接表达式
```

**`findPort()` vs `find()`**：
- `body.find("clk")` → 查找内部变量/网络名为 `clk`（可能返回 VariableSymbol）
- `body.findPort("clk")` → 查找端口名为 `clk`（返回 PortSymbol 或 None）
- 端口在 `body.portList` 中，但 `find()` 不一定能查到端口

**`internalSymbol` 的用途**：在扇出追踪中，当变量连接到子模块的输入端口时，
`port.internalSymbol` 给出子模块内部接收该信号的变量，可继续在子模块中追踪。

### 3.5 方向枚举 (ArgumentDirection)

```python
from pyslang import ast

# 枚举值（用于分支逻辑判断）：
ast.ArgumentDirection.In       # 输入端口
ast.ArgumentDirection.Out      # 输出端口
ast.ArgumentDirection.InOut    # 双向端口
ast.ArgumentDirection.Ref      # ref 端口

# 比较模式（推荐）：直接枚举比较
if port.direction == ast.ArgumentDirection.In:
    ...  # 输入端口的处理
elif port.direction == ast.ArgumentDirection.Out:
    ...  # 输出端口的处理

# 字符串映射（仅用于输出/显示）：
DIRECTION_MAP = {
    ast.ArgumentDirection.In:    'input',
    ast.ArgumentDirection.Out:   'output',
    ast.ArgumentDirection.InOut: 'inout',
    ast.ArgumentDirection.Ref:   'ref',
}
```

### 3.6 类型系统 (Type)

```python
port_type = port.type

# 标量类型 (ScalarType)
if port_type.kind == ast.SymbolKind.ScalarType:
    str(port_type)         # "logic", "reg", "integer", "bit", ...
    port_type.bitWidth     # 1, 32 (integer), 64 (real/time), ...
    port_type.scalarKind   # 如 Kind.Logic, Kind.Reg, Kind.Bit, ...
    port_type.isIntegral   # bool
    port_type.isSimpleBitVector  # bool

# 打包数组类型 (PackedArrayType)
if port_type.kind == ast.SymbolKind.PackedArrayType:
    str(port_type)         # "logic[7:0]", "reg[1:0]", ...
    port_type.bitWidth     # 8, 2, ...
    port_type.elementType  # 元素类型 (ScalarType)
    port_type.range        # 范围对象
    port_type.range.left   # 7
    port_type.range.right  # 0

# 注意：没有 getBitstreamWidth() 或 getBitWidth() 方法！
# 直接用 bitWidth 属性（int）
```

### 3.7 内部变量查找 (body.find)

```python
body = top_inst.body

# AST 查找变量（返回 VariableSymbol / NetSymbol / ParameterSymbol 等）
sym = body.find("add_sub_result")
if sym:
    sym.name        # "add_sub_result"
    sym.kind        # SymbolKind.Variable / .Net / .Parameter / .Genvar
    str(sym.type)   # "logic[8:0]"
    sym.type.bitWidth  # 9
    sym.location    # SourceLocation (用于取行号)
```

### 3.8 SourceManager / 源位置映射

```python
sm = comp.sourceManager  # SourceManager

sym = body.find("foo")
if sym and sym.location:
    line   = sm.getLineNumber(sym.location)    # int: 行号
    column = sm.getColumnNumber(sym.location)  # int: 列号

# 获取文件路径（两种方式）：
#   方式 1: getFileName(location) → 相对路径字符串
rel_path = sm.getFileName(sym.location)  # 如 "test/with_instance/alu_system.sv"

#   方式 2: getFullPath(buffer_id) → 绝对路径 pathlib.Path
#   注意: getFullPath 接受 BufferID，不是 SourceLocation！需要用 location.buffer
abs_path = str(sm.getFullPath(sym.location.buffer))  # 如 "/home/.../alu_system.sv"

# 区分两个位置概念：
#   inst.location             → 实例化位置（在父模块中，指向父模块文件）
#   inst.definition.location  → 模块定义位置（指向模块自身的文件）
```

注意：`SourceLocation` 本身只有 `buffer` 和 `offset` 属性，没有 `line` / `column`。必须通过 `SourceManager` 映射。

### 3.9 InstanceSymbol（实例化模块）与层次遍历

`InstanceSymbol` 表示一个模块实例（如 `u_adder`），是层次遍历的核心节点。**前提**：必须将所有 SV 文件一起编译，否则子模块会退化为 `UninstantiatedDefSymbol`（缺少定义）。

#### 3.9.1 核心属性

```python
inst = root.topInstances[0]

# 实例与模块
inst.name                 # str: 实例名（如 "u_core"）
inst.definition.name      # str: 模块类型名（如 "alu_core"），注意不是 inst.name!
inst.hierarchicalPath     # str: 完整层次路径（如 "alu_system.u_core.u_adder"）
                          # 顶层为模块名，后续层级均为实例名

# 位置信息
inst.location             # SourceLocation: 实例化位置（指向父模块文件）
inst.definition.location  # SourceLocation: 模块定义位置（指向模块自身文件）

# 类型标志
inst.isModule             # bool: 是否为模块实例
inst.isInterface          # bool: 是否为接口实例

# AST 体访问
inst.body                 # InstanceBodySymbol: 实例体（含 portList, find() 等）
inst.body.syntax          # ModuleDeclarationSyntax: CST 节点（含 members 遍历）

# 端口连接
inst.portConnections      # list[PortConnection]: 实例的端口连接
# PortConnection 属性:
#   conn.port       → PortSymbol: 被连接的端口
#   conn.expression → Expression: 连接到的表达式（结构因方向而异，见下方）
#   conn.ifaceConn  → 接口连接（若为接口端口）
```

#### 3.9.1.1 端口连接的表达式结构（输入 vs 输出）

`conn.expression` 的结构取决于端口方向 —— 这是向下游扇出和向上游追溯的核心：

```
对于输入端口 (port.direction == In)：
  父模块:  alu_core u_core (.opcode(opcode), ...);
                                     ^^^^^^
  conn.expression.kind == ExpressionKind.NamedValue
  conn.expression.symbol → 父模块的变量 "opcode"
  conn.port.internalSymbol → 子模块内部变量 "opcode"（用于继续追踪）

对于输出端口 (port.direction == Out)：
  父模块:  alu_core u_core (.result(core_result), ...);
                                      ^^^^^^^^^^^
  conn.expression.kind == ExpressionKind.Assignment
  conn.expression.left   → 父模块被驱动的变量 "core_result"（NamedValue）
  conn.expression.right  → 通常是 EmptyArgument
  conn.port.internalSymbol → 子模块内部变量 "result"
```

**输入端口扇出追踪**（向下游）：变量 X 连接到了子模块的输入端口 P：
1. 遍历 `inst.portConnections`，筛选 `port.direction == In`
2. 对 `conn.expression` 做 `visit()`，查找 `NamedValue` 匹配变量名 X
3. 命中 → `port.internalSymbol` 即子模块内的下游变量

**输出端口向上追溯**（从子模块输出端口回到父模块）：
1. 在父模块中，遍历 `inst.portConnections`，筛选 `port.direction == Out`
2. 对 `conn.expression`（`AssignmentExpression`），`.left.symbol` 即父模块的外部变量
3. 此外部变量可在父模块中按输入端口扇出继续追踪
```

#### 3.9.2 visit() 递归遍历

所有 Symbol 子类都有 `visit(callback)` 方法。**关键保证**：`visit()` 以**DFS（深度优先、前序）**遍历整个符号子树——不是只访问一层，而是递归进入每一层嵌套。

**为什么嵌套实例会被找到？**

elaboration 之后，AST 中的实例化关系是一棵完整的树：

```
RootSymbol
├── topInstances[0]: alu_system          ← 顶层实例（未被其他模块实例化）
│   └── InstanceBodySymbol               ← 展开后的实例体
│       ├── PortSymbol: clk, rst, ...    ← 端口
│       ├── InstanceSymbol: u_core       ← 嵌套子实例（在 body 的符号树中）
│       │   └── InstanceBodySymbol
│       │       ├── InstanceSymbol: u_adder   ← 更深层嵌套
│       │       │   └── InstanceBodySymbol ...
│       │       └── InstanceSymbol: u_mult
│       │           └── InstanceBodySymbol ...
│       └── InstanceSymbol: u_io_ctrl    ← 另一个子实例
│           └── InstanceBodySymbol ...
├── topInstances[1]: another_top
│   └── ...
```

当调用 `top_inst.visit(callback)` 时，遍历从顶层实例的根开始，DFS 进入每一层 `InstanceBodySymbol`，因此 callback 会按**前序**（父先于子）依次遇到所有层级的 `InstanceSymbol`。

```python
instances = []

def collect_instances(sym):
    """收集所有 InstanceSymbol（只过滤 SymbolKind.Instance）"""
    if sym.kind == ast.SymbolKind.Instance:
        instances.append(sym)

# 对每个顶层实例启动遍历——一次 visit() 覆盖所有层级
for top_inst in root.topInstances:
    top_inst.visit(collect_instances)

# instances 现在包含所有层次中的全部实例（DFS 前序）
# 每个 InstanceSymbol.hierarchicalPath 自动正确：
#   "alu_system.u_core"         ← 第二层
#   "alu_system.u_core.u_adder" ← 第三层
#   "alu_system.u_core.u_mult"  ← 第三层
#   "alu_system.u_io_ctrl"      ← 第二层
```

**注意**：`visit()` 会遍历**所有**类型的符号节点（含表达式、语句、类型等），很多节点没有 `name` 属性，callback **必须**用 `sym.kind` 过滤目标类型。

#### 3.9.2.1 为什么不用 CST 手动递归？

| 方式 | 问题 |
|---|---|
| CST `body.syntax.members` 手动递归 | 需要递归打开每个子模块的文件 → 需要手动管理多个 `Compilation`；无法自动跨越文件边界 |
| AST `visit()` | elaboration 已解析所有子模块 → 一棵完整的树，一次遍历即可 |

**`visit()` 之所以简洁有效，核心在于 pyslang 已经在 elaboration 阶段替我们做完了最重的活**——解析模块实例化、展开 generate、推导 parameter、建立完整的符号树。`visit()` 只需要在这棵树上做 DFS 遍历并筛选目标节点。

#### 3.9.3 额外属性

```python
# 数组实例
inst.arrayName            # 数组名（若为数组实例）
inst.arrayPath            # 数组路径

# 查找端口连接
inst.getPortConnection(port_name)  # 按名称查找端口连接
inst.canonicalBody         # 规范体（参数化展开后）

# 父级关系
inst.parentScope           # 父作用域
inst.declaredType          # 声明类型（通常为 None，用 definition.name）
inst.declaringDefinition   # 声明定义
```

### 3.10 DefinitionSymbol（模块定义）

```python
defn = inst.definition  # DefinitionSymbol

defn.name                # str: 模块名（如 "adder_8bit"）
defn.kind                # SymbolKind.Definition
defn.location            # SourceLocation: 定义位置
defn.definitionKind      # 定义种类
defn.defaultLifetime     # 默认生命周期
defn.defaultNetType      # 默认网络类型
defn.timeScale           # 时间刻度
defn.unconnectedDrive    # 未连接驱动行为
defn.instanceCount       # int: 被实例化的次数
defn.cellDefine          # bool: 是否为 cell define
defn.syntax              # CST 节点

# 注意：DefinitionSymbol 没有 body 属性！
# 要访问 InstanceBodySymbol 请使用 InstanceSymbol.body
```

### 3.11 InstanceBodySymbol 补充属性

```python
body = inst.body  # InstanceBodySymbol

# 除了已记录的 portList, find(), findPort(), syntax:
body.containingInstance   # InstanceBodySymbol: 包含此体的实例体（非 InstanceSymbol！）
                           # 注意: 返回值类型是 InstanceBodySymbol，不是 InstanceSymbol
body.containingInstance.parentInstance  # InstanceSymbol: 真正的实例符号（含 portConnections）
body.parentInstance       # InstanceSymbol: 父实例
body.lookupName(name)     # 按名称查找子符号
body.parameters           # list: 参数列表
body.defaultNetType       # 默认网络类型
body.timeScale            # 时间刻度
body.isUninstantiated     # bool: 是否未被实例化
body.isProceduralContext  # bool: 是否为过程上下文
body.compilationUnit      # 编译单元
body.definition           # DefinitionSymbol: 回到模块定义
```

---

## 4. 已验证的编码模式

### 4.1 端口扫描（纯 AST）

```python
# 完全使用 AST 符号树提取端口
comp = ast.Compilation()
comp.addSyntaxTree(syntax.SyntaxTree.fromFile(filepath))
root = comp.getRoot()

for top in root.topInstances:
    for port in top.body.portList:
        # ArgumentDirection 枚举、str(port.type)、port.type.bitWidth
```

### 4.2 变量扫描（CST 遍历 + AST 查找）

```python
# InstanceBodySymbol 没有 members 迭代器 → 用 CST 遍历声明，AST 查类型
sm = comp.sourceManager
body = top.body

for member in body.syntax.members:
    if member.kind in DECLARATION_KINDS:
        for decl in member.declarators:
            name = decl.name.value
            sym = body.find(name)
            if sym:
                line = sm.getLineNumber(sym.location)
                # str(sym.type), sym.type.bitWidth
```

### 4.3 层次遍历（visit 收集 + 输出组装）

```python
# 提取完整实例化层次，输出 {层次路径: {module, file, ast, ports}}
def extract_hierarchy(sv_files):
    # 步骤 1: 编译所有文件（必须全部编译！）
    comp = ast.Compilation()
    for f in sv_files:
        comp.addSyntaxTree(syntax.SyntaxTree.fromFile(f))
    root = comp.getRoot()
    sm = comp.sourceManager

    # 步骤 2: visit() 收集所有 InstanceSymbol
    instances = []
    def collect(sym):
        if sym.kind == ast.SymbolKind.Instance:
            instances.append(sym)
    for top_inst in root.topInstances:
        top_inst.visit(collect)

    # 步骤 3: 遍历实例列表，组装输出 dict
    result = {}
    for inst in instances:
        # 文件路径：用 definition.location → 指向模块定义文件
        file_path = str(sm.getFullPath(inst.definition.location.buffer))
        
        # 端口提取
        ports = []
        for port in inst.body.portList:
            ports.append({
                'name': port.name,
                'direction': DIRECTION_MAP.get(port.direction, str(port.direction)),
                'width': port.type.bitWidth if port.type and hasattr(port.type, 'bitWidth') else 0,
            })
        
        result[inst.hierarchicalPath] = {
            'module': inst.definition.name,
            'file': file_path,
            'ast': inst.body,        # InstanceBodySymbol，供后续解析使用
            'ports': ports,
        }

    return result
```

**关键点**：
- `inst.hierarchicalPath` 自动满足路径格式要求（顶层模块名 + 下级实例名）
- `inst.location` ≠ `inst.definition.location`：前者指向实例化位置（父文件），后者指向模块定义位置（自身文件）
- `inst.definition.name`（模块类型名）≠ `inst.name`（实例名）
- `DefinitionSymbol` 没有 `body` 属性，必须通过 `InstanceSymbol.body` 访问 `InstanceBodySymbol`

### 4.4 变量扇出追踪（Variable Fan-Out Tracing）

三类信号分类 + 单级扇出追踪。给定一个变量，找到它**直接**驱动的下一级变量（仅一跳）。

#### 4.4.1 信号分类与入口分发

用 `body.findPort()` 判断变量类型，分发到不同追踪逻辑：

```python
def trace_var_driver(filelist_path, var_path):
    # ... 复用 hierarchy 构建层次、hierarchy_var 解析变量 ...
    body = hierarchy[inst_path]['ast']

    is_input, is_output = _is_port(body, var_name)

    if is_output:
        # 情况 3：输出端口 → 向上追溯到父模块 wire
        symbols = _trace_output_port(hierarchy, inst_path, var_name)
    else:
        # 情况 1/2：内部变量或输入端口 → 模块内追踪
        symbols = _trace_in_module(body, var_name)

    return _build_result(var_info, symbols)


def _is_port(body, var_name):
    """判断变量是否为端口"""
    port = body.findPort(var_name)  # 注意：用 findPort() 而非 find()
    if port is None:
        return False, False
    is_input = port.direction == ast.ArgumentDirection.In
    is_output = port.direction == ast.ArgumentDirection.Out
    return is_input, is_output
```

#### 4.4.2 模块内追踪（内部变量 / 输入端口）

两步：A. 块扇出 + B. 子模块端口扇出。

**A. 块扇出** — 找读取该变量的 ProceduralBlock / ContinuousAssign，收集所有 LHS：

```python
def _find_block_fanout(body, var_name, target_ci):
    driven = []

    def check_block(sym):
        if sym.kind not in (ast.SymbolKind.ProceduralBlock,
                            ast.SymbolKind.ContinuousAssign):
            return
        # 过滤：只查当前模块的直接块
        parent = sym.parentScope
        if hasattr(parent, 'containingInstance'):
            if parent.containingInstance is not target_ci:
                return

        lhs_syms = set()
        var_lhs_count = 0
        var_total_count = 0

        def collect(node):
            nonlocal var_lhs_count, var_total_count
            if node.kind == ast.ExpressionKind.Assignment:
                left = node.left if hasattr(node, 'left') else None
                if left is not None and left.kind == ast.ExpressionKind.NamedValue:
                    s = left.symbol if hasattr(left, 'symbol') else None
                    if s is not None:
                        lhs_syms.add(s)
                        if s.name == var_name:
                            var_lhs_count += 1
            if node.kind == ast.ExpressionKind.NamedValue:
                s = node.symbol if hasattr(node, 'symbol') else None
                if s is not None and s.name == var_name:
                    var_total_count += 1

        sym.visit(collect)

        # var_name 出现在 RHS/条件中（不仅是 LHS）→ 被读取
        if var_total_count > var_lhs_count:
            driven.extend(lhs_syms)

    body.visit(check_block)
    return driven
```

**关键点**：Counter 计数法判断读取关系 — 若 `var_name` 的总引用次数 > LHS 出现次数，
说明该变量在 RHS 或条件中被**读取**，则块内所有 LHS 变量都被它驱动。

**B. 子模块端口扇出** — 找由该变量驱动的子模块输入端口：

```python
def _find_input_port_fanout(body, var_name, target_ci):
    driven = []

    def check_instance(sym):
        if sym.kind != ast.SymbolKind.Instance:
            return
        parent = sym.parentScope
        if hasattr(parent, 'containingInstance'):
            if parent.containingInstance is not target_ci:
                return

        for conn in sym.portConnections:
            port = conn.port
            if port is None or port.direction != ast.ArgumentDirection.In:
                continue
            expr = conn.expression if hasattr(conn, 'expression') else None
            if expr is None:
                continue

            found = False
            def check_expr(node):
                nonlocal found
                if found:
                    return
                if node.kind == ast.ExpressionKind.NamedValue:
                    s = node.symbol if hasattr(node, 'symbol') else None
                    if s is not None and s.name == var_name:
                        found = True
            expr.visit(check_expr)

            if found:
                internal = port.internalSymbol if hasattr(port, 'internalSymbol') else None
                if internal is not None:
                    driven.append(internal)

    body.visit(check_instance)
    return driven
```

#### 4.4.3 输出端口向上追溯

输出端口不在模块内部追踪，而是回到父模块找对应的 wire：

```python
def _trace_output_port(hierarchy, inst_path, port_name):
    """从子模块输出端口上溯到父模块 wire，不继续往下穿透。"""
    segments = inst_path.split('.')
    if len(segments) < 2:
        return []  # 顶层模块无父模块

    parent_inst_path = '.'.join(segments[:-1])
    inst_name = segments[-1]

    parent_body = hierarchy[parent_inst_path]['ast']
    parent_target_ci = parent_body.containingInstance

    result = []
    def find_instance(sym):
        nonlocal result
        if result:
            return
        if sym.kind != ast.SymbolKind.Instance:
            return
        if sym.name != inst_name:
            return
        p = sym.parentScope
        if hasattr(p, 'containingInstance'):
            if p.containingInstance is not parent_target_ci:
                return

        for conn in sym.portConnections:
            port = conn.port
            if port is None or port.direction != ast.ArgumentDirection.Out:
                continue
            if port.name != port_name:
                continue
            expr = conn.expression if hasattr(conn, 'expression') else None
            if expr is None:
                continue
            # 输出端口连接表达式 = Assignment，.left = 父模块外部变量
            if expr.kind == ast.ExpressionKind.Assignment:
                left = expr.left if hasattr(expr, 'left') else None
                if left is not None and left.kind == ast.ExpressionKind.NamedValue:
                    s = left.symbol if hasattr(left, 'symbol') else None
                    if s is not None:
                        result = [s]  # 只返回父模块 wire，不进一步穿透

    parent_body.visit(find_instance)
    return result
```

**设计原则**：`_trace_output_port` 只返回父模块 wire，**不继续穿透**。保证每一级
扇出是精确的一跳。例如 `alu_system.u_core.carry` → 返回 `[alu_system.core_carry]`，
用户再调用 `trace_var_driver(..., "alu_system.core_carry")` 追下一级。

#### 4.4.4 扇出追踪的完整数据流

```
输入: alu_system.u_core.carry (输出端口)
  → _is_port 判断为输出端口
  → _trace_output_port:
      inst_path="alu_system.u_core", port_name="carry"
      → 父模块 alu_system 中找实例 u_core
      → 遍历 portConnections，找到 port.name=="carry" 的 Out 连接
      → 提取外部变量: alu_system.core_carry  ← 返回值

输入: alu_system.core_carry (内部变量)
  → _is_port 判断为内部变量
  → _trace_in_module:
      A. _find_block_fanout: 无块读取 core_carry → 空
      B. _find_input_port_fanout:
         → 遍历子实例 (u_result) 的输入端口连接
         → 找到 .carry_in(core_carry) 匹配
         → 返回 port.internalSymbol: u_result.carry_in  ← 返回值

输入: alu_system.u_core.opcode (输入端口)
  → _is_port 判断为输入端口
  → _trace_in_module:
      A. _find_block_fanout:
         → always_comb: opcode 在 if 条件中被引用 → 收集 add_b_mux, add_cin
         → assign: opcode 在 RHS → 收集 logic_sel
         → always_comb case: opcode 在 case 表达式 → 收集 result, carry
      B. _find_input_port_fanout: opcode 未直接连到子模块输入 → 空
  → 返回 5 个被驱动变量
```

### 4.5 AST 过程块/赋值语句内部变量扫描

用 `ExpressionKind.Assignment` 和 `ExpressionKind.NamedValue` 在 AST 层扫描 always 块/assign 语句内部的赋值和变量引用，区分 LHS-only（仅被赋值）和 RHS/条件读取变量。

```python
from collections import Counter

def scan_block_variables(ast_symbol):
    """扫描块内变量，返回被读取的 Symbol 集合（排除仅 LHS 的变量）。"""
    lhs_symbols = []  # 赋值 LHS 的 symbol
    all_symbols = []  # 所有 NamedValue 的 symbol

    def collect(node):
        if node.kind == ast.ExpressionKind.Assignment:
            left = node.left if hasattr(node, 'left') else None
            if left is not None and left.kind == ast.ExpressionKind.NamedValue:
                s = left.symbol if hasattr(left, 'symbol') else None
                if s is not None:
                    lhs_symbols.append(s)
        if node.kind == ast.ExpressionKind.NamedValue:
            s = node.symbol if hasattr(node, 'symbol') else None
            if s is not None:
                all_symbols.append(s)

    ast_symbol.visit(collect)

    # 排除仅出现在 LHS 的变量
    lhs_count = Counter(id(s) for s in lhs_symbols)
    all_count = Counter(id(s) for s in all_symbols)
    return {s for s in all_symbols if all_count[id(s)] > lhs_count.get(id(s), 0)}
```

**LHS-only 判定原理**：变量引用（`NamedValue`）在 AST 中不区分左右侧——`a = a + 1` 中，左 `a` 和右 `a` 都是 `NamedValue`。但 `Assignment.left` 天然区分了位置。因此：如果某 symbol 的 LHS 出现次数 == 总出现次数，说明它从未出现在 RHS/条件中 → 排除。

**适用**：`ProceduralBlock`（always_comb/always_ff 等）、`ContinuousAssign`。

### 4.6 查找赋值块（AST 遍历 + parentScope 过滤）

`body.visit()` 会**穿透子模块实例**——遍历 `alu_core` 的 body 时，`adder_8bit` 内部的 `ProceduralBlock` 也会被访问到。必须用 `parentScope.containingInstance` 过滤：

```python
def find_containing_block(body, var_name, target_ci):
    """在 body 的直接块中查找包含 var_name 赋值的块。"""
    result = [None]

    def check_block(sym):
        if result[0] is not None:
            return
        if sym.kind not in (ast.SymbolKind.ProceduralBlock,
                            ast.SymbolKind.ContinuousAssign):
            return
        # 过滤子实例块：只保留 parentScope.containingInstance == target_ci 的
        parent = sym.parentScope
        if hasattr(parent, 'containingInstance'):
            if parent.containingInstance is not target_ci:
                return  # 跳过子实例中的块
        # 在块内查找目标变量的赋值
        found = False
        def check_assign(node):
            nonlocal found
            if found: return
            if node.kind == ast.ExpressionKind.Assignment:
                left = node.left if hasattr(node, 'left') else None
                if left and left.kind == ast.ExpressionKind.NamedValue:
                    s = left.symbol if hasattr(left, 'symbol') else None
                    if s and s.name == var_name:
                        found = True
        sym.visit(check_assign)
        if found:
            result[0] = sym

    body.visit(check_block)
    return result[0]
```

### 4.7 端口连接追踪（输入/输出端口双向）

#### 数据结构

| 端口方向 | `conn.expression.kind` | 变量访问方式 |
|---------|------------------------|-------------|
| `In` | `ExpressionKind.NamedValue` | `expr.symbol` → 父模块驱动变量 |
| `Out` | `ExpressionKind.Assignment` | `expr.left.symbol` → 父模块被驱动变量 |

#### 获取实例的 CST 完整实例化源文本

```python
# inst_ast: InstanceSymbol
# inst_ast.syntax → HierarchicalInstance CST（单个实例）
# inst_ast.syntax.parent → HierarchyInstantiation CST（完整实例化语句如 "adder_8bit u_adder (...);"）
hier_inst_cst = inst_ast.syntax.parent
sr = hier_inst_cst.sourceRange
# 用 sm.getLineNumber(sr.start) / sm.getLineNumber(sr.end) 获取行号
# 从文件读取该行范围的源文本
```

#### 输出端口追踪（找到驱动目标变量的子模块端口）

```python
def find_driving_instance(body, var_name, target_ci):
    """查找输出端口连接中包含 var_name 的子实例。"""
    result = [None]
    def check_inst(sym):
        if result[0] is not None: return
        if sym.kind != ast.SymbolKind.Instance: return
        parent = sym.parentScope
        if hasattr(parent, 'containingInstance'):
            if parent.containingInstance is not target_ci: return
        for conn in sym.portConnections:
            port = conn.port
            if port is None or port.direction != ast.ArgumentDirection.Out:
                continue
            expr = conn.expression
            if expr is None: continue
            # 检查是否包含目标变量
            if expr.kind == ast.ExpressionKind.Assignment:
                left = expr.left
                if left and left.kind == ast.ExpressionKind.NamedValue:
                    s = left.symbol
                    if s and s.name == var_name:
                        result[0] = sym
                        return
    body.visit(check_inst)
    return result[0]

# 获取驱动目标变量的子模块端口（而非全部输出端口）
def collect_driving_port(inst_ast, var_name):
    for conn in inst_ast.portConnections:
        port = conn.port
        if port is None or port.direction != ast.ArgumentDirection.Out:
            continue
        expr = conn.expression
        if expr is None: continue
        # 检查连接表达式是否匹配目标变量
        matches = False
        if expr.kind == ast.ExpressionKind.NamedValue:
            s = expr.symbol
            if s and s.name == var_name: matches = True
        elif expr.kind == ast.ExpressionKind.Assignment:
            left = expr.left
            if left and left.kind == ast.ExpressionKind.NamedValue:
                s = left.symbol
                if s and s.name == var_name: matches = True
        if matches:
            # 返回子模块端口 VariableSymbol（如 alu_system.u_core.carry）
            port_sym = inst_ast.body.find(port.name)
            if port_sym: return port_sym
    return None
```

#### 输入端口追踪（找到驱动输入端口的父模块信号）

```python
def find_input_port_connection(body, var_name):
    """检查变量是否为输入端口，返回驱动它的父模块信号。"""
    # 1. 确认是输入端口
    for port in body.portList:
        if port.name == var_name and port.direction == ast.ArgumentDirection.In:
            break
    else:
        return None  # 不是输入端口

    # 2. 从当前实例的端口连接找驱动信号
    # body.containingInstance 是 InstanceBodySymbol
    # body.containingInstance.parentInstance 才是 InstanceSymbol（含 portConnections）
    inst_sym = body.containingInstance.parentInstance
    if inst_sym is None:
        return None

    for conn in inst_sym.portConnections:
        if conn.port is None or conn.port.name != var_name:
            continue
        expr = conn.expression
        if expr is None: continue
        # 输入端口连接是 NamedValue
        if expr.kind == ast.ExpressionKind.NamedValue:
            return expr.symbol  # 如 core_carry
    return None
```

### 4.8 禁止的写法

- `str(kind) == "SyntaxKind.XXX"` → 用 `kind == SK.XXX` 枚举比较
- `'Input' in str(kind)` → 用 `kind == TK.InputKeyword` 枚举比较  
- `int(str(selector.left))` → 用 `int(selector.left.literal.value)` 或直接用 AST `port.type.bitWidth`
- `getattr(SK, 'WireType')` → WireType 不存在！Net 类型在 AST 中被推导为 logic
- `ast.SymbolKind.EnumMember` → 不存在！应为 `ast.SymbolKind.EnumValue`
- `data_type_node.getBitstreamWidth()` → 不存在！用 `bitWidth` 属性
- `inst.definition.body` → 不存在！`DefinitionSymbol` 没有 `body` 属性，用 `inst.body` 获取 `InstanceBodySymbol`
- `inst.location` 获取文件路径 → 用 `inst.definition.location`！前者指向父模块的实例化位置，后者才指向模块定义文件

---

## 5. 版本兼容性

本章记录 pyslang 版本间的 API 差异。当前基于 **pyslang 11.0.0**。

### 已确认不存在的属性/枚举值

- `SyntaxKind.WireType`, `SyntaxKind.TriType`, `SyntaxKind.TriAndType` 等 — Net 类型没有对应的 SyntaxKind
- `SyntaxKind.SignedType`, `SyntaxKind.UnsignedType` — 用 `signing` 属性
- `SyntaxKind.VariableDeclaration` — 只有 `ForVariableDeclaration`, `LocalVariableDeclaration`
- `SymbolKind.EnumMember` — 实际是 `SymbolKind.EnumValue`
- `SymbolKind.StructMember`, `SymbolKind.UnionMember` — 实际是 `SymbolKind.Field`
- `PackedArrayType.getBitstreamWidth()` / `ScalarType.getBitstreamWidth()` — 用 `.bitWidth` 属性
- `InstanceBodySymbol.members` — 不存在，用 `body.syntax.members` (CST)
- `GenvarDeclarationSyntax.declarator` — 不存在，用 `.identifiers` 列表
- `VariablePortHeaderSyntax.varKeyword` — 可能不存在

### 已确认需要区分的 API

- `inst.location` vs `inst.definition.location` — 前者是实例化位置（在父模块文件中），后者是模块定义位置（在模块自身文件中），获取文件路径时用后者
- `sm.getFileName(location)` vs `sm.getFullPath(buffer_id)` — 前者返回相对路径字符串，后者返回绝对路径 `pathlib.Path`；`getFullPath` 接受 `BufferID` 而非 `SourceLocation`，需用 `location.buffer` 传参
- `inst.name` vs `inst.definition.name` — 前者是实例名（如 `"u_adder"`），后者是模块类型名（如 `"adder_8bit"`）
- `DefinitionSymbol` 没有 `body` 属性 — 必须通过 `InstanceSymbol.body` 访问 `InstanceBodySymbol`
- `Diagnostic.isError()` — 是**方法**不是属性，需要加 `()` 调用
- `hierarchicalPath` — `InstanceSymbol` 和 `InstanceBodySymbol` 都有此属性，格式为 `"topModule.childInst.grandchildInst"`
- **`body.find(name)` vs `body.findPort(name)`** — 前者查找变量/网络/参数等内部符号，后者查找端口；端口不在 `find()` 的查找范围内，必须用 `findPort()`
- **输入端口 vs 输出端口的连接表达式结构不同**：
  - 输入端口：`conn.expression.kind == ExpressionKind.NamedValue`，`.symbol` 是父模块变量
  - 输出端口：`conn.expression.kind == ExpressionKind.Assignment`，`.left.symbol` 是父模块被驱动变量

### 已确认的运行时行为

- **缺少子模块定义** — 若未将所有 SV 文件加入 `Compilation`，子模块实例在 AST 中表现为 `UninstantiatedDefSymbol` 而非 `InstanceSymbol`，`visit()` 仍会遍历到它们但 `kind` 不同。层次遍历**必须一次性编译所有源文件**。
- **visit() 遍历范围** — `visit(callback)` 会遍历所有类型的符号节点（含表达式、语句等），callback 必须用 `sym.kind` 过滤目标类型，不可假设所有节点都有 `name` 属性。
- **`visit()` 穿透子实例** — `InstanceBodySymbol.visit()` 会遍历子模块实例内的符号（如 `alu_core` body 的 visit 会进入 `adder_8bit` 的 `ProceduralBlock`）。需用 `sym.parentScope.containingInstance is target_ci` 过滤仅保留当前模块的直接块。
- **`body.containingInstance` 类型** — 返回的是 `InstanceBodySymbol`，不是 `InstanceSymbol`。要访问 `portConnections` 需用 `body.containingInstance.parentInstance`。
- **获取完整实例化源文本** — `inst.syntax` 是 `HierarchicalInstance` CST（单个实例行），`inst.syntax.parent` 才是 `HierarchyInstantiation` CST（完整 `module_type inst_name (...);` 语句）。

### 已验证的编码最佳实践

- **`hasattr` 防御性属性访问** — pyslang 是 C++ 的 Python 绑定，某些属性在特定节点类型上可能不存在或为 None。访问 `Expression.left`、`Expression.symbol`、`PortConnection.expression` 等属性前应使用 `hasattr` 或判 None：
  ```python
  # 安全访问模式
  left = node.left if hasattr(node, 'left') else None
  s = left.symbol if left is not None and hasattr(left, 'symbol') else None
  expr = conn.expression if hasattr(conn, 'expression') else None
  if expr is None:
      continue
  ```
- **`id(symbol)` 去重** — pyslang 的 Symbol 对象在单次 elaboration 中具有**稳定的 Python 对象身份**。同一个变量（如 `alu_system.opcode`）在 AST 中的多个引用位置会返回相同的 Python 对象。因此 `id(s)` 可用于 Symbol 去重：
  ```python
  seen = set()
  for s in driven_symbols:
      if id(s) not in seen:
          seen.add(id(s))
          symbols.append(s)
  ```
  注意：**不能**用 `symbol.name` 去重——不同模块中可能有同名变量（如 `opcode` 同时存在于 `alu_system` 和 `alu_core`）。必须用 `id()` 或 `symbol.hierarchicalPath` 区分。

---

## 6. 更新日志

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.4.3 | 2026-08-23 | 补充 ExpressionKind 实测:复合赋值(isCompound)不 desugar、隐式读 LHS 需自行补;自增/自减为 UnaryOp 非 Assignment;新增 ElementSelect(.value/.selector,数组 LHS 解基行、下标是读) |
| 1.4.2 | 2026-08-16 | 新增：2.8 StatementKind 语句节点（Conditional/Case/ForLoop/Timed 结构属性、语句节点无 Loop 枚举、pybind11 表达式节点 id 不稳定）；3.3 ExpressionKind 补充 ConditionalOp（三元运算符，visit 穿透三操作数）| 
| 1.4.1 | 2026-07-30 | 完善：3.5 ArgumentDirection — 明确枚举值列表和直接比较模式（区分 DIRECTION_MAP 仅用于显示）；5 新增「已验证的编码最佳实践」— hasattr 防御性属性访问、id(symbol) 去重（name 不能去重的原因）|
| 1.4.0 | 2026-07-30 | 新增：ExpressionKind 枚举（Assignment/NamedValue 等）和 ProceduralBlockKind 枚举（3.3）；编码模式 4.5 AST 块内变量扫描 — LHS-only 排除算法（Counter 计数法）；4.6 查找赋值块 — parentScope.containingInstance 过滤子实例穿透；4.7 端口连接追踪 — 输入/输出端口双向、HierarchyInstantiation 源文本提取、子模块端口变量获取；新发现 — visit() 穿透子实例、body.containingInstance 类型纠正（InstanceBodySymbol vs InstanceSymbol）、inst.syntax.parent 获取完整实例化 CST |
| 1.3.0 | 2026-07-30 | 新增：端口连接表达式结构（3.9.1.1）— 输入/输出端口的 Expression 结构差异与扇出追踪方法；编码模式 4.4 变量扇出追踪 — 三类信号分类、块扇出、输入端口扇出、输出端口向上追溯；PortSymbol 补充 — findPort()、internalSymbol；确认 API 区分 — find() vs findPort()、输入/输出端口连接表达式结构不同 |
| 1.2.0 | 2026-07-29 | 新增：Elaboration 概念章节（3.1.1）阐述 pyslang elaboration 阶段所做的工作及为何 visit() 能自动递归；增强 visit() 递归遍历（3.9.2）— AST 实例树结构图、DFS 前序保证、前序示例路径、CST 手动递归对比表 |
| 1.1.0 | 2026-07-26 | 新增：InstanceSymbol 层次遍历（3.9）、DefinitionSymbol（3.10）、InstanceBodySymbol 补充属性（3.11）、层次遍历编码模式（4.3）；新增 SyntaxKind.HierarchyInstantiation（2.2）、CST 实例化节点结构（2.7）；新增 SymbolKind（UninstantiatedDef/ContinuousAssign/ProceduralBlock/Subroutine）；补充 SourceManager.getFileName/getFullPath 区分（3.8）；补充 Diagnostic 结构（3.1）；新增「已确认需要区分的 API」和「运行时行为」纠正项（5） |
| 1.0.0 | 2026-07-26 | 初始版本，覆盖 CST/AST 核心 API、端口扫描、变量扫描、源位置映射 |
