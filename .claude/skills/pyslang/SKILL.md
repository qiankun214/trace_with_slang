---
name: pyslang
description: This skill should be used when writing Python scripts that parse, analyze, or extract information from SystemVerilog files using the pyslang library. Covers CST (syntax tree), AST (elaborated symbol tree), type resolution, port/variable extraction, and source location mapping. Triggers on phrases like "pyslang", "用pyslang", "扫描SV", "提取端口", "SystemVerilog解析", "slang python", or when working with .sv file analysis tools.
version: 1.0.0
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
```

---

## 3. AST API

### 3.1 编译与 Elaboration

```python
from pyslang import ast

comp = ast.Compilation()
comp.addSyntaxTree(tree)
root = comp.getRoot()  # RootSymbol

# 诊断
diags = comp.getAllDiagnostics()  # list[Diagnostic]
```

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
```

### 3.4 PortSymbol（端口）

```python
port = body.portList[0]

port.name                 # str: 端口名
port.direction            # ArgumentDirection 枚举
port.isNetPort            # bool: 是否为网络端口
port.isAnsiPort           # bool: 是否为 ANSI 端口
port.type                 # Type: 推导后的类型对象
```

### 3.5 方向枚举 (ArgumentDirection)

```python
from pyslang import ast

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

### 3.8 行号 / 源位置

```python
sm = comp.sourceManager  # SourceManager

sym = body.find("foo")
if sym and sym.location:
    line   = sm.getLineNumber(sym.location)    # int
    column = sm.getColumnNumber(sym.location)  # int
```

注意：`SourceLocation` 本身只有 `buffer` 和 `offset` 属性，没有 `line` / `column`。必须通过 `SourceManager` 映射。

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

### 4.3 禁止的写法

- `str(kind) == "SyntaxKind.XXX"` → 用 `kind == SK.XXX` 枚举比较
- `'Input' in str(kind)` → 用 `kind == TK.InputKeyword` 枚举比较  
- `int(str(selector.left))` → 用 `int(selector.left.literal.value)` 或直接用 AST `port.type.bitWidth`
- `getattr(SK, 'WireType')` → WireType 不存在！Net 类型在 AST 中被推导为 logic
- `ast.SymbolKind.EnumMember` → 不存在！应为 `ast.SymbolKind.EnumValue`
- `data_type_node.getBitstreamWidth()` → 不存在！用 `bitWidth` 属性

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

---

## 6. 更新日志

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0.0 | 2026-07-26 | 初始版本，覆盖 CST/AST 核心 API、端口扫描、变量扫描、源位置映射 |
