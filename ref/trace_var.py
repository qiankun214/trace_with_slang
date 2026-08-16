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


# ── 表达式匹配辅助函数 ──────────────────────────────────────────

def _match_variable(left, var_segments):
    """判断 LHS 表达式是否匹配目标变量/字段路径。

    支持两种赋值模式：
      - 整 struct 赋值: NamedValue LHS，变量名匹配 var_segments[0]
      - 字段赋值: MemberAccess LHS，完整链匹配 var_segments

    Args:
        left:          赋值左侧 Expression 节点
        var_segments:  变量/字段路径段列表，如 ['cfg_reg'] 或 ['cfg_reg', 'baud', 'div']

    Returns:
        bool: 是否匹配
    """
    # 情况1: NamedValue (整 struct 赋值 cfg_reg <= ...)
    if left.kind == ast.ExpressionKind.NamedValue:
        sym_ref = left.symbol if hasattr(left, 'symbol') else None
        if sym_ref is not None:
            return sym_ref.name == var_segments[0]

    # 情况2: MemberAccess (字段赋值 cfg_reg.baud.div <= ...)
    if left.kind == ast.ExpressionKind.MemberAccess:
        chain_parts = []
        curr = left
        while curr.kind == ast.ExpressionKind.MemberAccess:
            chain_parts.append(curr.member.name)
            curr = curr.value
        # curr 现在是 NamedValueExpression (底层的基变量)
        if hasattr(curr, 'symbol') and curr.symbol is not None:
            chain_parts.append(curr.symbol.name)
        else:
            return False
        chain_parts.reverse()  # ['cfg_reg', 'baud', 'div']
        # 整 struct 追踪 (如 status_pack)：任意字段赋值都算驱动
        # 场景: status_pack 只由字段级 assign 驱动，无整 struct 赋值
        if len(var_segments) == 1:
            return chain_parts[0] == var_segments[0]
        return chain_parts == list(var_segments)

    return False


def collect_member_chain(expr):
    """从 MemberAccess 或 NamedValue 表达式收集所有 Symbol。

    对于 MemberAccess 链 (如 cfg_reg.baud.div)，收集链上所有 FieldSymbol 和底层
    VariableSymbol。对于 NamedValue，直接收集其 .symbol。

    Args:
        expr: Expression 节点 (MemberAccess 或 NamedValue 等)

    Returns:
        list[Symbol]: 表达式链上的所有符号
    """
    symbols = []
    if expr.kind == ast.ExpressionKind.MemberAccess:
        curr = expr
        while curr.kind == ast.ExpressionKind.MemberAccess:
            symbols.append(curr.member)  # FieldSymbol
            curr = curr.value
        # 底层基变量
        if hasattr(curr, 'symbol') and curr.symbol is not None:
            symbols.append(curr.symbol)
    elif expr.kind == ast.ExpressionKind.NamedValue:
        s = expr.symbol if hasattr(expr, 'symbol') else None
        if s is not None:
            symbols.append(s)
    return symbols


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
    member_path = var_info.get('member_path', [var_info['name']])

    # ── 4. 获取变量所在模块的 InstanceBodySymbol ─────────────────────
    inst_path = var_info['instance_path']
    entry = hierarchy.get(inst_path)
    if entry is None:
        raise ValueError(f"实例路径不在层次中: {inst_path}")
    body = entry['ast']  # InstanceBodySymbol

    # ── 5. 找到赋值所在的 AST 块 ─────────────────────────────────────
    target_ci = body.containingInstance  # 用于过滤子实例块
    var_name = var_info['name']
    block_ast, block_type, all_blocks = _find_containing_block_ast(
        body, member_path, target_ci
    )

    # ── 6. 处理端口连接驱动的情况 ───────────────────────────────────
    if block_ast is None:
        driving_inst = _find_driving_instance(body, member_path, target_ci)
        if driving_inst is not None:
            source_info = _get_hierarchy_instantiation_source(driving_inst, sm)
            output_symbols = _collect_output_port_variables(driving_inst, member_path)
            return _build_port_result(var_info, source_info, output_symbols)
        # 输入端口：变量由父模块的实例端口连接驱动。
        # 赋值位置即实例化语句（port_connection），驱动信号是父模块信号，
        # 不属于赋值块内读取的变量 → related_variables 为空
        input_info = _find_input_port_connection(body, member_path)
        if input_info is not None:
            source_info = _get_hierarchy_instantiation_source(input_info['instance_ast'], sm)
            return _build_port_result(var_info, source_info, [])
        # 顶层输入端口等无父模块驱动：若变量在模块内被读取，
        # 报告消费位置（如 fifo_level_i 打包进 status_pack 的 assign）
        reading_blocks = _find_reading_blocks_ast(body, member_path, target_ci)
        if reading_blocks:
            block_ast = reading_blocks[0]
            block_type = _classify_block_ast(block_ast)
            source_info = _extract_source_from_ast(block_ast, sm)
            if len(reading_blocks) > 1:
                merged = _merge_block_source_text(reading_blocks, sm)
                if merged is not None:
                    source_info = merged
            included_symbols = set()
            path_overrides = {}
            for blk in reading_blocks:
                syms, paths = _scan_block_variables_ast(blk)
                included_symbols |= syms
                path_overrides.update(paths)
            return _build_result(
                var_info, block_type, source_info, included_symbols, path_overrides
            )
        raise RuntimeError(
            f"变量 '{var_name}' 在 '{inst_path}' 中未找到 always 块或 assign 赋值"
        )

    # ── 7. 提取源文本 ────────────────────────────────────────────────
    source_info = _extract_source_from_ast(block_ast, sm)
    # 整 struct 由多个连续字段 assign 驱动时，合并源文本跨度
    if len(all_blocks) > 1:
        merged = _merge_block_source_text(all_blocks, sm)
        if merged is not None:
            source_info = merged

    # ── 8. 扫描块内相关变量（合并所有匹配块的 RHS 读取） ────────────
    included_symbols = set()
    path_overrides = {}
    for blk in all_blocks:
        syms, paths = _scan_block_variables_ast(blk)
        included_symbols |= syms
        path_overrides.update(paths)

    # ── 9. 组装结果 ──────────────────────────────────────────────────
    return _build_result(
        var_info, block_type, source_info, included_symbols, path_overrides
    )


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

