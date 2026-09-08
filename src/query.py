"""流程④ API 查询:只读查询流程③产出的 sqlite 库,服务四大功能。

行为契约见 doc/flow4_design_spec.md:每次调用独立建引擎、只读连接、查完
dispose;不写库、不重新解析 SV、不打日志。所有查询基于 src/schema.py 的
Table 元数据构建(SQLAlchemy Core 表达式,禁止手写 SQL 字符串),并执行
两条定稿查询语义:§5.1 端口连接边方向映射(端口连接边按数据流方向存储,
与块内边取列相反)与 §5.2 base↔field 层级合并(匹配行集 = var_path 自身
+ 祖先 + 后裔字段行,LIKE 需转义)。
"""

import os

from sqlalchemy import (
    Connection,
    Select,
    and_,
    create_engine,
    or_,
    select,
    union,
)
from sqlalchemy.engine import Engine, Row

from datatypes import BlockInfo, SignalInfo
from schema import blocks, dep_edges, instances, signals


def get_variable_info(db_path: str, var_path: str) -> SignalInfo:
    """变量信息:返回 var_path 精确匹配的信号行(§4.1)。

    信号行不存在 → ValueError(§6 规则 3);不适用 base↔field 合并规则,
    无合并查询。
    """
    engine = _create_engine(db_path)
    try:
        with engine.connect() as conn:
            return _row_to_signal(_get_signal_row(conn, var_path))
    finally:
        engine.dispose()


def get_assignment_blocks(db_path: str, var_path: str) -> list[BlockInfo]:
    """赋值语句块:完整赋值该变量的语句块列表,按块 id 升序(§4.2)。

    块内边以 driven 为被赋值侧、端口连接边以 read 为被驱动侧(§5.1);
    匹配行集按 §5.2 合并。同一块多条边 DISTINCT 一行;无匹配块 → 空列表。
    """
    engine = _create_engine(db_path)
    try:
        with engine.connect() as conn:
            _get_signal_row(conn, var_path)  # 存在性校验(§6 规则 3)
            matching = _matching_ids(conn, var_path)
            stmt = (
                select(
                    blocks.c.id,
                    instances.c.path.label("instance_path"),
                    blocks.c.block_type,
                    blocks.c.source_file,
                    blocks.c.start_line,
                    blocks.c.end_line,
                    blocks.c.source_text,
                )
                .select_from(
                    dep_edges.join(blocks, blocks.c.id == dep_edges.c.block_id).join(
                        instances, instances.c.id == blocks.c.instance_id
                    )
                )
                .where(
                    or_(
                        and_(
                            dep_edges.c.is_port_conn == 0,
                            dep_edges.c.driven_signal_id.in_(matching),
                        ),
                        and_(
                            dep_edges.c.is_port_conn == 1,
                            dep_edges.c.read_signal_id.in_(matching),
                        ),
                    )
                )
                .distinct()
                .order_by(blocks.c.id)
            )
            return _rows_to_blocks(conn.execute(stmt).all())
    finally:
        engine.dispose()


def trace_load(db_path: str, var_path: str) -> list[str]:
    """trace load(fan-out):读取该变量的赋值所驱动的信号 full_path 列表(§4.3)。

    块内边取 read 命中边的 driven;端口连接边取 driven 命中边的 read
    (§5.1);行集按 §5.2 合并。UNION 去重后按 full_path 升序;含条件读与
    端口连接边(§5.3);无匹配边 → 空列表。
    """
    engine = _create_engine(db_path)
    try:
        with engine.connect() as conn:
            _get_signal_row(conn, var_path)  # 存在性校验(§6 规则 3)
            matching = _matching_ids(conn, var_path)
            in_block = (
                select(signals.c.full_path)
                .select_from(
                    dep_edges.join(
                        signals, signals.c.id == dep_edges.c.driven_signal_id
                    )
                )
                .where(
                    dep_edges.c.read_signal_id.in_(matching),
                    dep_edges.c.is_port_conn == 0,
                )
            )
            port_conn = (
                select(signals.c.full_path)
                .select_from(
                    dep_edges.join(signals, signals.c.id == dep_edges.c.read_signal_id)
                )
                .where(
                    dep_edges.c.driven_signal_id.in_(matching),
                    dep_edges.c.is_port_conn == 1,
                )
            )
            return list(conn.execute(union(in_block, port_conn)).scalars())
    finally:
        engine.dispose()


