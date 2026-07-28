#!/usr/bin/env python3
"""
trace_var.py - 追踪 SystemVerilog 变量的赋值位置并扫描相关变量

功能：
  1. 输入层次变量路径（如 alu_system.u_core.add_b_mux）
  2. 找到该变量被赋值的完整 always 块或 assign 语句
  3. 扫描块内所有变量，排除仅位于赋值符号左边的变量
  4. 输出 JSON（变量信息 + 赋值块源文本 + 相关变量列表）

全程使用 AST（elaborated symbol tree）做逻辑分析，
仅在提取源文本时通过 .syntax 链回 CST。

用法（程序化调用）：
  from hierarchy import parse_filelist, extract_hierarchy
  from trace_var import trace_variable

  result = trace_variable('filelist.f', 'alu_system.u_core.add_b_mux')

用法（CLI）：
  python trace_var.py <filelist_path> <var_path>
  python trace_var.py ../test/with_instance/filelist.f alu_system.u_core.add_b_mux
"""

import sys
import os
import json
from collections import Counter
from pyslang import ast

# 导入现有模块的公开函数
from hierarchy import parse_filelist, extract_hierarchy
from hierarchy_var import find_hierarch_var, KIND_LABELS


# ── 过程块类型映射：ProceduralBlockKind → 字符串 ────────────────────

PROCEDURE_KIND_MAP = {
    ast.ProceduralBlockKind.AlwaysComb:  'always_comb',
    ast.ProceduralBlockKind.AlwaysFF:    'always_ff',
    ast.ProceduralBlockKind.AlwaysLatch: 'always_latch',
    ast.ProceduralBlockKind.Always:      'always',
    ast.ProceduralBlockKind.Initial:     'initial',
    ast.ProceduralBlockKind.Final:       'final',
}


# ==============================================================================
# 公开 API
# ==============================================================================

def trace_variable(filelist_path, var_path):
    """
    追踪变量的赋值位置，扫描赋值块内相关变量，返回结构化结果。

    Args:
        filelist_path: .f 文件路径
        var_path:      层次变量路径，如 "alu_system.u_core.add_b_mux"

    Returns:
        dict: {variable, assignment, related_variables}

    Raises:
        ValueError: 文件列表无效、路径不存在、变量未找到时
        RuntimeError: 变量在模块中找不到赋值时
    """
    # ── 1. 解析文件列表 & 构建层次 ──────────────────────────────────
    sv_files = parse_filelist(filelist_path)
    if not sv_files:
        raise ValueError(f"文件列表为空: {filelist_path}")

    hierarchy = extract_hierarchy(sv_files)
    if not hierarchy:
        raise ValueError("未找到任何 SystemVerilog 模块")

    # ── 2. 编译获取 SourceManager ────────────────────────────────────
    comp, sm = _build_compilation_for_source(sv_files)

    # ── 3. 查找目标变量 ─────────────────────────────────────────────
    var_info = find_hierarch_var(hierarchy, var_path)

    # ── 4. 获取变量所在模块的 InstanceBodySymbol ─────────────────────
    inst_path = var_info['instance_path']
    entry = hierarchy.get(inst_path)
    if entry is None:
        raise ValueError(f"实例路径不在层次中: {inst_path}")
    body = entry['ast']  # InstanceBodySymbol

    # ── 5. 找到赋值所在的 AST 块 ─────────────────────────────────────
    target_ci = body.containingInstance  # 用于过滤子实例块
    var_name = var_info['name']
    block_ast, block_type = _find_containing_block_ast(body, var_name, target_ci)

    # ── 6. 处理端口连接驱动的情况 ───────────────────────────────────
    if block_ast is None:
        driving_inst = _find_driving_instance(body, var_name, target_ci)
        if driving_inst is not None:
            source_info = _get_hierarchy_instantiation_source(driving_inst, sm)
            output_symbols = _collect_output_port_variables(driving_inst)
            return _build_port_result(var_info, source_info, output_symbols)
        raise RuntimeError(
            f"变量 '{var_name}' 在 '{inst_path}' 中未找到 always 块或 assign 赋值"
        )

    # ── 7. 提取源文本 ────────────────────────────────────────────────
    source_info = _extract_source_from_ast(block_ast, sm)

    # ── 8. 扫描块内相关变量 ─────────────────────────────────────────
    included_symbols = _scan_block_variables_ast(block_ast)

    # ── 9. 组装结果 ──────────────────────────────────────────────────
    return _build_result(var_info, block_type, source_info, included_symbols)


