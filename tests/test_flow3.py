"""流程③ sqlite 落库 — 单元测试

行为契约:doc/flow3_design_spec.md(build_db 公开 API 与 6 表 + 5 索引)。
目标模块:src/build_db.py(一级函数 build_db)与 src/datatypes.py(数据模型);
表元数据共享文件 src/schema.py 不直接 import —— 测试用标准库 sqlite3 查询
落地库(sqlite_master/pragma)独立核验,不读取 src/ 实现逻辑。
主路径端到端:仓库 test/*.sv → extract_design → build_db → sqlite3 断言;
仅错误路径(违反 flow2 契约的输入)用最小手构 dataclass 触发。
"""

from functools import lru_cache
from pathlib import Path
import sqlite3

import pytest

from build_db import build_db
from datatypes import (
    BlockInfo,
    DepEdge,
    InstanceInfo,
    ParseResult,
    PortInfo,
    SignalInfo,
)
from extract import extract_design


# ── 仓库 SV 素材定位与共享提取 ────────────────────────────────────

_TEST_ROOT = Path(__file__).resolve().parent.parent / "test"


def _file(*parts: str) -> str:
    """按 test/ 目录下的相对路径返回规范化绝对路径。"""
    return str(_TEST_ROOT.joinpath(*parts).resolve())


def _sv_files(rel_dir: str) -> list[str]:
    """返回 rel_dir 下全部 .sv 文件的绝对路径(排序,保证确定性)。"""
    return sorted(str(p) for p in (_TEST_ROOT / rel_dir).glob("*.sv"))


@lru_cache(maxsize=None)
def _extract_cached(rel_dir: str) -> ParseResult:
    """对 test/ 下某目录的全部 .sv 做一次 extract_design 并缓存(测试只读)。"""
    return extract_design(_sv_files(rel_dir))


def _mini_result() -> ParseResult:
    """test/flow3/mini.sv 的 ParseResult(与 flow3 spec §1.4 推演对应)。"""
    return extract_design([_file("flow3/mini.sv")])


@lru_cache(maxsize=None)
def _mini_cached() -> ParseResult:
    """mini 的 ParseResult 缓存,避免每测试重复编译。"""
    return _mini_result()


# ── sqlite3 断言辅助 ──────────────────────────────────────────────

_TABLES = ("instances", "instance_ports", "signals", "blocks", "dep_edges")
_INDEXES = (
    "idx_edges_unique",
    "idx_edges_driven",
    "idx_edges_read",
    "idx_signals_name",
    "idx_signals_inst",
)


def _db_rows(db_path: str, sql: str, params: tuple = ()) -> list[tuple]:
    """以 sqlite3 执行查询,返回按行元组展开的结果。"""
    with sqlite3.connect(db_path) as conn:
        return list(conn.execute(sql, params))


def _db_columns(db_path: str) -> dict[str, list[str]]:
    """返回 {表名: [列名, ...]},仅统计 _TABLES 内的表。"""
    rows = _db_rows(db_path, "SELECT name FROM sqlite_master WHERE type='table'")
    names = {r[0] for r in rows}
    columns: dict[str, list[str]] = {}
    for table in _TABLES:
        if table in names:
            columns[table] = [r[1] for r in _db_rows(db_path, f"PRAGMA table_info({table})")]
    return columns


def _row_counts(db_path: str) -> list[int]:
    """按 spec §1.3 表序返回 5 张业务表的行数。"""
    return [len(_db_rows(db_path, f"SELECT * FROM {table}")) for table in _TABLES]


def _ids(db_path: str, table: str, column: str = "id") -> list[int]:
    """返回表内指定列的全部值(按行物理序,便于断言显式 id 序列)。"""
    return [r[0] for r in _db_rows(db_path, f"SELECT {column} FROM {table} ORDER BY {column}")]


def _assert_empty_after(db_path: str) -> None:
    """断言建库结构完好但 5 张业务表均为空(事务回滚后的库状态)。"""
    assert _db_columns(db_path).keys() == set(_TABLES)
    assert _row_counts(db_path) == [0, 0, 0, 0, 0]


