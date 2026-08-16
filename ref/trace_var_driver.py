#!/usr/bin/env python3
"""
trace_var_driver.py - 追踪 SystemVerilog 变量的下游扇出（fan-out）

功能：
  1. 输入层次变量路径（如 alu_system.opcode）
  2. 找到该变量直接驱动的所有变量（仅一级扇出，不递归传递）
  3. 输出 JSON（变量信息 + 被驱动变量列表）

三类信号的处理方式：
  - 内部变量 / 输入端口：在同模块内追踪（block fan-out + 子模块端口 fan-out）
  - 输出端口：向上追溯到父模块的连接 wire，再在父模块追踪

用法（程序化调用）：
  from hierarchy import parse_filelist, extract_hierarchy
  from hierarchy_var import find_hierarch_var
  from trace_var_driver import trace_var_driver

  result = trace_var_driver('filelist.f', 'alu_system.opcode')

用法（CLI）：
  python trace_var_driver.py <filelist_path> <var_path>
  python trace_var_driver.py ../test/with_instance/filelist.f alu_system.opcode
"""

import sys
import os
import json
from collections import Counter
from pyslang import ast

# 复用已有模块的公开函数
from hierarchy import parse_filelist, extract_hierarchy
from hierarchy_var import find_hierarch_var
from trace_var import _build_variable_info, _match_variable, collect_member_chain as _collect_member_chain


# ==============================================================================
# 公开 API
# ==============================================================================

def trace_var_driver(filelist_path, var_path):
    """
    追踪变量的下游扇出：找到该变量直接驱动的所有变量。

    Args:
        filelist_path: .f 文件路径
        var_path:      层次变量路径，如 "alu_system.opcode"

    Returns:
        dict: {variable, driven_variables, fan_out_count}

    Raises:
        ValueError: 文件列表为空、层次不存在或变量未找到时
    """
    # ── 1. 解析文件列表 & 构建层次 ──────────────────────────────────
    sv_files = parse_filelist(filelist_path)
    if not sv_files:
        raise ValueError(f"文件列表为空: {filelist_path}")

    hierarchy = extract_hierarchy(sv_files)
    if not hierarchy:
        raise ValueError("未找到任何 SystemVerilog 模块")

    # ── 2. 查找目标变量 ─────────────────────────────────────────────
    var_info = find_hierarch_var(hierarchy, var_path)
    inst_path = var_info['instance_path']
    var_name = var_info['name']
    member_path = var_info.get('member_path', [var_name])

    entry = hierarchy.get(inst_path)
    if entry is None:
        raise ValueError(f"实例路径不在层次中: {inst_path}")

    body = entry['ast']  # InstanceBodySymbol

    # ── 3. 判断变量类型，分发到对应的追踪逻辑 ────────────────────────
    is_input, is_output = _is_port(body, var_name)

    if is_output:
        # 情况 3：输出端口 → 回溯父模块
        symbols = _trace_output_port(hierarchy, inst_path, var_name)
    else:
        # 情况 1 / 2：内部变量或输入端口 → 模块内追踪
        symbols = _trace_in_module(body, member_path)

    # ── 4. 组装结果 ──────────────────────────────────────────────────
    driven = [_build_variable_info(s) for s in symbols]
    return _build_result(var_info, driven)


# ==============================================================================
# 内部函数：端口判断
# ==============================================================================

def _is_port(body, var_name):
    """
    判断变量是否为端口，以及端口的输入/输出方向。

    Args:
        body:     InstanceBodySymbol
        var_name: 变量名

    Returns:
        tuple[bool, bool]: (is_input, is_output)
    """
    port = body.findPort(var_name)
    if port is None:
        return False, False

    is_input = port.direction == ast.ArgumentDirection.In
    is_output = port.direction == ast.ArgumentDirection.Out
    return is_input, is_output


# ==============================================================================
# 内部函数：模块内追踪（情况 1 / 2）
# ==============================================================================

