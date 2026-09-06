"""流程② pyslang 解析与信息提取。

将流程①输出的 `.sv` 文件绝对路径列表一次性编译并提取为**纯数据**解析信息
集合(ParseResult),作为流程③(sqlite 落库)的输入。行为契约见
doc/flow2_design_spec.md;算法原理见 doc/ref.md §3/§5。

实现要点(与 spec §3 子函数规划的差异):
- §6.1 要求每块单遍建边(禁止逐信号遍历全设计),故读取收集采用
  `_collect_reads` 显式递归(最大链语义:MemberAccess 链整体为一次读取,
  不重复计链上前缀),替代规划中逐目标匹配的 `_reads_signal`;
  `_collect_member_chain` 相应返回段名列表(规划为 Symbol 列表),供
  one-pass 路径拼接。
- 新增支撑函数 `_collect_child_instances` / `_resolve_lhs` /
  `_expand_struct_fields` / `_port_conn_syntax` 等。
"""

from loguru import logger
from pyslang import SourceManager, ast, syntax

from datatypes import (
    BlockInfo,
    DepEdge,
    InstanceInfo,
    ParseResult,
    PortInfo,
    SignalInfo,
)


# ── 常量映射 ──────────────────────────────────────────────────────

#: ArgumentDirection → 端口方向字符串(§1.4/§1.5)
_DIRECTION_MAP = {
    ast.ArgumentDirection.In: "input",
    ast.ArgumentDirection.Out: "output",
    ast.ArgumentDirection.InOut: "inout",
    ast.ArgumentDirection.Ref: "ref",
}

#: ProceduralBlockKind → block_type(§1.6)
_PROCEDURE_KIND_MAP = {
    ast.ProceduralBlockKind.AlwaysComb: "always_comb",
    ast.ProceduralBlockKind.AlwaysFF: "always_ff",
    ast.ProceduralBlockKind.AlwaysLatch: "always_latch",
    ast.ProceduralBlockKind.Always: "always",
    ast.ProceduralBlockKind.Initial: "initial",
    ast.ProceduralBlockKind.Final: "final",
}

#: 成员声明符号种类 → 信号 kind(§1.5;genvar/EnumValue 等非信号符号不展开)
_MEMBER_KIND_MAP = {
    ast.SymbolKind.Variable: "variable",
    ast.SymbolKind.Net: "net",
    ast.SymbolKind.Parameter: "parameter",
}

#: 通道 2 门控条件语句种类(§6.1)
_COND_STMT_KINDS = frozenset(
    {
        ast.StatementKind.Conditional,
        ast.StatementKind.Case,
        ast.StatementKind.ForLoop,
        ast.StatementKind.Timed,
    }
)

#: 自增/自减 UnaryOperator(§6.1:隐式读+写操作数,自依赖边)
_INCDEC_OPS = frozenset(
    {
        ast.UnaryOperator.Preincrement,
        ast.UnaryOperator.Postincrement,
        ast.UnaryOperator.Predecrement,
        ast.UnaryOperator.Postdecrement,
    }
)

#: 无子表达式的叶子 ExpressionKind(读取收集中直接跳过)
_LEAF_EXPR_KINDS = frozenset(
    k
    for k in (
        getattr(ast.ExpressionKind, name, None)
        for name in (
            "IntegerLiteral",
            "RealLiteral",
            "StringLiteral",
            "TimeLiteral",
            "NullLiteral",
            "EmptyArgument",
            "TypeReference",
            "UnbasedUnsizedIntegerLiteral",
        )
    )
    if k is not None
)


# ── 公开函数(§1.2) ────────────────────────────────────────────────


def extract_design(sv_files: list[str]) -> ParseResult:
    """一级函数:一次性编译全部文件并提取四组信息(§2 总流程)。

    空列表 → 空 ParseResult(不报错);内部共享一次编译,顺序为
    层次 → 信号 → 块 → 依赖边(§2 顺序要求)。
    """
    if not sv_files:
        return ParseResult([], [], [], [])
    comp, root, sm = _build_compilation(sv_files)
    _report_diagnostics(comp)
    instances = _extract_hierarchy_impl(root, sm)
    signals = _extract_signals_impl(root, sm)
    blocks = _extract_blocks_impl(root, sm)
    dep_edges = _extract_dep_edges_impl(root, sm, blocks, signals)
    return ParseResult(instances, signals, blocks, dep_edges)


def extract_hierarchy(sv_files: list[str]) -> list[InstanceInfo]:
    """只提取实例层次树(独立编译一次;大设计勿混用,见 §3 设计依据)。"""
    if not sv_files:
        return []
    comp, root, sm = _build_compilation(sv_files)
    _report_diagnostics(comp)
    return _extract_hierarchy_impl(root, sm)