def _find_containing_block_ast(body, var_segments, target_ci):
    """
    用 AST visit 遍历 body，找到包含目标变量/字段赋值的块。
    使用 parentScope.containingInstance 过滤，只查当前模块的直接块，
    不穿透到子模块实例。

    支持两种赋值模式：
      - 整 struct/变量赋值: NamedValue LHS，变量名匹配 var_segments[0]
      - 字段赋值: MemberAccess LHS，完整链匹配 var_segments
        （整 struct 追踪时，任意字段赋值都算驱动）

    整 struct 可能由多个字段赋值块共同驱动（如 status_pack 的 4 条
    assign），因此收集全部匹配块，由调用方合并 related 变量与源文本。

    Args:
        body:          InstanceBodySymbol
        var_segments:  变量/字段路径段列表，如 ['cfg_reg'] 或 ['cfg_reg', 'baud', 'div']
        target_ci:     body.containingInstance，用于过滤直接块

    Returns:
        tuple: (first_ast, block_type_str, all_matching) 或 (None, None, [])
    """
    matching = []

    def check_block(sym):
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
                if left is not None and _match_variable(left, var_segments):
                    found = True

        sym.visit(check_assign)

        if found:
            matching.append(sym)

    body.visit(check_block)

    if not matching:
        return (None, None, [])

    first = matching[0]
    block_type = _classify_block_ast(first)
    return (first, block_type, matching)