# ==============================================================================
# 内部函数：编译
# ==============================================================================

def _build_compilation_for_source(sv_files):
    """
    为源文本提取单独构建 Compilation（与 hierarchy 的是独立的）。

    Args:
        sv_files: SV 文件绝对路径列表

    Returns:
        tuple: (comp, sourceManager)
    """
    comp = ast.Compilation()
    for f in sv_files:
        comp.addSyntaxTree(__import__('pyslang', fromlist=['syntax']).syntax.SyntaxTree.fromFile(f))
    return comp, comp.sourceManager


# ==============================================================================
# 内部函数：查找赋值块（AST）
# ==============================================================================

def _find_containing_block_ast(body, var_name, target_ci):
    """
    用 AST visit 遍历 body，找到包含 var_name 赋值的块。
    使用 parentScope.containingInstance 过滤，只查当前模块的直接块，
    不穿透到子模块实例。

    Args:
        body:       InstanceBodySymbol
        var_name:   目标变量名
        target_ci:  body.containingInstance，用于过滤直接块

    Returns:
        tuple: (ast_symbol, block_type_str) 或 (None, None)
    """
    result = [None]  # closure 可变容器

    def check_block(sym):
        if result[0] is not None:
            return

        # 只查 ProcedureBlock 和 ContinuousAssign
        if sym.kind not in (ast.SymbolKind.ProceduralBlock,
                            ast.SymbolKind.ContinuousAssign):
            return

        # 过滤子模块实例中的块：只保留本模块的直接块
        parent = sym.parentScope
        if hasattr(parent, 'containingInstance'):
            if parent.containingInstance is not target_ci:
                return

        # 检查块内是否有目标变量出现在赋值 LHS
        found = False

        def check_assign(node):
            nonlocal found
            if found:
                return
            if node.kind == ast.ExpressionKind.Assignment:
                left = node.left if hasattr(node, 'left') else None
                if left is not None and left.kind == ast.ExpressionKind.NamedValue:
                    sym_ref = left.symbol if hasattr(left, 'symbol') else None
                    if sym_ref is not None and sym_ref.name == var_name:
                        found = True

        sym.visit(check_assign)

        if found:
            result[0] = sym

    body.visit(check_block)

    if result[0] is None:
        return (None, None)

    block_type = _classify_block_ast(result[0])
    return (result[0], block_type)


def _classify_block_ast(ast_symbol):
    """
    判定 AST 块的类型字符串。

    Args:
        ast_symbol: ProceduralBlock 或 ContinuousAssign 的 AST 符号

    Returns:
        str: 块类型标签
    """
    if ast_symbol.kind == ast.SymbolKind.ProceduralBlock:
        return PROCEDURE_KIND_MAP.get(
            ast_symbol.procedureKind,
            str(ast_symbol.procedureKind).lower()
        )
    elif ast_symbol.kind == ast.SymbolKind.ContinuousAssign:
        return 'continuous_assign'
    else:
        return str(ast_symbol.kind).replace('SymbolKind.', '').lower()


# ==============================================================================
# 内部函数：扫描块内变量（AST）
# ==============================================================================

def _scan_block_variables_ast(ast_symbol):
    """
    用 AST visit 扫描块内所有变量引用，排除仅出现在赋值 LHS 的变量。

    算法：
      1. 遍历所有 ExpressionKind.Assignment → 记录 .left 对应的 symbol（LHS）
      2. 遍历所有 ExpressionKind.NamedValue → 记录 .symbol（所有引用）
      3. 用 Counter 比较：若 symbol 在 LHS 出现次数 == 总出现次数，
         则该 symbol 仅被赋值（从未被读取），排除。

    Args:
        ast_symbol: ProceduralBlock 或 ContinuousAssign 的 AST 符号

    Returns:
        set: 被读取的 AST Symbol 对象集合（VariableSymbol/NetSymbol/...）
    """
    lhs_symbols = []
    all_symbols = []

    def collect(node):
        # 赋值表达式 → .left 是 LHS
        if node.kind == ast.ExpressionKind.Assignment:
            left = node.left if hasattr(node, 'left') else None
            if left is not None and left.kind == ast.ExpressionKind.NamedValue:
                s = left.symbol if hasattr(left, 'symbol') else None
                if s is not None:
                    lhs_symbols.append(s)

        # 变量引用（含 LHS 和 RHS/条件中的引用）
        if node.kind == ast.ExpressionKind.NamedValue:
            s = node.symbol if hasattr(node, 'symbol') else None
            if s is not None:
                all_symbols.append(s)

    ast_symbol.visit(collect)

    # 计数比较：排除仅 LHS 的变量
    lhs_count = Counter(id(s) for s in lhs_symbols)
    all_count = Counter(id(s) for s in all_symbols)

    included = set()
    for s in all_symbols:
        if all_count[id(s)] > lhs_count.get(id(s), 0):
            included.add(s)

    return included