def extract_signals(sv_files: list[str]) -> list[SignalInfo]:
    """只提取信号列表(独立编译一次),含 struct 字段展开。"""
    if not sv_files:
        return []
    comp, root, sm = _build_compilation(sv_files)
    _report_diagnostics(comp)
    return _extract_signals_impl(root, sm)


def extract_blocks(sv_files: list[str]) -> list[BlockInfo]:
    """只提取赋值语句块列表(独立编译一次),含 port_connection 块。"""
    if not sv_files:
        return []
    comp, root, sm = _build_compilation(sv_files)
    _report_diagnostics(comp)
    return _extract_blocks_impl(root, sm)


def extract_dep_edges(sv_files: list[str]) -> list[DepEdge]:
    """只提取依赖边列表(独立编译一次;先取信号/块以满足 §2 顺序要求)。"""
    if not sv_files:
        return []
    comp, root, sm = _build_compilation(sv_files)
    _report_diagnostics(comp)
    signals = _extract_signals_impl(root, sm)
    blocks = _extract_blocks_impl(root, sm)
    return _extract_dep_edges_impl(root, sm, blocks, signals)


# ── 编译与诊断(§5 规则 2/3) ────────────────────────────────────────


def _build_compilation(
    sv_files: list[str],
) -> tuple[ast.Compilation, ast.RootSymbol, SourceManager]:
    """单次 Compilation 编译全部文件并 elaborate(§5 规则 2)。

    必须一次性编译全部文件,否则缺失定义的子模块退化为 UninstantiatedDef。
    文件不可读/不存在时由 pyslang 抛出 IOError 直接爆出(§7,禁止过度 try)。
    """
    comp = ast.Compilation()
    for f in sv_files:
        comp.addSyntaxTree(syntax.SyntaxTree.fromFile(f))
    root = comp.getRoot()
    return comp, root, comp.sourceManager


def _report_diagnostics(comp: ast.Compilation) -> None:
    """统计编译诊断并 log(§5 规则 3)。

    单条诊断按 DEBUG 输出;ERROR/WARNING 按计数汇总输出;存在 ERROR 时
    额外告警"错误恢复可能清空过程块,提取结果可能不完整",继续提取。
    """
    diags = comp.getAllDiagnostics()
    errors = [d for d in diags if d.isError()]
    warnings = [d for d in diags if not d.isError()]
    for d in diags:
        logger.debug(f"编译诊断: {d.code} {d.args}")
    if errors:
        logger.error(f"编译诊断: {len(errors)} 条 ERROR")
        logger.warning("编译存在 ERROR,错误恢复可能清空过程块,提取结果可能不完整")
    if warnings:
        logger.warning(f"编译诊断: {len(warnings)} 条 WARNING")


# ── 层次提取(§1.4/§5 规则 4) ───────────────────────────────────────


def _collect_instances(root: ast.RootSymbol) -> list[ast.InstanceSymbol]:
    """visit 收集全部 InstanceSymbol(DFS 前序,§1.4)。

    缺失定义的子模块为 UninstantiatedDef:告警且不进实例树(§7)。
    """
    instances: list[ast.InstanceSymbol] = []

    def collect(sym) -> None:
        if sym.kind == ast.SymbolKind.Instance:
            instances.append(sym)
        elif sym.kind == ast.SymbolKind.UninstantiatedDef:
            logger.warning(f"子模块定义缺失,跳过实例树节点: {getattr(sym, 'name', sym)}")

    for top in root.topInstances:
        top.visit(collect)
    return instances


def _extract_ports(body: ast.InstanceBodySymbol) -> list[PortInfo]:
    """portList → PortInfo 列表(声明序;direction 枚举映射,§1.4)。"""
    ports: list[PortInfo] = []
    for port in body.portList:
        ports.append(
            PortInfo(
                name=port.name,
                direction=_DIRECTION_MAP.get(port.direction, str(port.direction)),
                bit_width=_bit_width(getattr(port, "type", None)),
            )
        )
    return ports


def _extract_hierarchy_impl(
    root: ast.RootSymbol, sm: SourceManager
) -> list[InstanceInfo]:
    """共享编译的层次提取实现(§1.4)。

    file 取模块定义位置(inst.definition.location,非实例化位置);
    depth 由 hierarchicalPath 段数计算。
    """
    instances: list[InstanceInfo] = []
    for inst in _collect_instances(root):
        loc = inst.definition.location
        file = str(sm.getFullPath(loc.buffer)) if loc is not None else ""
        instances.append(
            InstanceInfo(
                path=inst.hierarchicalPath,
                name=inst.name,
                module_name=inst.definition.name,
                depth=len(inst.hierarchicalPath.split(".")),
                file=file,
                ports=_extract_ports(inst.body),
            )
        )
    return instances


