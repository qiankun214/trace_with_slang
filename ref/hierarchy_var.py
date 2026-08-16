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

    解析 var_path（如 "alu_system.u_core.add_sum" 或
    "csr_system.u_regfile.cfg_reg.baud.div"），在 hierarchy dict
    中查找对应的 InstanceBodySymbol，再用 AST body.find() 解析变量符号。
    支持 struct 字段路径：实例路径之后的剩余段逐级通过 struct type scope 查找。

    Args:
        hierarchy: extract_hierarchy() 返回的 dict[str, dict]，
                   key 为 hierarchicalPath，value 含 'ast' (InstanceBodySymbol)
        var_path:  层次变量路径，点分隔，格式为 <顶层模块>.<实例>.<变量>[.<字段>...]

    Returns:
        dict: {name, member_path, type_name, bit_width, kind,
               hierarchical_path, instance_path}

    Raises:
        ValueError: 路径格式错误、实例路径不存在或变量未找到时
    """
    # ── 1. 解析路径：从右向左尝试实例路径匹配 ─────────────────
    segments = var_path.split('.')
    if len(segments) < 2:
        raise ValueError(
            f"层次变量路径至少需要两段 (顶层模块.变量名)，得到: {var_path}"
        )

    # 从最长可能实例路径开始尝试 (至少保留 1 段作为变量/字段名)
    # 只有当剩余段能成功解析时才接受该候选
    inst_path = None
    var_segments = None
    resolved_symbol = None
    first_failed_inst = None  # 记录第一个有层次但解析失败的实例路径
    for i in range(len(segments) - 1, 0, -1):
        candidate_inst = '.'.join(segments[:i])
        if candidate_inst not in hierarchy:
            continue
        # 尝试解析剩余的变量/字段段
        candidate_vars = list(segments[i:])
        body = hierarchy[candidate_inst]['ast']
        sym = body.find(candidate_vars[0])
        # body.find() 可能返回 InstanceSymbol (子模块)，需排除
        if sym is None or sym.kind == ast.SymbolKind.Instance:
            # 仅当剩余段只有变量名（而非中间实例名）时记录"未找到"错误
            if len(candidate_vars) == 1 and first_failed_inst is None:
                first_failed_inst = (candidate_inst, candidate_vars[0])
            continue  # 基变量未找到或匹配到实例名，尝试更短的实例路径
        # 遍历后续字段段
        ok = True
        for field_name in candidate_vars[1:]:
            struct_scope = sym.type
            if hasattr(struct_scope, 'canonicalType') and struct_scope.canonicalType is not None:
                struct_scope = struct_scope.canonicalType
            if struct_scope is None or not hasattr(struct_scope, 'find'):
                ok = False
                break
            sym = struct_scope.find(field_name)
            if sym is None:
                ok = False
                break
        if ok:
            inst_path = candidate_inst
            var_segments = candidate_vars
            resolved_symbol = sym
            break

    if inst_path is None:
        # 区分子错误：有层次但变量未找到 vs 层次路径不存在
        if first_failed_inst is not None:
            failed_inst, failed_var = first_failed_inst
            raise ValueError(f"变量 '{failed_var}' 在 '{failed_inst}' 中未找到")
        raise ValueError(f"层次路径不存在: {var_path}")

    symbol = resolved_symbol
    entry = hierarchy[inst_path]
    body = entry['ast']  # InstanceBodySymbol

    # ── 4. 提取类型 / 位宽 / 种类 ───────────────────────────────
    var_name = var_segments[-1]
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
        'member_path': var_segments,  # ['cfg_reg'] 或 ['cfg_reg', 'baud', 'div']
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