# ==============================================================================
# 内部函数：源文本提取（通过 .syntax 链回 CST）
# ==============================================================================

def _extract_source_from_ast(ast_symbol, sm):
    """
    通过 ast_symbol.syntax.sourceRange 获取源文本和行号。

    Args:
        ast_symbol: AST 块符号
        sm:         SourceManager

    Returns:
        dict: {source_text, file, start_line, end_line}
    """
    cst_node = ast_symbol.syntax
    sr = cst_node.sourceRange

    start_line = sm.getLineNumber(sr.start)
    end_line = sm.getLineNumber(sr.end)

    # 文件路径
    try:
        filepath = str(sm.getFullPath(sr.start.buffer))
    except Exception:
        filepath = sm.getFileName(sr.start) or '<unknown>'

    # 读取源文本
    source_text = ''
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            lines = f.readlines()
        # 行号是 1-indexed
        extracted = lines[start_line - 1:end_line]
        source_text = ''.join(extracted).rstrip('\n')

    return {
        'source_text': source_text,
        'file': filepath,
        'start_line': start_line,
        'end_line': end_line,
    }


# ==============================================================================
# 内部函数：端口连接驱动检测
# ==============================================================================

def _find_driving_instance(body, var_name, target_ci):
    """
    查找输出端口连接中包含目标变量的子模块实例。

    遍历 body 的直接子实例，检查每个输出端口的连接表达式，
    找到包含 var_name 的实例即返回。

    Args:
        body:      InstanceBodySymbol（目标变量所在模块的 AST 体）
        var_name:  目标变量名
        target_ci: body.containingInstance，用于过滤直接子实例

    Returns:
        InstanceSymbol 或 None
    """
    result = [None]

    def check_instance(sym):
        if result[0] is not None:
            return
        if sym.kind != ast.SymbolKind.Instance:
            return

        # 只查当前模块的直接子实例（不穿透到更深层次）
        parent = sym.parentScope
        if hasattr(parent, 'containingInstance'):
            if parent.containingInstance is not target_ci:
                return

        # 遍历端口连接，检查输出端口连接表达式
        for conn in sym.portConnections:
            port = conn.port
            if port is None or port.direction != ast.ArgumentDirection.Out:
                continue

            expr = conn.expression if hasattr(conn, 'expression') else None
            if expr is None:
                continue

            # 在表达式中查找目标变量
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
                result[0] = sym
                return

    body.visit(check_instance)
    return result[0]


def _get_hierarchy_instantiation_source(inst_ast, sm):
    """
    提取实例化语句的完整源文本和位置信息。

    从 AST InstanceSymbol 的 .syntax.parent 获取 HierarchyInstantiation CST 节点，
    该节点对应完整的实例化语句（如 'adder_8bit u_adder (...);'）。

    Args:
        inst_ast: InstanceSymbol（AST 实例符号）
        sm:       SourceManager

    Returns:
        dict: {source_text, file, start_line, end_line, instance_name, definition_name}
    """
    cst_node = inst_ast.syntax  # HierarchicalInstance CST
    # 父节点是 HierarchyInstantiation，包含完整实例化语句
    hier_inst_cst = cst_node.parent if hasattr(cst_node, 'parent') else None
    if hier_inst_cst is None:
        # 回退：使用 inst_ast.syntax 自身
        hier_inst_cst = cst_node

    sr = hier_inst_cst.sourceRange
    start_line = sm.getLineNumber(sr.start)
    end_line = sm.getLineNumber(sr.end)

    # 文件路径
    try:
        filepath = str(sm.getFullPath(sr.start.buffer))
    except Exception:
        filepath = sm.getFileName(sr.start) or '<unknown>'

    # 读取源文本
    source_text = ''
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            lines = f.readlines()
        source_text = ''.join(lines[start_line - 1:end_line]).rstrip('\n')

    return {
        'source_text': source_text,
        'file': filepath,
        'start_line': start_line,
        'end_line': end_line,
        'instance_name': inst_ast.name,
        'definition_name': inst_ast.definition.name if hasattr(inst_ast, 'definition') else '?',
    }