# ── 信号提取(§1.5/§5 规则 5/6) ─────────────────────────────────────


def _type_name(t) -> str:
    """Type → 类型名字符串;无类型时 '<unknown>'(§1.5)。"""
    return str(t) if t is not None else "<unknown>"


def _bit_width(t) -> int:
    """Type → 位宽;无类型或无 bitWidth 属性时 0(§1.5)。"""
    if t is None or not hasattr(t, "bitWidth"):
        return 0
    return t.bitWidth


def _location_of(sym, sm: SourceManager) -> tuple[str, int]:
    """符号定义位置 → (文件绝对路径, 行号);无位置时 ('', 0)。"""
    loc = getattr(sym, "location", None)
    if loc is None:
        return "", 0
    return str(sm.getFullPath(loc.buffer)), sm.getLineNumber(loc)


def _decl_names(member) -> list[str]:
    """CST 声明节点 → 声明名列表(§5 规则 5:CST 遍历声明 + AST 查找)。

    多变量声明(x, y)的 declarators 混有逗号 Token,按 hasattr(name) 过滤;
    genvar 声明不在此列(非信号符号不展开)。
    """
    kind = member.kind
    if kind in (syntax.SyntaxKind.DataDeclaration, syntax.SyntaxKind.NetDeclaration):
        decls = getattr(member, "declarators", None) or []
        return [d.name.value for d in decls if hasattr(d, "name")]
    if kind == syntax.SyntaxKind.ParameterDeclarationStatement:
        param = getattr(member, "parameter", None)
        return [d.name.value for d in param.declarators] if param is not None else []
    return []


def _struct_scope(t) -> ast.Type | None:
    """类型 → struct 作用域(canonicalType);非 struct 时 None(§1.5)。"""
    if t is None or not getattr(t, "isStruct", False):
        return None
    return getattr(t, "canonicalType", None)


def _enum_struct_fields(scope) -> list[ast.FieldSymbol]:
    """struct 作用域 → 直接 Field 符号列表(visit 收集;嵌套由调用方递归)。"""
    fields: list[ast.FieldSymbol] = []

    def collect(sym) -> None:
        if sym.kind == ast.SymbolKind.Field:
            fields.append(sym)

    scope.visit(collect)
    return fields


def _signal_full_path(instance_path: str, segments: list[str]) -> str:
    """拼接实例路径 + 基名 + 各字段名为 full_path(§1.5 拼接规则)。

    注意:FieldSymbol.hierarchicalPath 指向类型定义处,不可直接使用。
    """
    return ".".join([instance_path] + segments)


def _expand_struct_fields(
    rows: dict[str, SignalInfo],
    inst_path: str,
    segments: list[str],
    scope,
    base_sym,
    sm: SourceManager,
) -> None:
    """递归展开 struct 字段为信号行(kind='field',§1.5)。

    字段行 definition_file/line 继承基变量定义位置(§5 规则 6:
    字段符号的 location 指向类型定义处,不作信号定义位置)。
    """
    base_file, base_line = _location_of(base_sym, sm)
    for field in _enum_struct_fields(scope):
        segs = segments + [field.name]
        fp = _signal_full_path(inst_path, segs)
        if fp not in rows:
            ft = getattr(field, "type", None)
            rows[fp] = SignalInfo(
                instance_path=inst_path,
                full_path=fp,
                name=field.name,
                type_name=_type_name(ft),
                bit_width=_bit_width(ft),
                kind="field",
                is_port=False,
                direction="",
                definition_file=base_file,
                definition_line=base_line,
            )
        sub = _struct_scope(getattr(field, "type", None))
        if sub is not None:
            _expand_struct_fields(rows, inst_path, segs, sub, base_sym, sm)


def _collect_port_rows(
    rows: dict[str, SignalInfo], path: str, body: ast.InstanceBodySymbol, sm: SourceManager
) -> None:
    """portList 每端口一条信号行(kind='port');struct 端口展开字段行(§1.5)。"""
    for port in body.portList:
        fp = _signal_full_path(path, [port.name])
        pt = getattr(port, "type", None)
        pfile, pline = _location_of(port, sm)
        rows[fp] = SignalInfo(
            instance_path=path,
            full_path=fp,
            name=port.name,
            type_name=_type_name(pt),
            bit_width=_bit_width(pt),
            kind="port",
            is_port=True,
            direction=_DIRECTION_MAP.get(port.direction, str(port.direction)),
            definition_file=pfile,
            definition_line=pline,
        )
        scope = _struct_scope(pt)
        if scope is not None:
            # struct 端口的字段展开(§1.5 场景2):供端口字段读(如 cfg_i.div)
            # 解析;字段定义位置继承端口
            _expand_struct_fields(rows, path, [port.name], scope, port, sm)