def _trace_in_module(body, var_segments):
    """
    在模块内部追踪一个变量的一级扇出。

    两步：
      A. 块扇出：找读取目标变量的块，收集块内所有 LHS 变量
      B. 子模块端口扇出：找由目标变量驱动的子模块输入端口

    Args:
        body:          InstanceBodySymbol
        var_segments:  变量/字段路径段列表，如 ['cfg_reg'] 或 ['cfg_reg', 'baud', 'div']

    Returns:
        list[Symbol]: 被直接驱动的 AST Symbol 列表
    """
    target_ci = body.containingInstance

    symbols = []
    seen = set()  # 用 id() 去重

    # A. 块扇出
    block_driven = _find_block_fanout(body, var_segments, target_ci)
    for s in block_driven:
        if id(s) not in seen:
            seen.add(id(s))
            symbols.append(s)

    # B. 子模块端口扇出（使用 var_segments[0] 作为简单变量名）
    port_driven = _find_input_port_fanout(body, var_segments[0], target_ci)
    for s in port_driven:
        if id(s) not in seen:
            seen.add(id(s))
            symbols.append(s)

    return symbols


# ==============================================================================
# 内部函数：块内扇出扫描
# ==============================================================================

def _find_block_fanout(body, var_segments, target_ci):
    """
    扫描当前模块的 ProceduralBlock 和 ContinuousAssign，找到目标变量
    被读取的块，返回这些块中所有被赋值（LHS）的 Symbol。

    支持 NamedValue 和 MemberAccess（struct 字段访问）两种表达式。
    对于 MemberAccess，收集链上所有符号（基变量 + 中间字段）。

    算法（引用计数平衡法，参考 trace_var._scan_block_variables_ast）：
      1. 遍历 Assignment 节点：记录 .left 链 → LHS 计数。匹配的 LHS 链
         上每个符号（各级 MemberAccess 节点 + 链底基变量子节点）都会在
         引用计数中被 visit 到，故 LHS 侧需按链长同步计入，避免字段
         赋值块被误判为"读取了目标"
      2. 遍历 NamedValue 和 MemberAccess 节点：记录引用计数（仅针对目标变量）
      3. 若目标变量的总引用 > LHS 出现次数 → 说明在 RHS/条件中被读取
      4. 收集该块内所有 LHS Symbol 作为被驱动变量

    Args:
        body:          InstanceBodySymbol
        var_segments:  变量/字段路径段列表，如 ['cfg_reg'] 或 ['cfg_reg', 'baud', 'div']
        target_ci:     body.containingInstance，用于过滤直接块

    Returns:
        list[Symbol]: 被驱动变量 Symbol 列表
    """
    driven = []

    def check_block(sym):
        if sym.kind not in (ast.SymbolKind.ProceduralBlock,
                            ast.SymbolKind.ContinuousAssign):
            return

        # 过滤子模块中的块：只保留本模块的直接块
        parent = sym.parentScope
        if hasattr(parent, 'containingInstance'):
            if parent.containingInstance is not target_ci:
                return

        lhs_syms = set()
        var_lhs_count = 0
        var_total_count = 0

        def collect(node):
            nonlocal var_lhs_count, var_total_count

            # 赋值表达式 → .left 是 LHS（含 NamedValue 和 MemberAccess）
            if node.kind == ast.ExpressionKind.Assignment:
                left = node.left if hasattr(node, 'left') else None
                if left is not None:
                    # 收集 LHS 符号
                    chain = _collect_member_chain(left)
                    for s in chain:
                        lhs_syms.add(s)
                    # 检查是否匹配目标变量
                    if _match_variable(left, var_segments):
                        # LHS 链上每个符号在引用计数中都会被 visit 到
                        # （MemberAccess 节点 + 链底基变量子节点），
                        # 按链长同步计入 LHS 侧
                        var_lhs_count += len(chain)

            # 简单变量引用
            if node.kind == ast.ExpressionKind.NamedValue:
                s = node.symbol if hasattr(node, 'symbol') else None
                if s is not None and s.name == var_segments[0]:
                    var_total_count += 1

            # struct 字段访问引用
            if node.kind == ast.ExpressionKind.MemberAccess:
                if _match_variable(node, var_segments):
                    var_total_count += 1

        sym.visit(collect)

        # 目标变量出现在块的 RHS / 条件中（不仅是 LHS）
        if var_total_count > var_lhs_count:
            driven.extend(lhs_syms)

    body.visit(check_block)
    return driven


# ==============================================================================
# 内部函数：子模块端口扇出扫描
# ==============================================================================