def _collect_output_port_variables(inst_ast):
    """
    收集实例所有输出端口连接的变量。

    遍历 portConnections，筛选 direction == Out 的端口，
    从连接表达式（ExpressionKind.Assignment）的 .left 提取被驱动的变量。

    Args:
        inst_ast: InstanceSymbol

    Returns:
        list[Symbol]: 输出端口连接的 AST Symbol 列表（可直接传给 _build_variable_info）
    """
    output_symbols = []

    for conn in inst_ast.portConnections:
        port = conn.port
        if port is None or port.direction != ast.ArgumentDirection.Out:
            continue

        expr = conn.expression if hasattr(conn, 'expression') else None
        if expr is None:
            continue

        # 输出端口连接表达式是 Assignment，.left 为被驱动的变量
        if expr.kind == ast.ExpressionKind.Assignment:
            left = expr.left if hasattr(expr, 'left') else None
            if left is not None and left.kind == ast.ExpressionKind.NamedValue:
                s = left.symbol if hasattr(left, 'symbol') else None
                if s is not None:
                    output_symbols.append(s)

    return output_symbols


# ==============================================================================
# 内部函数：构建输出
# ==============================================================================

def _build_variable_info(symbol):
    """
    从 AST Symbol 提取变量信息字典。

    Args:
        symbol: VariableSymbol / NetSymbol / ParameterSymbol 等

    Returns:
        dict: {name, hierarchical_path, bit_width, type_name, kind}
    """
    name = symbol.name if hasattr(symbol, 'name') else '<unknown>'
    path = symbol.hierarchicalPath if hasattr(symbol, 'hierarchicalPath') else name

    bit_width = 0
    type_name = '<unknown>'
    if hasattr(symbol, 'type') and symbol.type is not None:
        type_name = str(symbol.type)
        if hasattr(symbol.type, 'bitWidth'):
            bit_width = symbol.type.bitWidth

    kind = KIND_LABELS.get(
        symbol.kind,
        str(symbol.kind).replace('SymbolKind.', '').lower()
    )

    return {
        'name': name,
        'hierarchical_path': path,
        'bit_width': bit_width,
        'type_name': type_name,
        'kind': kind,
    }


def _build_result(var_info, block_type, source_info, included_symbols):
    """组装完整的追踪结果字典。"""
    related = [_build_variable_info(s) for s in included_symbols]

    return {
        'variable': {
            'name': var_info['name'],
            'hierarchical_path': var_info['hierarchical_path'],
            'bit_width': var_info['bit_width'],
            'type_name': var_info['type_name'],
            'kind': var_info['kind'],
        },
        'assignment': {
            'type': block_type,
            'source_text': source_info['source_text'],
            'file': source_info['file'],
            'start_line': source_info['start_line'],
            'end_line': source_info['end_line'],
        },
        'related_variables': related,
    }


def _build_port_result(var_info, source_info, output_symbols):
    """
    组装端口连接驱动的结果字典。

    Args:
        var_info:       find_hierarch_var 返回的变量信息
        source_info:    _get_hierarchy_instantiation_source 返回的源文本信息
        output_symbols: _collect_output_port_variables 返回的输出端口变量列表

    Returns:
        dict: 完整的追踪结果
    """
    related = [_build_variable_info(s) for s in output_symbols]

    return {
        'variable': {
            'name': var_info['name'],
            'hierarchical_path': var_info['hierarchical_path'],
            'bit_width': var_info['bit_width'],
            'type_name': var_info['type_name'],
            'kind': var_info['kind'],
        },
        'assignment': {
            'type': 'port_connection',
            'source_text': source_info['source_text'],
            'file': source_info['file'],
            'start_line': source_info['start_line'],
            'end_line': source_info['end_line'],
            'instance_name': source_info['instance_name'],
            'definition_name': source_info['definition_name'],
        },
        'related_variables': related,
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
        var_path = 'alu_system.u_core.add_b_mux'

    try:
        result = trace_variable(filelist_path, var_path)
    except (ValueError, RuntimeError) as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