def _collect_member_rows(
    rows: dict[str, SignalInfo], path: str, body: ast.InstanceBodySymbol, sm: SourceManager
) -> None:
    """成员声明逐名产出行(CST 遍历 + AST 查找,§5 规则 5);struct 变量展开字段。

    同 full_path 的 port 行与 variable 行合并为一行(§1.5 合并规则):
    kind/is_port/direction 取端口,name/type_name/bit_width/定义位置取变量符号;
    genvar / EnumValue 等非信号符号不展开。
    """
    for member in body.syntax.members:
        for name in _decl_names(member):
            sym = body.find(name)
            if sym is None:
                logger.debug(f"成员声明符号未找到,跳过: {path}.{name}")
                continue
            if sym.kind not in _MEMBER_KIND_MAP:
                continue
            fp = _signal_full_path(path, [name])
            sfile, sline = _location_of(sym, sm)
            if fp in rows and rows[fp].is_port:
                # 与端口行合并:kind/is_port/direction 取端口,其余取变量符号
                rows[fp] = SignalInfo(
                    instance_path=path,
                    full_path=fp,
                    name=sym.name,
                    type_name=_type_name(sym.type),
                    bit_width=_bit_width(sym.type),
                    kind="port",
                    is_port=True,
                    direction=rows[fp].direction,
                    definition_file=sfile,
                    definition_line=sline,
                )
            else:
                rows[fp] = SignalInfo(
                    instance_path=path,
                    full_path=fp,
                    name=sym.name,
                    type_name=_type_name(sym.type),
                    bit_width=_bit_width(sym.type),
                    kind=_MEMBER_KIND_MAP[sym.kind],
                    is_port=False,
                    direction="",
                    definition_file=sfile,
                    definition_line=sline,
                )
            scope = _struct_scope(sym.type)
            if scope is not None:
                _expand_struct_fields(rows, path, [name], scope, sym, sm)


def _collect_instance_signals(
    inst: ast.InstanceSymbol, sm: SourceManager
) -> list[SignalInfo]:
    """单实例信号行:端口(portList 序)→ 成员声明(声明序)→ struct 字段。

    合并后按 full_path 唯一(流程③依赖此保证)。
    """
    path = inst.hierarchicalPath
    rows: dict[str, SignalInfo] = {}
    _collect_port_rows(rows, path, inst.body, sm)
    _collect_member_rows(rows, path, inst.body, sm)
    return list(rows.values())


def _extract_signals_impl(
    root: ast.RootSymbol, sm: SourceManager
) -> list[SignalInfo]:
    """共享编译的信号提取实现:按实例 DFS 前序逐个收集(§4 顺序)。"""
    signals: list[SignalInfo] = []
    for inst in _collect_instances(root):
        signals.extend(_collect_instance_signals(inst, sm))
    return signals


# ── 块提取(§1.6/§5 规则 7/8) ───────────────────────────────────────


def _classify_block(sym: ast.Symbol) -> str:
    """块符号 → block_type:ContinuousAssign → 'assign';过程块按 procedureKind。"""
    if sym.kind == ast.SymbolKind.ContinuousAssign:
        return "assign"
    procedure_kind = getattr(sym, "procedureKind", None)
    return _PROCEDURE_KIND_MAP.get(procedure_kind, str(procedure_kind))


def _collect_direct_blocks(
    body: ast.InstanceBodySymbol,
) -> list[tuple[ast.Symbol, str]]:
    """本实例直接块,返回 (块符号, 块类型)(§5 规则 7)。

    visit 会穿透子实例,须按 parentScope.containingInstance 过滤,
    只留本实例直接块。
    """
    blocks: list[tuple[ast.Symbol, str]] = []

    def check(sym) -> None:
        if sym.kind not in (
            ast.SymbolKind.ProceduralBlock,
            ast.SymbolKind.ContinuousAssign,
        ):
            return
        parent = sym.parentScope
        if hasattr(parent, "containingInstance") and parent.containingInstance is not body:
            return
        blocks.append((sym, _classify_block(sym)))

    body.visit(check)
    return blocks


def _collect_child_instances(body: ast.InstanceBodySymbol) -> list[ast.InstanceSymbol]:
    """本实例的直接子实例(containingInstance 过滤,visit 序)。"""
    children: list[ast.InstanceSymbol] = []

    def check(sym) -> None:
        if sym.kind != ast.SymbolKind.Instance:
            return
        parent = sym.parentScope
        if hasattr(parent, "containingInstance") and parent.containingInstance is not body:
            return
        children.append(sym)

    body.visit(check)
    return children


def _port_conn_syntax(child: ast.InstanceSymbol):
    """子实例化语句的 HierarchyInstantiation CST;无源语法时 None(§5 规则 8)。

    块提取与边提取共用本判定,保证 blocks 列表与边绑定的块对象一一对应。
    """
    syntax_node = getattr(child, "syntax", None)
    return getattr(syntax_node, "parent", None)