def _assert_edges_resolve(db_path: str, result: ParseResult) -> None:
    """spec §5 规则 10/§4.4:库内每条边两端都能 JOIN 回 signals。"""
    rows = _db_rows(
        db_path,
        "SELECT driven_signal_id, read_signal_id FROM dep_edges "
        "WHERE driven_signal_id NOT IN (SELECT id FROM signals) "
        "OR read_signal_id NOT IN (SELECT id FROM signals)",
    )
    assert rows == []
    assert len(_db_rows(db_path, "SELECT * FROM dep_edges")) == len(result.dep_edges)


def _assert_ids_sequence(db_path: str) -> None:
    """spec §5 规则 11:instances/signals/dep_edges 的 id 均为 1..N 连续。"""
    for table in ("instances", "signals", "dep_edges"):
        count = len(_db_rows(db_path, f"SELECT * FROM {table}"))
        assert _ids(db_path, table) == list(range(1, count + 1))


# ── 最小 ParseResult 构造(仅错误路径与 block=None 场景) ──────────


def _inst(path: str, depth: int = 1) -> InstanceInfo:
    """构造最小 InstanceInfo(无端口)。"""
    return InstanceInfo(path=path, name=path.rsplit(".", 1)[-1],
                        module_name="m", depth=depth,
                        file="/tmp/x.sv", ports=[])


def _sig(instance_path: str, full_path: str) -> SignalInfo:
    """构造最小 SignalInfo(非端口变量)。"""
    name = full_path.rsplit(".", 1)[-1]
    return SignalInfo(instance_path=instance_path, full_path=full_path, name=name,
                      type_name="logic", bit_width=1, kind="variable", is_port=False,
                      direction="", definition_file="/tmp/x.sv", definition_line=1)


def _block(index: int, instance_path: str = "mini") -> BlockInfo:
    """构造最小 BlockInfo。"""
    return BlockInfo(instance_path=instance_path, index=index, block_type="assign",
                     source_file="/tmp/x.sv", start_line=1, end_line=1,
                     source_text="assign x = y;")


def _edge(driven: str, read: str, block: BlockInfo | None,
          is_condition: bool = False, is_port_conn: bool = False) -> DepEdge:
    """构造最小 DepEdge(两端 full_path)。"""
    return DepEdge(driven_signal=driven, read_signal=read, block=block,
                   is_condition=is_condition, is_port_conn=is_port_conn)


def _parse(instances: list[InstanceInfo], signals: list[SignalInfo],
           blocks: list[BlockInfo], edges: list[DepEdge]) -> ParseResult:
    """按四列表构造 ParseResult。"""
    return ParseResult(instances=instances, signals=signals, blocks=blocks,
                       dep_edges=edges)


def _mini_parse() -> ParseResult:
    """空实例 + 单信号 + 无块边的 ParseResult,供 block=None 场景。"""
    sig = _sig("mini", "mini.a")
    return _parse([_inst("mini")], [sig], [], [_edge("mini.a", "mini.a", None)])


# ── 建库与运行辅助 ───────────────────────────────────────────────


def _build_at(tmp_path: Path, rel: str, result: ParseResult) -> str:
    """在 tmp_path 下建库并返回绝对路径。"""
    db_path = str(tmp_path / rel)
    assert build_db(result, db_path) is None
    return db_path


def _assert_warning(records: list[dict], keyword: str) -> None:
    """断言存在一条 WARNING 日志,消息含给定关键词。"""
    warns = [r["message"] for r in records if r["level"].name == "WARNING"]
    assert any(keyword in m for m in warns), f"WARNING 未含 {keyword}: {warns}"


# ── 表结构 ────────────────────────────────────────────────────────


