"""流程③ sqlite 落库:把流程②的 ParseResult 一次性持久化入库。

行为契约见 doc/flow3_design_spec.md:全量重建、SQLAlchemy Core(不手写
sqlite3/DDL)、单事务(`engine.begin()` 成功自动 commit、异常自动回滚)、
全表显式 id(列表位置 + 1,blocks 为 index + 1)、边解析失败告警丢弃。
"""

import os

from loguru import logger
from sqlalchemy import Connection, create_engine, event, func, select
from sqlalchemy.engine import Engine

from datatypes import (
    BlockInfo,
    DepEdge,
    InstanceInfo,
    ParseResult,
    SignalInfo,
)
from schema import (
    blocks,
    dep_edges,
    instance_ports,
    instances,
    metadata,
    signals,
)


def build_db(parse_result: ParseResult, db_path: str) -> None:
    """把 ParseResult 一次性持久化到 sqlite 数据库文件(全量重建)。

    db_path 已存在时先删除(spec §5 规则 1);空四列表是合法输入,
    建 6 张空表。插入全部在一个事务内,任一步异常自动回滚并爆出(§7)。
    """
    if os.path.exists(db_path):
        os.remove(db_path)
    engine = _create_engine(db_path)
    try:
        _create_schema(engine)
        with engine.begin() as conn:
            instance_ids = _insert_instances(conn, parse_result.instances)
            _insert_ports(conn, parse_result.instances, instance_ids)
            signal_ids = _insert_signals(conn, parse_result.signals, instance_ids)
            block_ids = _insert_blocks(conn, parse_result.blocks, instance_ids)
            dropped = _insert_dep_edges(
                conn, parse_result.dep_edges, signal_ids, block_ids
            )
        _log_summary(engine, dropped)
    finally:
        engine.dispose()