#: 源文本行缓存:文件绝对路径 → 行列表(单进程内文件内容不变,可安全复用)
_source_lines_cache: dict[str, list[str]] = {}


def _read_source_lines(sm: SourceManager, buffer) -> list[str]:
    """SourceManager 取文件全部行,按绝对路径缓存。"""
    path = str(sm.getFullPath(buffer))
    if path not in _source_lines_cache:
        _source_lines_cache[path] = sm.getSourceText(buffer).splitlines()
    return _source_lines_cache[path]


def _source_of(node, sm: SourceManager) -> tuple[str, int, int, str]:
    """node.sourceRange → (文件绝对路径, 起始行, 结束行, 源文本)(§1.6)。

    行号 1-indexed,源文本为含首尾行的原始文本;接受带 sourceRange 的
    AST 符号语法节点(块)或 CST 节点(实例化语句)。
    """
    sr = node.sourceRange
    start = sm.getLineNumber(sr.start)
    end = sm.getLineNumber(sr.end)
    file = str(sm.getFullPath(sr.start.buffer))
    text = "\n".join(_read_source_lines(sm, sr.start.buffer)[start - 1 : end])
    return file, start, end, text


def _extract_blocks_impl(
    root: ast.RootSymbol, sm: SourceManager
) -> list[BlockInfo]:
    """共享编译的块提取实现(§1.6)。

    每实例:直接块(遍历序)→ port_connection 块(直接子实例,列实例末尾);
    index 为全列表递增序号;无源语法的块/实例化语句跳过(§5 规则 8)。
    """
    blocks: list[BlockInfo] = []
    for inst in _collect_instances(root):
        inst_path = inst.hierarchicalPath
        body = inst.body
        for sym, block_type in _collect_direct_blocks(body):
            syntax_node = getattr(sym, "syntax", None)
            if syntax_node is None:
                logger.debug(f"块无源语法,跳过: {inst_path}")
                continue
            file, start, end, text = _source_of(syntax_node, sm)
            blocks.append(
                BlockInfo(
                    instance_path=inst_path,
                    index=len(blocks),
                    block_type=block_type,
                    source_file=file,
                    start_line=start,
                    end_line=end,
                    source_text=text,
                )
            )
        for child in _collect_child_instances(body):
            hier = _port_conn_syntax(child)
            if hier is None:
                continue
            file, start, end, text = _source_of(hier, sm)
            blocks.append(
                BlockInfo(
                    instance_path=inst_path,
                    index=len(blocks),
                    block_type="port_connection",
                    source_file=file,
                    start_line=start,
                    end_line=end,
                    source_text=text,
                )
            )
    return blocks


# ── 依赖提取(§6) ──────────────────────────────────────────────────


def _collect_member_chain(expr) -> list[str] | None:
    """NamedValue → [基名];MemberAccess → 自顶向下段列表;其他 → None(§6.3)。

    注:spec §3 规划返回 Symbol 列表;one-pass 建边只需段名拼接 full_path,
    故改为段名列表。
    """
    if expr is None:
        return None
    if expr.kind == ast.ExpressionKind.NamedValue:
        s = getattr(expr, "symbol", None)
        return [s.name] if s is not None else None
    if expr.kind == ast.ExpressionKind.MemberAccess:
        segs: list[str] = []
        node = expr
        while node is not None and node.kind == ast.ExpressionKind.MemberAccess:
            member = getattr(node, "member", None)
            if member is None:
                return None
            segs.append(member.name)
            node = node.value
        if node is not None and node.kind == ast.ExpressionKind.NamedValue:
            s = getattr(node, "symbol", None)
            if s is not None:
                segs.append(s.name)
                segs.reverse()
                return segs
        return None
    return None


def _add_read(reads: list[str], fp: str, valid: set[str]) -> None:
    """读取候选信号入列;不在信号表时 logger.debug 并丢弃(§5 规则 9)。"""
    if fp in valid:
        reads.append(fp)
    else:
        logger.debug(f"读取信号不在信号表中,丢弃: {fp}")