class TestSchema:
    """spec §4/§5 规则 3:6 表 + 5 索引,列与约束齐全,无多余表。"""

    def test_六张业务表齐全(self, tmp_path):
        db = _build_at(tmp_path, "s.db", _mini_parse())
        assert set(_db_columns(db)) == set(_TABLES)

    def test_表列清单与spec一致(self, tmp_path):
        db = _build_at(tmp_path, "s.db", _mini_parse())
        columns = _db_columns(db)
        assert columns["instances"] == ["id", "path", "name", "module_name",
                                        "parent_id", "depth", "file"]
        assert columns["instance_ports"] == ["instance_id", "position", "name",
                                             "direction", "bit_width"]
        assert columns["signals"] == ["id", "instance_id", "name", "full_path",
                                      "type_name",
                                      "bit_width", "kind", "is_port", "direction",
                                      "definition_file", "definition_line"]
        assert columns["blocks"] == ["id", "instance_id", "block_type", "source_file",
                                     "start_line", "end_line", "source_text"]
        assert columns["dep_edges"] == ["id", "driven_signal_id", "read_signal_id",
                                        "block_id", "is_condition", "is_port_conn"]

    def test_五个索引齐全且唯一索引为表达式索引(self, tmp_path):
        db = _build_at(tmp_path, "s.db", _mini_parse())
        rows = _db_rows(db, "SELECT name, sql FROM sqlite_master WHERE type='index' "
                            "AND name NOT LIKE 'sqlite_autoindex%'")
        index_map = {r[0]: (r[1] or "") for r in rows}
        assert set(index_map) == set(_INDEXES)
        assert "coalesce" in index_map["idx_edges_unique"].lower()
        assert "UNIQUE" in index_map["idx_edges_unique"]

    def test_无多余业务表(self, tmp_path):
        db = _build_at(tmp_path, "s.db", _mini_parse())
        rows = _db_rows(db, "SELECT name FROM sqlite_master WHERE type='table'")
        extra = {r[0] for r in rows} - set(_TABLES)
        assert extra <= {"sqlite_sequence"}  # 仅允许 sqlite 自留表


# ── mini 端到端全表推演 ───────────────────────────────────────────


class TestMiniExample:
    """spec §1.4:mini.sv 端到端建库,固化全表行与 id 映射。"""

    def test_各表行数与id序列(self, tmp_path):
        db = _build_at(tmp_path, "mini.db", _mini_result())
        assert _row_counts(db) == [1, 3, 4, 2, 4]
        assert _ids(db, "instances") == [1]
        assert _ids(db, "signals") == [1, 2, 3, 4]
        assert _ids(db, "blocks") == [1, 2]
        assert _ids(db, "dep_edges") == [1, 2, 3, 4]

    def test_instances行(self, tmp_path):
        db = _build_at(tmp_path, "mini.db", _mini_result())
        assert _db_rows(db, "SELECT * FROM instances") == [
            (1, "mini", "mini", "mini", None, 1, _file("flow3/mini.sv")),
        ]

    def test_instance_ports按声明序(self, tmp_path):
        db = _build_at(tmp_path, "mini.db", _mini_result())
        assert _db_rows(db, "SELECT instance_id, position, name, direction, bit_width "
                            "FROM instance_ports ORDER BY position") == [
            (1, 0, "clk", "input", 1),
            (1, 1, "a", "input", 4),
            (1, 2, "y", "output", 4),
        ]

    def test_signals行(self, tmp_path):
        db = _build_at(tmp_path, "mini.db", _mini_result())
        result = _mini_cached()
        rows = _db_rows(db, "SELECT * FROM signals ORDER BY id")
        assert len(rows) == len(result.signals) == 4
        for position, signal in enumerate(result.signals, 1):
            assert rows[position - 1][:4] == (position, 1, signal.name, signal.full_path)
            assert rows[position - 1][4:7] == (signal.type_name, signal.bit_width, signal.kind)
            assert rows[position - 1][7:9] == (int(signal.is_port), signal.direction)
            assert rows[position - 1][9:11] == (signal.definition_file, signal.definition_line)

    def test_blocks行(self, tmp_path):
        db = _build_at(tmp_path, "mini.db", _mini_cached())
        rows = _db_rows(db, "SELECT id, instance_id, block_type, start_line, "
                            "end_line, source_text FROM blocks ORDER BY id")
        assert [(r[0], r[2]) for r in rows] == [(1, "assign"), (2, "always_ff")]
        assert all(r[1] == 1 for r in rows)
        for block in _mini_cached().blocks:
            row = rows[block.index]
            assert (row[3], row[4], row[5]) == (
                block.start_line, block.end_line, block.source_text,
            )

    def test_dep_edges行(self, tmp_path):
        db = _build_at(tmp_path, "mini.db", _mini_result())
        assert _db_rows(db, "SELECT * FROM dep_edges ORDER BY id") == [
            (1, 3, 2, 1, 0, 0),  # y ← a
            (2, 3, 4, 1, 0, 0),  # y ← b
            (3, 4, 2, 2, 0, 0),  # b ← a
            (4, 4, 1, 2, 1, 0),  # b ← clk(门控)
        ]

    def test_同块多边共享block_id(self, tmp_path):
        db = _build_at(tmp_path, "mini.db", _mini_result())
        y_edges = _db_rows(db, "SELECT DISTINCT block_id FROM dep_edges "
                               "WHERE driven_signal_id = 3")
        b_edges = _db_rows(db, "SELECT DISTINCT block_id FROM dep_edges "
                               "WHERE driven_signal_id = 4")
        assert y_edges == [(1,)]
        assert b_edges == [(2,)]