def _find_input_port_fanout(body, var_name, target_ci):
    """
    扫描当前模块的直接子实例，找到由 var_name 驱动的输入端口，
    返回子模块内部对应的变量 Symbol。

    对每个子 InstanceSymbol 的 portConnections，筛选 direction == In 的端口，
    在连接表达式中 visit 查找是否引用了 var_name。若命中，取 port.internalSymbol。

    Args:
        body:      InstanceBodySymbol
        var_name:  目标变量名
        target_ci: body.containingInstance，用于过滤直接子实例

    Returns:
        list[Symbol]: 子模块内部被驱动的 Symbol 列表
    """
    driven = []

    def check_instance(sym):
        if sym.kind != ast.SymbolKind.Instance:
            return

        # 过滤子实例中的更深层实例：只保留本模块的直接子实例
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

            # 在连接表达式中查找 var_name
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


# ==============================================================================
# 内部函数：输出端口向上追溯（情况 3）
# ==============================================================================

def _trace_output_port(hierarchy, inst_path, port_name):
    """
    输出端口向上追溯：在父模块中找到连接该输出端口的 wire，
    再在父模块中追踪该 wire 的扇出。

    Args:
        hierarchy:  extract_hierarchy() 返回的层次字典
        inst_path:  当前模块的层次路径，如 "alu_system.u_core"
        port_name:  输出端口名，如 "result"

    Returns:
        list[Symbol]: 父模块中被驱动变量 Symbol 列表
    """
    # 解析父模块路径和当前实例名
    segments = inst_path.split('.')
    if len(segments) < 2:
        return []  # 顶层模块，无父模块

    parent_inst_path = '.'.join(segments[:-1])
    inst_name = segments[-1]

    parent_entry = hierarchy.get(parent_inst_path)
    if parent_entry is None:
        return []

    parent_body = parent_entry['ast']
    parent_target_ci = parent_body.containingInstance

    # 在父模块中找到当前模块对应的 InstanceSymbol
    result = []

    def find_instance(sym):
        nonlocal result
        if result:
            return
        if sym.kind != ast.SymbolKind.Instance:
            return

        # 过滤：只查父模块的直接子实例，且实例名匹配
        if sym.name != inst_name:
            return
        p = sym.parentScope
        if hasattr(p, 'containingInstance'):
            if p.containingInstance is not parent_target_ci:
                return

        # 找到实例，检查端口连接中对应的输出端口
        for conn in sym.portConnections:
            port = conn.port
            if port is None or port.direction != ast.ArgumentDirection.Out:
                continue
            if port.name != port_name:
                continue

            expr = conn.expression if hasattr(conn, 'expression') else None
            if expr is None:
                continue

            # 输出端口连接表达式为 AssignmentExpression
            # .left 是父模块中被驱动的变量
            if expr.kind == ast.ExpressionKind.Assignment:
                left = expr.left if hasattr(expr, 'left') else None
                if left is not None and left.kind == ast.ExpressionKind.NamedValue:
                    s = left.symbol if hasattr(left, 'symbol') else None
                    if s is not None:
                        # 只返回父模块 wire，不继续往下追
                        # 保持每一级扇出是精确的一跳，不跳过中间层次
                        result = [s]

    parent_body.visit(find_instance)
    return result


# ==============================================================================
# 内部函数：结果组装
# ==============================================================================

def _build_result(var_info, driven_variables):
    """
    组装最终输出字典。

    Args:
        var_info:          find_hierarch_var 返回的变量信息 dict
        driven_variables:  list[dict]（_build_variable_info 的输出）

    Returns:
        dict: {variable, driven_variables, fan_out_count}
    """
    return {
        'variable': {
            'name': var_info['name'],
            'hierarchical_path': var_info['hierarchical_path'],
            'bit_width': var_info['bit_width'],
            'type_name': var_info['type_name'],
            'kind': var_info['kind'],
        },
        'driven_variables': driven_variables,
        'fan_out_count': len(driven_variables),
    }


# ==============================================================================
# CLI
# ==============================================================================

def main():
    """CLI 入口：解析参数、调用追踪、输出 JSON。"""
    if len(sys.argv) >= 3:
        filelist_path = sys.argv[1]
        var_path = sys.argv[2]
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filelist_path = os.path.join(
            script_dir, '..', 'test', 'with_instance', 'filelist.f'
        )
        var_path = 'alu_system.opcode'

    try:
        result = trace_var_driver(filelist_path, var_path)
    except (ValueError, RuntimeError) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