def _flat_reads(node, reads: list[str], inst_path: str, valid: set[str]) -> None:
    """未知表达式种类的回退收集:flat visit 收 NV/MA(前缀去重近似)。

    仅覆盖显式递归未枚举的罕见种类(如结构化赋值模式);
    近似缺陷:同一表达式内"整链 + 部分链"并存时可能漏报部分链
    (如 a.b.c + a.b,ref.md §5 未覆盖种类)。
    """
    chains: list[list[str]] = []
    names: list[str] = []

    def collect(n) -> None:
        if n.kind == ast.ExpressionKind.NamedValue:
            s = getattr(n, "symbol", None)
            if s is not None:
                names.append(s.name)
        elif n.kind == ast.ExpressionKind.MemberAccess:
            segs = _collect_member_chain(n)
            if segs is not None:
                chains.append(segs)

    node.visit(collect)
    for segs in chains:
        if not any(other != segs and other[: len(segs)] == segs for other in chains):
            _add_read(reads, _signal_full_path(inst_path, segs), valid)
    for name in names:
        if not any(chain[0] == name for chain in chains):
            _add_read(reads, _signal_full_path(inst_path, [name]), valid)


def _expression_children(node):
    """表达式节点 → 子表达式列表(读取收集的显式递归分发);未知种类返回 None。

    MemberAccess 的 .member 是字段名非表达式,不列入子节点(链整体由
    _collect_reads 处理);叶子种类返回空列表。
    """
    EK = ast.ExpressionKind
    kind = node.kind
    if kind == EK.NamedValue or kind in _LEAF_EXPR_KINDS:
        return []
    if kind == EK.MemberAccess:
        return [getattr(node, "value", None)]
    if kind == EK.UnaryOp:
        return [getattr(node, "operand", None)]
    if kind == EK.BinaryOp:
        return [getattr(node, "left", None), getattr(node, "right", None)]
    if kind == EK.ConditionalOp:
        conds = [getattr(c, "expr", None) for c in getattr(node, "conditions", []) or []]
        return conds + [getattr(node, "left", None), getattr(node, "right", None)]
    if kind == EK.Assignment:
        return [getattr(node, "left", None), getattr(node, "right", None)]
    if kind == EK.ElementSelect:
        return [getattr(node, "value", None), getattr(node, "selector", None)]
    if kind == EK.RangeSelect:
        return [getattr(node, "value", None), getattr(node, "left", None), getattr(node, "right", None)]
    if kind == EK.Conversion:
        return [getattr(node, "operand", None)]
    if kind == EK.Concatenation:
        return list(getattr(node, "operands", []) or [])
    if kind == EK.Replication:
        return [getattr(node, "count", None), getattr(node, "concat", None)]
    if kind == EK.Call:
        return list(getattr(node, "arguments", []) or [])
    return None  # 未知种类 → flat visit 回退


def _collect_reads(expr, inst_path: str, valid: set[str]) -> list[str]:
    """收集表达式读取的候选信号 full_path(仅有效集内,§6.3 读侧)。

    显式递归遍历(最大链语义):MemberAccess 链整体作为一次读取,不重复计
    链上前缀(如 cfg_reg.baud.div 只读 div 字段行);整 struct 读以基变量行
    参与(链底基名即命中);三元运算符三个操作数自然覆盖;读侧
    x = mem[addr] 穿透 ElementSelect 命中 mem/addr,无需特殊代码。
    """
    reads: list[str] = []
    EK = ast.ExpressionKind

    def walk(node) -> None:
        if node is None:
            return
        kind = node.kind
        if kind == EK.NamedValue:
            s = getattr(node, "symbol", None)
            if s is not None:
                _add_read(reads, _signal_full_path(inst_path, [s.name]), valid)
        elif kind == EK.MemberAccess:
            segs = _collect_member_chain(node)
            if segs is not None:
                _add_read(reads, _signal_full_path(inst_path, segs), valid)
            return  # 链整体为一次读取,不递归链上前缀
        children = _expression_children(node)
        if children is None:
            _flat_reads(node, reads, inst_path, valid)
            return
        for child in children:
            walk(child)

    walk(expr)
    return reads


def _resolve_lhs(expr, inst_path: str, valid: set[str]) -> tuple[str | None, list[str]]:
    """LHS 解析(§6.3):剥 ElementSelect/RangeSelect → 段路径 → 驱动 full_path。

    返回 (驱动 full_path | None, 下标读取候选列表);LHS 无法解析为信号行时
    驱动为 None(调用方丢弃 driven 边,§5 规则 9);下标表达式计入读取(下标是读)。
    RangeSelect(部分选择写)按同 Select 剥离规则处理(评审意见 §3.2 定稿)。
    """
    reads: list[str] = []
    node = expr
    while node is not None and node.kind in (
        ast.ExpressionKind.ElementSelect,
        ast.ExpressionKind.RangeSelect,
    ):
        if node.kind == ast.ExpressionKind.ElementSelect:
            reads.extend(_collect_reads(node.selector, inst_path, valid))
        else:
            reads.extend(_collect_reads(node.left, inst_path, valid))
            reads.extend(_collect_reads(node.right, inst_path, valid))
        node = node.value
    segs = _collect_member_chain(node)
    if segs is None:
        logger.debug(f"LHS 无法解析为信号行,跳过: {inst_path}")
        return None, reads
    fp = _signal_full_path(inst_path, segs)
    if fp not in valid:
        logger.debug(f"LHS 信号不在信号表中,跳过: {fp}")
        return None, reads
    return fp, reads