# ── 层次树与信号落库 ─────────────────────────────────────────────


class TestHierarchyAndSignals:
    """spec §4.1/§4.2/§8:parent_id 反查、同模块多实例、struct 字段行。"""

    def test_多级DFS实例parent与depth(self, tmp_path):
        result = _extract_cached("with_instance")
        db = _build_at(tmp_path, "alu.db", result)
        rows = _db_rows(db, "SELECT id, path, name, module_name, parent_id, depth "
                            "FROM instances ORDER BY id")
        by_path = {r[1]: r for r in rows}
        assert [r[5] for r in rows] == [i.depth for i in result.instances]
        assert by_path["alu_system"][4] is None
        assert by_path["alu_system.u_core"][4] == by_path["alu_system"][0]
        assert by_path["alu_system.u_core.u_adder"][4] == by_path["alu_system.u_core"][0]
        assert by_path["alu_system.u_core.u_logic"][4] == by_path["alu_system.u_core"][0]
        assert len(rows) == len(result.instances)

    def test_同模块多处实例化parent各归其位(self, tmp_path):
        result = extract_design([_file("flow2_edge/dup_leaf.sv"),
                                 _file("flow2_edge/dup_top.sv")])
        db = _build_at(tmp_path, "dup.db", result)
        rows = _db_rows(db, "SELECT id, path, parent_id FROM instances ORDER BY id")
        top_id = rows[0][0]
        assert rows == [
            (1, "dup_top", None),
            (2, "dup_top.u1", top_id),
            (3, "dup_top.u2", top_id),
        ]

    def test_同名信号不同实例各自成行且full_path唯一(self, tmp_path):
        result = extract_design([_file("flow2_edge/dup_leaf.sv"),
                                 _file("flow2_edge/dup_top.sv")])
        db = _build_at(tmp_path, "dup.db", result)
        rows = _db_rows(db, "SELECT full_path FROM signals ORDER BY full_path")
        assert ("dup_top.u1.a",) in rows and ("dup_top.u2.a",) in rows
        full_paths = [r[0] for r in rows]
        assert len(full_paths) == len(set(full_paths))

    def test_signals行数等于ParseResult列表长且id连续(self, tmp_path):
        for rel in ("with_instance", "with_struct"):
            result = _extract_cached(rel)
            db = _build_at(tmp_path, f"{rel}.db", result)
            assert len(_db_rows(db, "SELECT * FROM signals")) == len(result.signals)
            _assert_ids_sequence(db)

    def test_struct字段与definition列持久化(self, tmp_path):
        result = extract_design([_file("with_struct/csr_pkg.sv"),
                                 _file("with_struct/csr_regfile.sv")])
        db = _build_at(tmp_path, "csr.db", result)
        base = next(r for r in _db_rows(db, "SELECT * FROM signals WHERE full_path = "
                                            "'csr_regfile.cfg_reg'"))
        field = next(r for r in _db_rows(db, "SELECT * FROM signals WHERE full_path = "
                                             "'csr_regfile.cfg_reg.baud.div'"))
        assert field[6] == "field"  # kind
        assert field[9] == base[9] and field[10] == base[10]  # definition 继承
        assert field[8] == "" and field[7] == 0  # 非端口 direction/is_port

    def test_端口方向标志位落库(self, tmp_path):
        result = extract_design([_file("smoke/simple_alu.sv")])
        db = _build_at(tmp_path, "alu.db", result)
        port_row = next(r for r in _db_rows(db, "SELECT * FROM signals "
                                                "WHERE full_path = 'simple_alu.a'"))
        var_row = next(r for r in _db_rows(db, "SELECT * FROM signals "
                                               "WHERE full_path = 'simple_alu.add_sub_result'"))
        assert port_row[7] == 1 and port_row[8] == "input"
        assert var_row[7] == 0 and var_row[8] == ""


