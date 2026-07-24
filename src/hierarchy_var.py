#!/usr/bin/env python3
"""
hierarchy_var.py - 通过层次路径查找 SystemVerilog 模块内部变量

功能：
  1. 输入层次变量路径（如 alu_system.u_core.add_sum），找到变量
  2. 确定其类型、位宽、符号种类
  3. 全程使用 AST（elaborated symbol tree）

路径格式：
  <top的module名>.<实例名>.<实例名>...<变量名>
  首段为顶层模块名，末段为变量名，中间为实例名

用法（程序化调用）：
  from hierarchy import parse_filelist, extract_hierarchy
  from hierarchy_var import find_hierarch_var

  h = extract_hierarchy(parse_filelist('filelist.f'))
  v = find_hierarch_var(h, 'alu_system.u_core.add_sum')

用法（CLI）：
  python hierarchy_var.py <filelist_path> <var_path>
  python hierarchy_var.py ../test/with_instance/filelist.f alu_system.u_core.add_sum
"""

import sys
import os
from pyslang import ast

# 导入 hierarchy 模块的公开函数
from hierarchy import parse_filelist, extract_hierarchy


# ── 符号种类映射：SymbolKind → 可读标签 ──────────────────────────

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


# ==============================================================================
# 公开 API
# ==============================================================================

def find_hierarch_var(hierarchy, var_path):
    """
    通过层次路径查找 elaborated 变量符号，返回变量信息。

    解析 var_path（如 "alu_system.u_core.add_sum"），在 hierarchy dict
    中查找对应的 InstanceBodySymbol，再用 AST body.find() 解析变量符号。

    Args:
        hierarchy: extract_hierarchy() 返回的 dict[str, dict]，
                   key 为 hierarchicalPath，value 含 'ast' (InstanceBodySymbol)
        var_path:  层次变量路径，点分隔，格式为 <顶层模块>.<实例>.<变量名>

    Returns:
        dict: {name, type_name, bit_width, kind, hierarchical_path, instance_path}

    Raises:
        ValueError: 路径格式错误、实例路径不存在或变量未找到时
    """
    # ── 1. 解析路径 ─────────────────────────────────────────────
    segments = var_path.split('.')
    if len(segments) < 2:
        raise ValueError(
            f"层次变量路径至少需要两段 (顶层模块.变量名)，得到: {var_path}"
        )

    var_name = segments[-1]
    inst_path = '.'.join(segments[:-1])

    # ── 2. 查找实例 body ────────────────────────────────────────
    entry = hierarchy.get(inst_path)
    if entry is None:
        raise ValueError(f"层次路径不存在: {inst_path}")

    body = entry['ast']  # InstanceBodySymbol

    # ── 3. 查找变量符号 ─────────────────────────────────────────
    symbol = body.find(var_name)
    if symbol is None:
        raise ValueError(f"变量 '{var_name}' 在 '{inst_path}' 中未找到")

    # ── 4. 提取类型 / 位宽 / 种类 ───────────────────────────────
    if hasattr(symbol, 'type') and symbol.type is not None:
        type_name = str(symbol.type)
        bit_width = (
            symbol.type.bitWidth
            if hasattr(symbol.type, 'bitWidth')
            else 0
        )
    else:
        type_name = '<unknown>'
        bit_width = 0

    kind_label = KIND_LABELS.get(
        symbol.kind,
        str(symbol.kind).replace('SymbolKind.', '').lower()
    )

    return {
        'name': var_name,
        'type_name': type_name,
        'bit_width': bit_width,
        'kind': kind_label,
        'hierarchical_path': var_path,
        'instance_path': inst_path,
    }


# ==============================================================================
# CLI
# ==============================================================================

def main():
    """CLI 入口：解析参数、构建层次、查找变量、打印结果。"""
    if len(sys.argv) >= 3:
        filelist_path = sys.argv[1]
        var_path = sys.argv[2]
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filelist_path = os.path.join(
            script_dir, '..', 'test', 'with_instance', 'filelist.f'
        )
        # 默认示例路径
        var_path = 'alu_system.u_core.add_sum'

    # 解析 filelist 并构建层次
    sv_files = parse_filelist(filelist_path)
    if not sv_files:
        print("{}")
        return

    hierarchy = extract_hierarchy(sv_files)

    # 查找变量
    try:
        result = find_hierarch_var(hierarchy, var_path)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    # 打印结果
    print(f"层次路径:   {result['hierarchical_path']}")
    print(f"实例路径:   {result['instance_path']}")
    print(f"变量名:     {result['name']}")
    print(f"类型:       {result['type_name']}")
    print(f"位宽:       {result['bit_width']}")
    print(f"符号种类:   {result['kind']}")


if __name__ == "__main__":
    main()