def _broadcast_conditions(
    stmt,
    conditions,
    inst_path: str,
    valid: set[str],
    block_obj: BlockInfo | None,
    cond_edges: list[DepEdge],
) -> None:
    """条件向分支子树内全部赋值广播(§6.1 通道 2)。

    对分支语句 visit(),每遇 Assignment,对 (条件读取信号 × LHS 信号)
    逐一产生 is_condition=True 的边。嵌套条件自动累积:外层广播命中内层
    分支的赋值,内层再广播一次(§5.4)。
    """
    if stmt is None:
        return
    cond_reads: list[str] = []
    for cond in conditions:
        cond_reads.extend(_collect_reads(cond, inst_path, valid))
    if not cond_reads:
        return

    def hit(node) -> None:
        if node.kind != ast.ExpressionKind.Assignment:
            return
        driven, _ = _resolve_lhs(node.left, inst_path, valid)
        if driven is None:
            return
        for r in cond_reads:
            cond_edges.append(DepEdge(driven, r, block_obj, True, False))

    stmt.visit(hit)


def _broadcast_stmt_conditions(
    node, inst_path: str, valid: set[str], block_obj: BlockInfo | None, cond_edges: list[DepEdge]
) -> None:
    """语句节点 → 门控条件向分支子树广播(§6.1 通道 2 分发)。

    Conditional/Case/ForLoop/Timed 四类条件语句,条件表达式取自对应属性
    (§5.2 实测);嵌套条件自动累积(§5.4)。
    """
    SK = ast.StatementKind
    kind = node.kind
    if kind == SK.Conditional:
        conds = [c.expr for c in node.conditions]
        for branch in (node.ifTrue, node.ifFalse):
            _broadcast_conditions(branch, conds, inst_path, valid, block_obj, cond_edges)
    elif kind == SK.Case:
        sel = [node.expr]
        for item in node.items:
            conds = sel + list(item.expressions or [])
            _broadcast_conditions(item.stmt, conds, inst_path, valid, block_obj, cond_edges)
        _broadcast_conditions(node.defaultCase, sel, inst_path, valid, block_obj, cond_edges)
    elif kind == SK.ForLoop:
        _broadcast_conditions(node.body, [node.stopExpr], inst_path, valid, block_obj, cond_edges)
    elif kind == SK.Timed:
        _broadcast_conditions(node.stmt, [node.timing], inst_path, valid, block_obj, cond_edges)


def _build_block_edges(
    block_sym, block_obj: BlockInfo | None, inst_path: str, valid: set[str]
) -> list[DepEdge]:
    """单块内赋值级依赖提取(§6.1 两通道,单遍遍历建出全部边)。

    产出顺序与 §1.8 示例一致:通道 1 边在前、通道 2 边在后(单遍 visit
    中分别收集再拼接)。复合赋值(isCompound)把 LHS 基变量链计入读取
    (隐式读自身);自增/自减(UnaryOp)产生自依赖边;连续赋值无语句条件,
    只走通道 1。
    """
    edges: list[DepEdge] = []
    cond_edges: list[DepEdge] = []
    EK = ast.ExpressionKind

    def on_node(node) -> None:
        kind = node.kind
        if kind == EK.Assignment:
            driven, lhs_reads = _resolve_lhs(node.left, inst_path, valid)
            if driven is not None:
                reads = _collect_reads(node.right, inst_path, valid)
                if node.isCompound:
                    reads.append(driven)  # 复合赋值隐式读 LHS(§6.1)
                reads.extend(lhs_reads)  # LHS 下标是读(§6.3)
                for r in reads:
                    edges.append(DepEdge(driven, r, block_obj, False, False))
        elif kind == EK.UnaryOp and getattr(node, "op", None) in _INCDEC_OPS:
            driven, lhs_reads = _resolve_lhs(node.operand, inst_path, valid)
            if driven is not None:
                edges.append(DepEdge(driven, driven, block_obj, False, False))
                for r in lhs_reads:
                    edges.append(DepEdge(driven, r, block_obj, False, False))
        elif kind in _COND_STMT_KINDS:
            _broadcast_stmt_conditions(node, inst_path, valid, block_obj, cond_edges)

    block_sym.visit(on_node)
    return edges + cond_edges