# ── 赋值块与依赖边 ───────────────────────────────────────────────


class TestBlocksAndEdges:
    """spec §4.3/§4.4/§5 规则 9–10:块 id、端口连接边、自依赖与条件边。"""

    def test_实例端口表对应各实例端口数(self, tmp_path):
        result = _extract_cached("with_instance")
        db = _build_at(tmp_path, "alu.db", result)
        expected_ports = sum(len(i.ports) for i in result.instances)
        assert len(_db_rows(db, "SELECT * FROM instance_ports")) == expected_ports
        assert len(_db_rows(db, "SELECT * FROM blocks")) == len(result.blocks)

    def test_端口连接边归属父实例且is_port_conn(self, tmp_path):
        result = _extract_cached("with_instance")
        db = _build_at(tmp_path, "alu.db", result)
        rows = _db_rows(db, "SELECT e.driven_signal_id, e.read_signal_id, e.block_id, "
                            "e.is_port_conn, b.instance_id, b.block_type "
                            "FROM dep_edges e JOIN blocks b ON b.id = e.block_id "
                            "WHERE e.is_port_conn = 1")
        assert rows
        assert all(r[3] == 1 and r[5] == "port_connection" for r in rows)
        instance_ids = {r[0] for r in _db_rows(db, "SELECT id FROM instances")}
        assert {r[4] for r in rows} <= instance_ids

    def test_边端信号与块id全解析(self, tmp_path):
        for rel in ("with_instance", "with_struct"):
            result = _extract_cached(rel)
            db = _build_at(tmp_path, f"{rel}.db", result)
            _assert_edges_resolve(db, result)
            rows = _db_rows(db, "SELECT block_id FROM dep_edges")
            assert all(r[0] is not None for r in rows)  # real 数据无 block=None

    def test_复合赋值自依赖边(self, tmp_path):
        result = extract_design([_file("flow2_edge/compound.sv")])
        db = _build_at(tmp_path, "compound.db", result)
        rows = _db_rows(db, "SELECT driven_signal_id, read_signal_id, is_condition, "
                            "is_port_conn FROM dep_edges")
        sig = {r[1]: r[0] for r in _db_rows(db, "SELECT id, full_path FROM signals")}
        assert (sig["compound_edge.acc"], sig["compound_edge.acc"], 0, 0) in rows

    def test_循环块门控与自依赖边(self, tmp_path):
        result = extract_design([_file("flow2_edge/loop_array.sv")])
        db = _build_at(tmp_path, "loop.db", result)
        rows = set(_db_rows(db, "SELECT driven_signal_id, read_signal_id, is_condition, "
                                "is_port_conn FROM dep_edges"))
        sig = {r[1]: r[0] for r in _db_rows(db, "SELECT id, full_path FROM signals")}
        pre = "loop_array_edge."
        assert (sig[pre + "i"], sig[pre + "clk"], 1, 0) in rows
        assert (sig[pre + "i"], sig[pre + "i"], 0, 0) in rows
        assert (sig[pre + "q"], sig[pre + "d"], 0, 0) in rows

    def test_block为空时落NULL(self, tmp_path):
        result = _mini_parse()
        db = _build_at(tmp_path, "nullblock.db", result)
        assert _db_rows(db, "SELECT block_id FROM dep_edges") == [(None,)]