def trace_driver(db_path: str, var_path: str) -> list[str]:
    """trace driver(fan-in):驱动该变量的赋值所读的信号 full_path 列表(§4.4)。

    块内边取 driven 命中边的 read;端口连接边取 read 命中边的 driven
    (§5.1);行集按 §5.2 合并。UNION 去重后按 full_path 升序;含条件读与
    端口连接边(§5.3);无匹配边 → 空列表。
    """
    engine = _create_engine(db_path)
    try:
        with engine.connect() as conn:
            _get_signal_row(conn, var_path)  # 存在性校验(§6 规则 3)
            matching = _matching_ids(conn, var_path)
            in_block = (
                select(signals.c.full_path)
                .select_from(
                    dep_edges.join(signals, signals.c.id == dep_edges.c.read_signal_id)
                )
                .where(
                    dep_edges.c.driven_signal_id.in_(matching),
                    dep_edges.c.is_port_conn == 0,
                )
            )
            port_conn = (
                select(signals.c.full_path)
                .select_from(
                    dep_edges.join(
                        signals, signals.c.id == dep_edges.c.driven_signal_id
                    )
                )
                .where(
                    dep_edges.c.read_signal_id.in_(matching),
                    dep_edges.c.is_port_conn == 1,
                )
            )
            return list(conn.execute(union(in_block, port_conn)).scalars())
    finally:
        engine.dispose()


def _create_engine(db_path: str) -> Engine:
    """校验库文件存在并建引擎(spec §2;每次调用独立引擎,查完 dispose)。

    db_path 不是文件 → FileNotFoundError 直接爆出(§6 规则 1);URL 用绝对
    路径,与流程③一致。不挂 PRAGMA/不写库,无需连接事件。
    """
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"数据库文件不存在: {db_path}")
    return create_engine(f"sqlite:///{os.path.abspath(db_path)}")


def _get_signal_row(conn: Connection, var_path: str) -> Row:
    """查 var_path 精确匹配的信号行(JOIN instances 取 instance_path,§4.1)。

    无行 → ValueError(f"变量不存在: {var_path}")(§6 规则 3),先于合并
    查询执行,拼写错误立刻暴露;full_path 唯一,恰一行。
    """
    stmt = (
        select(
            signals.c.full_path,
            signals.c.name,
            signals.c.type_name,
            signals.c.bit_width,
            signals.c.kind,
            signals.c.is_port,
            signals.c.direction,
            signals.c.definition_file,
            signals.c.definition_line,
            instances.c.path.label("instance_path"),
        )
        .select_from(
            signals.join(instances, instances.c.id == signals.c.instance_id)
        )
        .where(signals.c.full_path == var_path)
    )
    row = conn.execute(stmt).first()
    if row is None:
        raise ValueError(f"变量不存在: {var_path}")
    return row


def _matching_ids(conn: Connection, var_path: str) -> Select:
    """构造 base↔field 合并匹配的信号 id 子查询(§5.2),三个边查询复用。

    匹配行集 = var_path 自身与各级祖先前缀(IN 精确匹配;instance 路径
    前缀天然不命中,无信号行)∪ 全部后裔字段行(LIKE var_path || '.%',
    经 _escape_like 转义)。普通信号(无字段行)自动退化为精确匹配。
    """
    parts = var_path.split(".")
    prefixes = [".".join(parts[:i]) for i in range(len(parts), 0, -1)]
    escaped = _escape_like(var_path)
    return (
        select(signals.c.id)
        .where(
            or_(
                signals.c.full_path.in_(prefixes),
                signals.c.full_path.like(escaped + ".%", escape="\\"),
            )
        )
    )


def _escape_like(text: str) -> str:
    """转义 LIKE 模式特殊字符 \\ % _(逐个前置 \\,§5.2)。

    信号名可含下划线(如 clk_2),不转义时 '_' 匹配任意单字符,会误匹配
    'clkX2.field' 之类路径。
    """
    for special in ("\\", "%", "_"):
        text = text.replace(special, "\\" + special)
    return text


def _row_to_signal(row: Row) -> SignalInfo:
    """信号行 → SignalInfo;is_port 由 Integer 0/1 转 bool(§1.3)。

    行列序即 §4.1 SELECT 序:full_path/name/type_name/bit_width/kind/
    is_port/direction/definition_file/definition_line/instance_path。
    """
    return SignalInfo(
        instance_path=row[9],
        full_path=row[0],
        name=row[1],
        type_name=row[2],
        bit_width=row[3],
        kind=row[4],
        is_port=bool(row[5]),
        direction=row[6],
        definition_file=row[7],
        definition_line=row[8],
    )


def _rows_to_blocks(rows: list[Row]) -> list[BlockInfo]:
    """块行 → BlockInfo;index = 块 id - 1(flow3 显式 id 契约的逆映射)。

    行列序即 §4.2 SELECT 序:id/instance_path/block_type/source_file/
    start_line/end_line/source_text。
    """
    return [
        BlockInfo(
            instance_path=row[1],
            index=row[0] - 1,
            block_type=row[2],
            source_file=row[3],
            start_line=row[4],
            end_line=row[5],
            source_text=row[6],
        )
        for row in rows
    ]