def _parent_conn_path(expr, parent_inst_path: str) -> str | None:
    """父侧端口连接表达式 → 父实例内信号 full_path(§6.2)。

    NamedValue 取 symbol.hierarchicalPath(实测为父实例内完整路径,可直接用);
    MemberAccess(struct 端口字段)按 §6.3 拼接规则解析;其他 None。
    """
    if expr is None:
        return None
    if expr.kind == ast.ExpressionKind.NamedValue:
        s = getattr(expr, "symbol", None)
        return getattr(s, "hierarchicalPath", None)
    if expr.kind == ast.ExpressionKind.MemberAccess:
        segs = _collect_member_chain(expr)
        return _signal_full_path(parent_inst_path, segs) if segs is not None else None
    return None


def _build_port_conn_edges(
    child: ast.InstanceSymbol,
    parent_inst_path: str,
    block_obj: BlockInfo | None,
    valid: set[str],
) -> list[DepEdge]:
    """实例端口连接跨模块边(§6.2):In 父→子;Out 子→父。

    每条连接一条边,is_port_conn=True;block 绑定该实例化语句的
    port_connection 块(块因无源语法被跳过时 block=None,§5 规则 8);
    InOut/Ref 告警跳过(§7);空连接/符号缺失 debug 跳过。
    """
    edges: list[DepEdge] = []
    EK = ast.ExpressionKind
    for conn in child.portConnections:
        port = getattr(conn, "port", None)
        if port is None:
            logger.debug(f"端口连接无端口符号,跳过: {child.name}")
            continue
        if port.direction in (ast.ArgumentDirection.InOut, ast.ArgumentDirection.Ref):
            logger.warning(f"InOut/Ref 端口连接不在本次范围,跳过: {child.name}.{port.name}")
            continue
        internal = getattr(port, "internalSymbol", None)
        internal_path = getattr(internal, "hierarchicalPath", None)
        expr = getattr(conn, "expression", None)
        if expr is None or expr.kind == EK.EmptyArgument:
            logger.debug(f"端口连接表达式为空,跳过: {child.name}.{port.name}")
            continue
        if port.direction == ast.ArgumentDirection.In:
            if expr.kind not in (EK.NamedValue, EK.MemberAccess):
                logger.warning(f"输入端口连接表达式结构不识别,跳过: {child.name}.{port.name}")
                continue
            driven, read = _parent_conn_path(expr, parent_inst_path), internal_path
        else:  # Out:conn.expression 为 Assignment,.left 为父模块被驱动信号
            if expr.kind != EK.Assignment:
                logger.warning(f"输出端口连接表达式结构不识别,跳过: {child.name}.{port.name}")
                continue
            parent_path = _parent_conn_path(getattr(expr, "left", None), parent_inst_path)
            driven, read = internal_path, parent_path
        if driven is None or read is None or driven not in valid or read not in valid:
            logger.debug(f"端口连接边引用的信号不在信号表中,丢弃: {child.name}.{port.name}")
            continue
        edges.append(DepEdge(driven, read, block_obj, False, True))
    return edges


def _dedup_edges(edges: list[DepEdge]) -> list[DepEdge]:
    """按 (driven, read, 块对象身份, is_condition, is_port_conn) 去重(§5 规则 10)。

    保持首次出现顺序;块对象以 id() 判定(同一 BlockInfo 对象)。
    """
    seen: set[tuple] = set()
    result: list[DepEdge] = []
    for e in edges:
        key = (e.driven_signal, e.read_signal, id(e.block), e.is_condition, e.is_port_conn)
        if key not in seen:
            seen.add(key)
            result.append(e)
    return result


def _extract_dep_edges_impl(
    root: ast.RootSymbol,
    sm: SourceManager,
    blocks: list[BlockInfo],
    signals: list[SignalInfo],
) -> list[DepEdge]:
    """共享编译的依赖提取实现(§6 汇总;边直接绑定传入 blocks 中的对象)。

    按与 _extract_blocks_impl 完全相同的遍历顺序消费 blocks(§2 顺序要求):
    直接块 → 下一 BlockInfo;port_connection → 有源语法取下一项,被跳过时
    block=None(§5 规则 8 兜底)。边两端必须引用已产出的信号 full_path。
    """
    valid = {s.full_path for s in signals}
    edges: list[DepEdge] = []
    bidx = 0
    for inst in _collect_instances(root):
        inst_path = inst.hierarchicalPath
        body = inst.body
        for sym, _block_type in _collect_direct_blocks(body):
            if getattr(sym, "syntax", None) is None:
                block_obj = None  # 块因无源语法被跳过,边 block=None
            else:
                block_obj = blocks[bidx]
                bidx += 1
            edges.extend(_build_block_edges(sym, block_obj, inst_path, valid))
        for child in _collect_child_instances(body):
            hier = _port_conn_syntax(child)
            block_obj = blocks[bidx] if hier is not None else None
            if hier is not None:
                bidx += 1
            edges.extend(_build_port_conn_edges(child, inst_path, block_obj, valid))
    return _dedup_edges(edges)