# ── 流程④查询模式推演(spec §6)────────────────────────────────────


class TestQueryPatterns:
    """spec §6:以 mini 库推演变量信息/赋值块/load/driver 四种查询。"""

    def _mini_db(self, tmp_path) -> str:
        return _build_at(tmp_path, "q.db", _mini_result())

    def test_变量信息按full_path(self, tmp_path):
        db = self._mini_db(tmp_path)
        rows = _db_rows(db, "SELECT * FROM signals WHERE full_path = ?", ("mini.b",))
        assert rows and rows[0][2] == "b" and rows[0][3] == "mini.b"
        assert rows[0][5] == 4 and rows[0][9] == _file("flow3/mini.sv")

    def test_赋值块按driven信号JOIN(self, tmp_path):
        db = self._mini_db(tmp_path)
        rows = _db_rows(db, "SELECT DISTINCT b.* FROM dep_edges e "
                            "JOIN blocks b ON b.id = e.block_id "
                            "WHERE e.driven_signal_id = "
                            "(SELECT id FROM signals WHERE full_path = 'mini.b')")
        assert len(rows) == 1 and rows[0][2] == "always_ff"

    def test_load按read信号(self, tmp_path):
        db = self._mini_db(tmp_path)
        rows = _db_rows(db, "SELECT s.full_path FROM dep_edges e "
                            "JOIN signals s ON s.id = e.driven_signal_id "
                            "WHERE e.read_signal_id = "
                            "(SELECT id FROM signals WHERE full_path = 'mini.a')")
        assert {r[0] for r in rows} == {"mini.y", "mini.b"}

    def test_driver按driven信号(self, tmp_path):
        db = self._mini_db(tmp_path)
        rows = _db_rows(db, "SELECT s.full_path FROM dep_edges e "
                            "JOIN signals s ON s.id = e.read_signal_id "
                            "WHERE e.driven_signal_id = "
                            "(SELECT id FROM signals WHERE full_path = 'mini.b')")
        assert {r[0] for r in rows} == {"mini.a", "mini.clk"}


# ── 确定性与重建语义 ─────────────────────────────────────────────


class TestDeterminismAndRebuild:
    """spec §5 规则 1/11/12、§7:删除重建、空输入合法、双跑可复现。"""

    def test_同输入两次建库行列一致(self, tmp_path):
        result = _extract_cached("with_instance")
        db1 = _build_at(tmp_path, "a.db", result)
        db2 = _build_at(tmp_path, "b.db", result)
        assert _db_rows(db1, "SELECT * FROM dep_edges") == \
            _db_rows(db2, "SELECT * FROM dep_edges")
        assert _db_rows(db1, "SELECT * FROM signals") == \
            _db_rows(db2, "SELECT * FROM signals")

    def test_已存在dbPath删除重建(self, tmp_path):
        db = str(tmp_path / "rebuild.db")
        Path(db).write_text("old sqlite junk", encoding="utf-8")
        assert build_db(_mini_result(), db) is None
        assert _row_counts(db) == [1, 3, 4, 2, 4]
        assert Path(db).stat().st_size > 0

    def test_空ParseResult建六张空表(self, tmp_path):
        db = _build_at(tmp_path, "empty.db", ParseResult([], [], [], []))
        assert _db_columns(db).keys() == set(_TABLES)
        assert _row_counts(db) == [0, 0, 0, 0, 0]
        assert _db_rows(db, "SELECT name FROM sqlite_master WHERE type='index'") != []


