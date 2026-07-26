#!/usr/bin/env python3
"""
scan_var.py - 使用 pyslang AST 扫描 SystemVerilog 文件，提取模块内部所有变量并打印

用法：
    python scan_var.py [sv_file_path]

默认扫描当前目录下的 simple_alu.sv

采用 CST 遍历 + AST 解析的混合策略：
  - CST：遍历模块成员，发现所有声明语句（Data / Net / Parameter 等）
  - AST：对每个声明的变量名，通过 body.find() 查找符号，
         获取经过 elaboration 的类型名、位宽和行号

输出的变量类别包括：
  - variable  ：logic / reg / integer 等变量
  - net       ：wire / tri / wand / wor 等网络
  - parameter ：parameter / localparam
  - genvar    ：genvar
  - enum_member / struct_member / union_member
"""

import sys
import os
from pyslang import ast, syntax


SK = syntax.SyntaxKind

# SymbolKind → 可读中文标签
KIND_LABELS = {
    ast.SymbolKind.Variable:          'variable',
    ast.SymbolKind.Net:               'net',
    ast.SymbolKind.Parameter:         'parameter',
    ast.SymbolKind.Specparam:         'specparam',
    ast.SymbolKind.Genvar:            'genvar',
    ast.SymbolKind.Field:             'field',
    ast.SymbolKind.EnumValue:         'enum_value',
    ast.SymbolKind.ClockVar:          'clocking',
    ast.SymbolKind.ModportPort:       'modport',
    ast.SymbolKind.ModportClocking:   'modport_clk',
    ast.SymbolKind.TypeAlias:         'typedef',
    ast.SymbolKind.TypeParameter:     'typeparam',
    ast.SymbolKind.ClassProperty:     'class_prop',
    ast.SymbolKind.FormalArgument:    'formal_arg',
    ast.SymbolKind.LocalAssertionVar: 'assert_var',
    ast.SymbolKind.PatternVar:        'pattern_var',
    ast.SymbolKind.Iterator:          'iterator',
    ast.SymbolKind.LetDecl:           'let',
    ast.SymbolKind.DefParam:          'defparam',
}


# ── CST 声明节点类型 ──────────────────────────────────────────────

# 包含 declarators 的成员类型：直接遍历 declarators
DECLARATION_KINDS = {
    SK.DataDeclaration,             # logic [7:0] foo;
    SK.NetDeclaration,              # wire [3:0] bar;
    SK.SpecparamDeclaration,        # specparam X = ...;
    SK.UserDefinedNetDeclaration,   # 用户自定义网络类型
}

# 包装类型：内部 member 节点包含 declarators
WRAPPED_DECL_KINDS = {
    SK.ParameterDeclarationStatement,  # parameter / localparam 包装
}


def _extract_from_declaration(decl_node, body, sm, results):
    """从 CST 声明节点中提取变量名，并查 AST 获取类型信息"""
    declarators = getattr(decl_node, 'declarators', None)
    if not declarators:
        return

    for decl in declarators:
        name = getattr(decl.name, 'value', None)
        if name is None:
            continue

        _add_from_ast(name, body, sm, results)


def _add_from_ast(name, body, sm, results):
    """通过 AST body.find() 解析符号的类型 / 位宽 / 行号"""
    symbol = body.find(name)
    if symbol is None:
        return

    kind = symbol.kind
    label = KIND_LABELS.get(kind, str(kind).replace('SymbolKind.', '').lower())

    type_str = str(symbol.type) if hasattr(symbol, 'type') and symbol.type else '—'
    width = symbol.type.bitWidth if hasattr(symbol, 'type') and symbol.type else '—'

    # ── 行号：通过 SourceManager 从 SourceLocation 提取 ──
    line = '—'
    if symbol.location and hasattr(symbol.location, 'buffer'):
        try:
            line = sm.getLineNumber(symbol.location)
        except Exception:
            pass

    results.append({
        'name': name,
        'kind': label,
        'type': type_str,
        'width': width,
        'line': line,
    })


def scan_variables(filepath):
    """
    扫描 SV 文件，提取模块内部所有变量 / 网络 / 参数信息。

    流程：
      1. SyntaxTree 解析为 CST
      2. Compilation elaboration
      3. 遍历每个顶层模块的 CST 成员
      4. 对每个声明，用 AST body.find() 查符号类型，用 SourceManager 查行号
    """
    tree = syntax.SyntaxTree.fromFile(filepath)
    comp = ast.Compilation()
    comp.addSyntaxTree(tree)

    # 诊断
    diagnostics = comp.getAllDiagnostics()
    if diagnostics:
        print(f"警告: 发现 {len(diagnostics)} 条编译诊断信息")
        for d in diagnostics[:3]:
            print(f"  - {d}")
        if len(diagnostics) > 3:
            print(f"  ... 共 {len(diagnostics)} 条")
        print()

    root = comp.getRoot()
    sm = comp.sourceManager
    all_vars = []

    for top_inst in root.topInstances:
        module_name = top_inst.name
        print(f"模块名称: {module_name}")

        body = top_inst.body
        module_cst = body.syntax

        variables = []

        for member in module_cst.members:
            kind = member.kind

            # 1. 直接包含 declarators 的声明节点
            if kind in DECLARATION_KINDS:
                _extract_from_declaration(member, body, sm, variables)

            # 2. 包装类型：ParameterDeclarationStatement 等
            elif kind in WRAPPED_DECL_KINDS:
                inner = getattr(member, 'parameter', None)
                if inner is not None:
                    _extract_from_declaration(inner, body, sm, variables)

            # 3. GenvarDeclaration：使用 identifiers 列表
            elif kind == SK.GenvarDeclaration:
                for ident in getattr(member, 'identifiers', []) or []:
                    token = getattr(ident, 'identifier', None)
                    if token is not None:
                        _add_from_ast(token.valueText, body, sm, variables)

            # 4. 其他可扩展类型：
            #    - TypedefDeclaration / ForwardTypedefDeclaration
            #    - EnumDeclaration / StructDeclaration / UnionDeclaration
            #    - 等等

        all_vars.extend(variables)

    return all_vars


def main():
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(script_dir, 'simple_alu.sv')

    if not os.path.exists(filepath):
        print(f"错误: 文件不存在 - {filepath}")
        sys.exit(1)

    print(f"扫描文件: {filepath}")
    print()

    variables = scan_variables(filepath)

    if not variables:
        print("未找到变量 / 网络 / 参数。")
        return

    # 打印
    print(f"{'名称':<20} {'行号':<6} {'类别':<12} {'类型':<20} {'位宽':<6}")
    print("-" * 66)

    for v in variables:
        width_str = str(v['width']) if v['width'] != '—' else '—'
        line_str = str(v['line']) if v['line'] != '—' else '—'
        print(f"{v['name']:<20} {line_str:<6} {v['kind']:<12} {v['type']:<20} {width_str:<6}")

    print()
    print(f"共扫描到 {len(variables)} 个变量 / 网络 / 参数。")


if __name__ == "__main__":
    main()