def _find_reading_blocks_ast(body, var_segments, target_ci):
    """
    用 AST visit 遍历 body，找到读取目标变量（RHS/条件位置）的块。

    用于无 LHS 赋值、也无父模块端口连接驱动的变量（如顶层输入端口
    fifo_level_i，被 assign status_pack.fifo_level = fifo_level_i 读取），
    报告其消费位置。

    支持 NamedValue 和 MemberAccess（struct 字段访问）两种表达式。

    Args:
        body:          InstanceBodySymbol
        var_segments:  变量/字段路径段列表，如 ['fifo_level_i']
        target_ci:     body.containingInstance，用于过滤直接块

    Returns:
        list[ast Symbol]: 读取目标变量的块列表
    """
    matching = []

    def check_block(sym):
        # 只查 ProcedureBlock 和 ContinuousAssign
        if sym.kind not in (ast.SymbolKind.ProceduralBlock,
                            ast.SymbolKind.ContinuousAssign):
            return

        # 过滤子模块实例中的块：只保留本模块的直接块
        parent = sym.parentScope
        if hasattr(parent, 'containingInstance'):
            if parent.containingInstance is not target_ci:
                return

        # 检查块内是否有目标变量在 RHS/条件位置被读取
        found = False

        def check_ref(node):
            nonlocal found
            if found:
                return
            # 简单变量引用
            if node.kind == ast.ExpressionKind.NamedValue:
                s = node.symbol if hasattr(node, 'symbol') else None
                if s is not None and s.name == var_segments[0]:
                    found = True
            # struct 字段访问引用
            elif node.kind == ast.ExpressionKind.MemberAccess:
                if _match_variable(node, var_segments):
                    found = True

        sym.visit(check_ref)

        if found:
            matching.append(sym)

    body.visit(check_block)
    return matching


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

    支持 NamedValue 和 MemberAccess（struct 字段访问）两种表达式。

    计数规则（避免 LHS 基变量/中间字段重复计数）：
      - LHS：collect_member_chain 收集整链符号（字段赋值即赋值了整 struct）
      - 引用：每个 MemberAccess 节点只计其直接成员 .member；
        链底基变量的 NamedValue 子节点跳过计数（相关变量只报字段，
        不报基变量——读取 cfg_reg.baud 即读取整个 struct 的字段 baud）
      - 用 Counter 比较：若 symbol 在 LHS 出现次数 == 总出现次数，
        则该 symbol 仅被赋值（从未被读取），排除。

    Args:
        ast_symbol: ProceduralBlock 或 ContinuousAssign 的 AST 符号

    Returns:
        tuple: (set, dict)
            - set: 被读取的 AST Symbol 对象集合
            - dict: {id(symbol): 完整字段访问路径}，如
              {id(baud): 'csr_system.u_regfile.cfg_reg.baud'}
              （字段符号自身的 hierarchicalPath 指向类型定义处，
                如 'csr_pkg.baud'，需修正为实例中的完整访问路径）
    """
    lhs_symbols = []
    all_symbols = []
    member_base_ids = set()  # MemberAccess 链底基变量 symbol id（不直接计入）
    member_paths = {}        # id(member_symbol) -> 完整访问路径

    def collect(node):
        # 赋值表达式 → .left 是 LHS（含 NamedValue 和 MemberAccess）
        if node.kind == ast.ExpressionKind.Assignment:
            left = node.left if hasattr(node, 'left') else None
            if left is not None:
                lhs_symbols.extend(collect_member_chain(left))

        # 简单变量引用（含 LHS 和 RHS/条件中的引用）。
        # 若为 MemberAccess 链底基变量则跳过——由 MemberAccess 分支统一处理
        if node.kind == ast.ExpressionKind.NamedValue:
            s = node.symbol if hasattr(node, 'symbol') else None
            if s is not None and id(s) not in member_base_ids:
                all_symbols.append(s)

        # struct 字段访问：只计本层直接成员，并记录完整访问路径
        if node.kind == ast.ExpressionKind.MemberAccess:
            member = node.member if hasattr(node, 'member') else None
            if member is not None:
                all_symbols.append(member)
                member_paths[id(member)] = _member_full_path(node)
            # 链底基变量：标记跳过其 NamedValue 计数
            base = node.value
            while base is not None and base.kind == ast.ExpressionKind.MemberAccess:
                base = base.value
            if base is not None and base.kind == ast.ExpressionKind.NamedValue:
                bs = base.symbol if hasattr(base, 'symbol') else None
                if bs is not None:
                    member_base_ids.add(id(bs))

    ast_symbol.visit(collect)

    # 计数比较：排除仅 LHS 的变量
    lhs_count = Counter(id(s) for s in lhs_symbols)
    all_count = Counter(id(s) for s in all_symbols)

    included = set()
    for s in all_symbols:
        if all_count[id(s)] > lhs_count.get(id(s), 0):
            included.add(s)

    return included, member_paths


def _member_full_path(node):
    """
    构造 MemberAccess 节点的完整访问路径。

    如 cfg_reg.baud → 'csr_system.u_regfile.cfg_reg.baud'；
    嵌套如 cfg_reg.baud.div → 'csr_system.u_regfile.cfg_reg.baud.div'。

    Args:
        node: MemberAccess 表达式节点

    Returns:
        str: 完整的层次字段访问路径
    """
    parts = []
    curr = node
    while curr is not None and curr.kind == ast.ExpressionKind.MemberAccess:
        m = curr.member if hasattr(curr, 'member') else None
        if m is not None:
            parts.append(m.name)
        curr = curr.value
    parts.reverse()

    base = ''
    if curr is not None and hasattr(curr, 'symbol') and curr.symbol is not None:
        sym = curr.symbol
        if hasattr(sym, 'hierarchicalPath'):
            base = sym.hierarchicalPath
        elif hasattr(sym, 'name'):
            base = sym.name

    if base:
        return base + '.' + '.'.join(parts)
    return '.'.join(parts)


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


def _merge_block_source_text(blocks, sm):
    """
    合并同一文件内连续行上的多个赋值块的源文本。

    整 struct 可能由多条连续字段 assign 驱动（如 status_pack 的 4 条
    assign），单块只显示第一条。若所有匹配块都是 ContinuousAssign 且
    位于同一文件、行号连续，则合并为一个源跨度；否则返回 None。

    Args:
        blocks: list[ast Symbol]，全部匹配的赋值块
        sm:     SourceManager

    Returns:
        dict 或 None: {source_text, file, start_line, end_line}
    """
    ranges = []
    for blk in blocks:
        if blk.kind != ast.SymbolKind.ContinuousAssign:
            return None
        cst = blk.syntax
        sr = cst.sourceRange
        try:
            filepath = str(sm.getFullPath(sr.start.buffer))
        except Exception:
            return None
        ranges.append({
            'file': filepath,
            'start_line': sm.getLineNumber(sr.start),
            'end_line': sm.getLineNumber(sr.end),
        })

    ranges.sort(key=lambda r: r['start_line'])
    file = ranges[0]['file']
    for i in range(1, len(ranges)):
        prev_r, cur_r = ranges[i - 1], ranges[i]
        if cur_r['file'] != file or cur_r['start_line'] != prev_r['end_line'] + 1:
            return None

    start_line = ranges[0]['start_line']
    end_line = ranges[-1]['end_line']

    source_text = ''
    if os.path.exists(file):
        with open(file, 'r') as f:
            lines = f.readlines()
        source_text = ''.join(lines[start_line - 1:end_line]).rstrip('\n')

    return {
        'source_text': source_text,
        'file': file,
        'start_line': start_line,
        'end_line': end_line,
    }


# ==============================================================================
# 内部函数：端口连接驱动检测
# ==============================================================================

def _find_driving_instance(body, var_segments, target_ci):
    """
    查找输出端口连接中包含目标变量的子模块实例。

    遍历 body 的直接子实例，检查每个输出端口的连接表达式，
    找到包含目标变量的实例即返回。支持 struct 端口字段追踪。

    Args:
        body:          InstanceBodySymbol（目标变量所在模块的 AST 体）
        var_segments:  变量/字段路径段列表，如 ['cfg_o'] 或 ['cfg_o', 'div']
        target_ci:     body.containingInstance，用于过滤直接子实例

    Returns:
        InstanceSymbol 或 None
    """
    result = [None]
    base_name = var_segments[0]  # 端口连接的基变量名

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

            # 在表达式中查找目标变量（匹配基变量名）
            found = False

            def check_expr(node):
                nonlocal found
                if found:
                    return
                if node.kind == ast.ExpressionKind.NamedValue:
                    s = node.symbol if hasattr(node, 'symbol') else None
                    if s is not None and s.name == base_name:
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


def _collect_output_port_variables(inst_ast, var_segments):
    """
    收集驱动目标变量的子模块输出端口。

    只返回连接表达式中包含目标变量的输出端口变量，不返回实例的全部输出端口。
    支持 struct 端口字段追踪。

    Args:
        inst_ast:      InstanceSymbol
        var_segments:  变量/字段路径段列表，如 ['cfg_o'] 或 ['cfg_o', 'div']

    Returns:
        list[Symbol]: 驱动目标变量的端口 AST Symbol 列表
    """
    output_symbols = []
    base_name = var_segments[0]  # 端口连接的基变量名

    for conn in inst_ast.portConnections:
        port = conn.port
        if port is None or port.direction != ast.ArgumentDirection.Out:
            continue

        # 检查连接表达式是否包含目标变量
        expr = conn.expression if hasattr(conn, 'expression') else None
        if expr is None:
            continue

        matches = False
        if expr.kind == ast.ExpressionKind.NamedValue:
            s = expr.symbol if hasattr(expr, 'symbol') else None
            if s is not None and s.name == base_name:
                matches = True
        elif expr.kind == ast.ExpressionKind.Assignment:
            left = expr.left if hasattr(expr, 'left') else None
            if left is not None and left.kind == ast.ExpressionKind.NamedValue:
                s = left.symbol if hasattr(left, 'symbol') else None
                if s is not None and s.name == base_name:
                    matches = True

        if matches:
            port_sym = inst_ast.body.find(port.name)
            if port_sym is not None:
                output_symbols.append(port_sym)

    return output_symbols


def _find_input_port_connection(body, var_segments):
    """
    检查变量是否为输入端口（或其 struct 字段），若是则返回父模块中驱动该端口的信号。

    输入端口的值来自父模块实例化时的端口连接。通过 body.portList 确认
    端口方向为 In，再从 body.containingInstance.portConnections 获取
    连接表达式中的驱动信号。

    支持 struct 端口字段追踪：var_segments[0] 是端口名，后续段是字段路径。
    如 var_segments=['cfg_i','div'] → 检查端口 'cfg_i' 是否为输入端口。

    Args:
        body:          InstanceBodySymbol（目标变量所在模块的 AST 体）
        var_segments:  变量/字段路径段列表，如 ['cfg_i'] 或 ['cfg_i', 'div']

    Returns:
        dict 或 None: {'instance_ast': InstanceSymbol, 'driving_symbol': Symbol}
    """
    port_name = var_segments[0]  # 端口名是基变量名

    # 1. 确认是输入端口
    is_input_port = False
    for port in body.portList:
        if port.name == port_name and port.direction == ast.ArgumentDirection.In:
            is_input_port = True
            break

    if not is_input_port:
        return None

    # 2. 从当前实例的端口连接中找驱动信号
    current_inst = body.containingInstance  # InstanceBodySymbol
    if current_inst is None:
        return None
    # InstanceBodySymbol.parentInstance → InstanceSymbol（含 portConnections）
    inst_sym = current_inst.parentInstance
    if inst_sym is None:
        return None

    for conn in inst_sym.portConnections:
        if conn.port is None or conn.port.name != port_name:
            continue

        expr = conn.expression if hasattr(conn, 'expression') else None
        if expr is None:
            continue

        # 输入端口连接表达式是 NamedValue（如 baud_cfg_wire）
        if expr.kind == ast.ExpressionKind.NamedValue:
            driving_sym = expr.symbol if hasattr(expr, 'symbol') else None
            if driving_sym is not None:
                return {
                    'instance_ast': inst_sym,
                    'driving_symbol': driving_sym,
                }

    return None


# ==============================================================================
# 内部函数：构建输出
# ==============================================================================

def _build_variable_info(symbol, path_override=None):
    """
    从 AST Symbol 提取变量信息字典。

    Args:
        symbol: VariableSymbol / NetSymbol / ParameterSymbol 等
        path_override: 可选，覆盖 hierarchical_path。用于 struct 字段符号
                       （其自身 hierarchicalPath 指向类型定义处，如
                       'csr_pkg.baud'，需用实例中的完整访问路径覆盖）

    Returns:
        dict: {name, hierarchical_path, bit_width, type_name, kind}
    """
    name = symbol.name if hasattr(symbol, 'name') else '<unknown>'
    path = path_override
    if path is None:
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


def _build_result(var_info, block_type, source_info, included_symbols, path_overrides=None):
    """组装完整的追踪结果字典。"""
    related = [
        _build_variable_info(
            s, path_overrides.get(id(s)) if path_overrides else None
        )
        for s in included_symbols
    ]

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