# ── 错误与回滚 ───────────────────────────────────────────────────


class TestErrorsAndRollback:
    """spec §7/§5 规则 6/8/10:错误直抛、告警丢弃、单事务回滚。"""

    def test_不存在父目录直接抛出(self, tmp_path):
        missing = str(tmp_path / "no_dir" / "x.db")
        with pytest.raises(Exception):
            build_db(_mini_result(), missing)
        assert not Path(missing).exists()

    def test_instancePath不在映射KeyError且回滚(self, tmp_path):
        db = str(tmp_path / "orphan.db")
        result = _parse([_inst("mini")], [_sig("ghost", "ghost.a")], [], [])
        with pytest.raises(KeyError):
            build_db(result, db)
        _assert_empty_after(db)

    def test_父实例缺失KeyError且回滚(self, tmp_path):
        db = str(tmp_path / "parent.db")
        result = _parse([_inst("a.b", depth=2)], [], [], [])
        with pytest.raises(KeyError):
            build_db(result, db)
        _assert_empty_after(db)

    def test_边block对象不在blocksKeyError且回滚(self, tmp_path):
        db = str(tmp_path / "block.db")
        sig = _sig("mini", "mini.a")
        orphan_block = _block(7)
        result = _parse([_inst("mini")], [sig], [_block(0)],
                        [_edge("mini.a", "mini.a", orphan_block)])
        with pytest.raises(KeyError):
            build_db(result, db)
        _assert_empty_after(db)

    def test_重复fullPathIntegrityError且回滚(self, tmp_path):
        db = str(tmp_path / "dup_sig.db")
        result = _parse([_inst("mini")], [_sig("mini", "mini.a"), _sig("mini", "mini.a")],
                        [], [])
        with pytest.raises(Exception):
            build_db(result, db)
        _assert_empty_after(db)

    def test_重复边含NULLblock唯一索引拦截(self, tmp_path):
        db = str(tmp_path / "dup_edge.db")
        sig = _sig("mini", "mini.a")
        edge = _edge("mini.a", "mini.a", None)
        result = _parse([_inst("mini")], [sig], [], [edge, edge])
        with pytest.raises(Exception):
            build_db(result, db)
        _assert_empty_after(db)


# ── 日志 ─────────────────────────────────────────────────────────


class TestLogs:
    """spec §5 规则 10/12:汇总 INFO 与边丢弃 WARNING 均经 loguru。"""

    def test_汇总INFO含各表计数与丢弃数(self, tmp_path, log_records):
        db = _build_at(tmp_path, "log.db", _mini_result())
        infos = [r["message"] for r in log_records if r["level"].name == "INFO"]
        assert infos and "instances=1" in infos[-1]
        assert "instance_ports=3" in infos[-1] and "signals=4" in infos[-1]
        assert "blocks=2" in infos[-1] and "dep_edges=4" in infos[-1]
        assert "丢弃边=0" in infos[-1]
        assert Path(db).exists()

    def test_孤儿信号边WARNING并丢弃(self, tmp_path, log_records):
        db = str(tmp_path / "drop.db")
        sig = _sig("mini", "mini.a")
        good = _edge("mini.a", "mini.a", None)
        orphan = _edge("mini.a", "mini.missing", None)
        result = _parse([_inst("mini")], [sig], [], [good, orphan])
        assert build_db(result, db) is None
        assert _db_rows(db, "SELECT * FROM dep_edges") == [(1, 1, 1, None, 0, 0)]
        infos = [r["message"] for r in log_records if r["level"].name == "INFO"]
        assert "丢弃边=1" in infos[-1]
        _assert_warning(log_records, "mini.missing")