def _create_engine(db_path: str) -> Engine:
    """建引擎并挂 connect 事件:逐连接执行 PRAGMA foreign_keys=ON。

    SQLAlchemy 按需创建连接,PRAGMA 只对单个连接生效,仅对 engine 执行
    一次无效;漏开则 REFERENCES 约束静默失效(spec §5 规则 2)。
    """
    engine = create_engine(f"sqlite:///{os.path.abspath(db_path)}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _record) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def _create_schema(engine: Engine) -> None:
    """建 6 张表与全部索引(spec §4;元数据定义于 src/schema.py)。"""
    metadata.create_all(engine)


def _insert_instances(
    conn: Connection, instances_list: list[InstanceInfo]
) -> dict[str, int]:
    """按列表序批量插入实例行(显式 id = 位置 + 1),返回 path→id 映射。

    parent_id 按 path 前缀反查已建映射(flow2 按 DFS 前序产出,父先于子);
    父路径不在映射中 → KeyError 直接爆出(spec §5 规则 6)。
    """
    path_to_id: dict[str, int] = {}
    rows: list[dict] = []
    for position, inst in enumerate(instances_list):
        inst_id = position + 1
        parent_id = None
        if "." in inst.path:
            parent_id = path_to_id[inst.path.rsplit(".", 1)[0]]
        path_to_id[inst.path] = inst_id
        rows.append(
            {
                "id": inst_id,
                "path": inst.path,
                "name": inst.name,
                "module_name": inst.module_name,
                "parent_id": parent_id,
                "depth": inst.depth,
                "file": inst.file,
            }
        )
    if rows:
        conn.execute(instances.insert(), rows)
    return path_to_id


def _insert_ports(
    conn: Connection,
    instances_list: list[InstanceInfo],
    instance_ids: dict[str, int],
) -> None:
    """插入 instance_ports 行(position 自 0 按端口声明序递增,§5 规则 7)。"""
    rows: list[dict] = []
    for inst in instances_list:
        for position, port in enumerate(inst.ports):
            rows.append(
                {
                    "instance_id": instance_ids[inst.path],
                    "position": position,
                    "name": port.name,
                    "direction": port.direction,
                    "bit_width": port.bit_width,
                }
            )
    if rows:
        conn.execute(instance_ports.insert(), rows)


def _insert_signals(
    conn: Connection,
    signals_list: list[SignalInfo],
    instance_ids: dict[str, int],
) -> dict[str, int]:
    """按列表序批量插入信号行(显式 id = 位置 + 1),返回 full_path→id 映射。

    instance_path 不在实例映射 → KeyError 直接爆出(flow2 契约保证一致,
    spec §5 规则 8);direction 原样落列(非端口为空串)。
    """
    full_path_to_id: dict[str, int] = {}
    rows: list[dict] = []
    for position, sig in enumerate(signals_list):
        sig_id = position + 1
        full_path_to_id[sig.full_path] = sig_id
        rows.append(
            {
                "id": sig_id,
                "instance_id": instance_ids[sig.instance_path],
                "name": sig.name,
                "full_path": sig.full_path,
                "type_name": sig.type_name,
                "bit_width": sig.bit_width,
                "kind": sig.kind,
                "is_port": sig.is_port,
                "direction": sig.direction,
                "definition_file": sig.definition_file,
                "definition_line": sig.definition_line,
            }
        )
    if rows:
        conn.execute(signals.insert(), rows)
    return full_path_to_id


def _insert_blocks(
    conn: Connection,
    blocks_list: list[BlockInfo],
    instance_ids: dict[str, int],
) -> dict[int, int]:
    """按列表序插入块行(显式 id = index + 1),返回 id(BlockInfo)→id 映射。

    映射按对象身份(flow2 §9 契约),供依赖边解析 block_id。
    """
    block_id_by_obj: dict[int, int] = {}
    rows: list[dict] = []
    for blk in blocks_list:
        block_id = blk.index + 1
        block_id_by_obj[id(blk)] = block_id
        rows.append(
            {
                "id": block_id,
                "instance_id": instance_ids[blk.instance_path],
                "block_type": blk.block_type,
                "source_file": blk.source_file,
                "start_line": blk.start_line,
                "end_line": blk.end_line,
                "source_text": blk.source_text,
            }
        )
    if rows:
        conn.execute(blocks.insert(), rows)
    return block_id_by_obj


def _insert_dep_edges(
    conn: Connection,
    edges: list[DepEdge],
    signal_ids: dict[str, int],
    block_ids: dict[int, int],
) -> int:
    """按列表序插入依赖边(显式 id = 原始列表位置 + 1),返回丢弃边数。

    两端信号 full_path 不在映射 → logger.warning 并丢弃该边(flow2 §9
    契约的兜底,spec §5 规则 10);block 对象不在映射 → KeyError 直接爆出
    (flow2 保证不存在此情形)。
    """
    rows: list[dict] = []
    dropped = 0
    for position, edge in enumerate(edges):
        driven = signal_ids.get(edge.driven_signal)
        read = signal_ids.get(edge.read_signal)
        if driven is None or read is None:
            logger.warning(
                "依赖边引用的信号不在信号表中,丢弃该边: driven={} read={}",
                edge.driven_signal,
                edge.read_signal,
            )
            dropped += 1
            continue
        rows.append(
            {
                "id": position + 1,
                "driven_signal_id": driven,
                "read_signal_id": read,
                "block_id": None if edge.block is None else block_ids[id(edge.block)],
                "is_condition": edge.is_condition,
                "is_port_conn": edge.is_port_conn,
            }
        )
    if rows:
        conn.execute(dep_edges.insert(), rows)
    return dropped


def _log_summary(engine: Engine, dropped_edges: int) -> None:
    """统计各表行数并 logger.info 汇总(含丢弃边计数,§5 规则 12)。"""
    tables = (instances, instance_ports, signals, blocks, dep_edges)
    with engine.connect() as conn:
        counts = [
            conn.execute(select(func.count()).select_from(table)).scalar()
            for table in tables
        ]
    logger.info(
        "build_db 完成: instances={} instance_ports={} signals={} blocks={} "
        "dep_edges={} 丢弃边={}",
        *counts,
        dropped_edges,
    )
