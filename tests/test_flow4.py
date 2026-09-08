"""流程④ API 查询 — 单元测试

行为契约:doc/flow4_design_spec.md(四大查询函数 get_variable_info /
get_assignment_blocks / trace_load / trace_driver,只读查询流程③产出的
sqlite 库)。目标模块:src/query.py(四个公开函数);DB 由仓库 test/*.sv 经
extract_design → build_db 端到端构建(与 tests/test_flow3.py 同一套真实素材),
spec §5.2 的合成推演与 §8 的少数边界(下划线转义、NULL block 端口边)按
spec 示例以最小手构 ParseResult 触发;测试不读取 src/ 实现逻辑,期望值全部
按 spec 语义从 SV 素材独立推算/按行读取固定素材计算(与 test_flow2 同手法)。
mini.sv 各字段的物理行号以素材文件实际行位置为准(素材头部注释行随仓库演化,
flow2/flow3 spec §1.4 示例行号比素材早 4 行,故定义行/块行按文件行推算)。

覆盖:spec §1.3/§1.4(类型反序列化与四功能 mini 推演)、§4(四种 SQL 查询
模式)、§5.1(端口连接边方向映射)、§5.2(base↔field 合并)、§5.3(条件读
包含)、§6 规则 3/5/6/8(错误前置、排序去重、instance_path 取 join)、
§7(错误处理)、§8(边界情况)。
"""

import sqlite3
from functools import lru_cache
from pathlib import Path

import pytest
from sqlalchemy.exc import DatabaseError, OperationalError

from build_db import build_db
from datatypes import (
    BlockInfo,
    DepEdge,
    InstanceInfo,
    ParseResult,
    SignalInfo,
)
from extract import extract_design
from query import (
    get_assignment_blocks,
    get_variable_info,
    trace_driver,
    trace_load,
)


# ── 仓库 SV 素材定位、共享提取与建库 ─────────────────────────────


_TEST_ROOT = Path(__file__).resolve().parent.parent / "test"


def _file(*parts: str) -> str:
    """按 test/ 目录下的相对路径返回规范化绝对路径。"""
    return str(_TEST_ROOT.joinpath(*parts).resolve())


def _read_lines(path: str) -> list[str]:
    """按行读取固定 SV 素材(供 source_text / definition_line 期望推算)。"""
    return Path(path).read_text(encoding="utf-8").splitlines()


@lru_cache(maxsize=None)
def _cached_parse(sv_files: tuple[str, ...]) -> ParseResult:
    """对素材相对路径元组做一次 extract_design 并缓存(测试只读)。"""
    return extract_design([_file(p) for p in sv_files])


def _mini_result() -> ParseResult:
    """mini.sv 的 ParseResult(flow3 spec §1.4/flow4 spec §1.4 推演对应)。"""
    return _cached_parse(("flow3/mini.sv",))


@lru_cache(maxsize=None)
def _with_instance_files() -> tuple[str, ...]:
    """with_instance 目录全部 .sv 相对路径(排序,与 flow3 同一取法)。"""
    return tuple(sorted(f"with_instance/{p.name}"
                        for p in (_TEST_ROOT / "with_instance").glob("*.sv")))


def _alu_result() -> ParseResult:
    """with_instance 全套素材的 ParseResult(alu 层次,flow2 fixture)。"""
    return _cached_parse(_with_instance_files())


def _csr_result() -> ParseResult:
    """csr_pkg + csr_regfile 的 ParseResult(嵌套 struct 真实素材)。"""
    return _cached_parse(("with_struct/csr_pkg.sv", "with_struct/csr_regfile.sv"))


def _build_db(tmp_path: Path, name: str, result: ParseResult) -> str:
    """在 tmp_path 下以 result 建库,返回库文件绝对路径。"""
    db_path = str(tmp_path / name)
    assert build_db(result, db_path) is None
    return db_path


def _def_line(rel: str, needle: str) -> int:
    """返回素材文件中首个含 needle 的物理行号(1 起),供定义行期望推算。"""
    lines = _read_lines(_file(rel))
    for i, line in enumerate(lines, 1):
        if needle in line:
            return i
    raise AssertionError(f"{rel} 中未找到含 {needle!r} 的行")


def _source_text(rel: str, start: int, end: int) -> str:
    """素材文件 start..end 行范围的原始源文本(与 flow2 §1.6 块文本语义一致)。"""
    return "\n".join(_read_lines(_file(rel))[start - 1:end])


# ── 最小 ParseResult 构造(合成推演与边界场景) ────────────────────


def _inst(path: str, depth: int = 1, module_name: str | None = None) -> InstanceInfo:
    """构造最小 InstanceInfo(无端口)。"""
    return InstanceInfo(path=path, name=path.rsplit(".", 1)[-1],
                        module_name=module_name or path.rsplit(".", 1)[-1],
                        depth=depth, file="/tmp/x.sv", ports=[])


def _sig(instance_path: str, full_path: str, kind: str = "variable") -> SignalInfo:
    """构造最小 SignalInfo(非端口变量)。"""
    return SignalInfo(instance_path=instance_path, full_path=full_path,
                      name=full_path.rsplit(".", 1)[-1], type_name="logic",
                      bit_width=1, kind=kind, is_port=False, direction="",
                      definition_file="/tmp/x.sv", definition_line=1)


def _block(index: int, instance_path: str, block_type: str = "assign",
           text: str = "assign x = y;") -> BlockInfo:
    """构造最小 BlockInfo(文本区分各块,供等值断言辨认 id 映射)。"""
    return BlockInfo(instance_path=instance_path, index=index,
                     block_type=block_type, source_file="/tmp/x.sv",
                     start_line=1, end_line=1, source_text=text)


def _edge(driven: str, read: str, block: BlockInfo | None,
          is_condition: bool = False, is_port_conn: bool = False) -> DepEdge:
    """构造最小 DepEdge(两端 full_path)。"""
    return DepEdge(driven_signal=driven, read_signal=read, block=block,
                   is_condition=is_condition, is_port_conn=is_port_conn)


def _struct_parse() -> ParseResult:
    """spec §5.2 合成示例 s.sv 的 ParseResult(整 struct 赋值/字段写/字段读)。

    库节选(与 spec §5.2 推演逐行对应):signals 含 s.cfg_reg(基行)/
    s.cfg_reg.div/s.cfg_reg.en(字段行);边 (s.cfg_reg, s.other_cfg, 块0)、
    (s.cfg_reg.en, s.en_in, 块1)、(s.y, s.cfg_reg.div, 块2)。
    """
    inst = _inst("s")
    sigs = [_sig("s", "s.cfg_reg"), _sig("s", "s.cfg_reg.div"),
            _sig("s", "s.cfg_reg.en"), _sig("s", "s.other_cfg"),
            _sig("s", "s.en_in"), _sig("s", "s.y")]
    blk0 = _block(0, "s", text="assign cfg_reg = other_cfg;")
    blk1 = _block(1, "s", block_type="always_comb", text="cfg_reg.en = en_in;")
    blk2 = _block(2, "s", text="assign y = cfg_reg.div;")
    edges = [_edge("s.cfg_reg", "s.other_cfg", blk0),
             _edge("s.cfg_reg.en", "s.en_in", blk1),
             _edge("s.y", "s.cfg_reg.div", blk2)]
    return ParseResult([inst], sigs, [blk0, blk1, blk2], edges)


def _underscore_parse() -> ParseResult:
    """含 '_' 信号名的合成 ParseResult,供 §5.2 LIKE 转义边界场景。

    库:s.b_2 与 s.bX2 为两个并列 struct(均带字段行),X 恰在 '_' 同位置;
    不转义时 LIKE 's.b_2.%' 会把 s.bX2.hi 误并入匹配集(spec §5.2)。
    """
    inst = _inst("u")
    sigs = [_sig("u", "u.b_2"), _sig("u", "u.b_2.lo"),
            _sig("u", "u.bX2"), _sig("u", "u.bX2.hi"),
            _sig("u", "u.b_2_src"), _sig("u", "u.bX2_src"),
            _sig("u", "u.y"), _sig("u", "u.z")]
    blk0 = _block(0, "u", text="assign b_2 = b_2_src; assign bX2 = bX2_src;")
    blk1 = _block(1, "u", text="assign y = bX2.hi;")
    blk2 = _block(2, "u", text="assign z = b_2.lo;")
    edges = [_edge("u.b_2", "u.b_2_src", blk0),
             _edge("u.bX2", "u.bX2_src", blk0),
             _edge("u.y", "u.bX2.hi", blk1),
             _edge("u.z", "u.b_2.lo", blk2)]
    return ParseResult([inst], sigs, [blk0, blk1, blk2], edges)


def _nullblock_parse() -> ParseResult:
    """端口连接边 block=None 的合成 ParseResult(flow2 §5 规则 8 兜底场景)。

    库:实例 t(顶层)与 t.u;In 端口连接边 (t.p → t.u.p) 与 Out 边
    (t.u.q → t.q) 均 block=None;块内边 (t.u.q, t.u.p, 块0) 带真实块。
    """
    insts = [_inst("t", depth=1, module_name="top"),
             _inst("t.u", depth=2, module_name="sub")]
    sigs = [_sig("t", "t.p"), _sig("t.u", "t.u.p"),
            _sig("t.u", "t.u.q"), _sig("t", "t.q")]
    blk0 = _block(0, "t.u", block_type="always_comb", text="q = p;")
    edges = [_edge("t.p", "t.u.p", None, is_port_conn=True),
             _edge("t.u.q", "t.q", None, is_port_conn=True),
             _edge("t.u.q", "t.u.p", blk0)]
    return ParseResult(insts, sigs, [blk0], edges)


# ── mini 端到端四功能推演(spec §1.4/§4)──────────────────────────


class TestMiniEndToEnd:
    """spec §1.4/§4:以 mini 库推演四功能;期望行号按素材文件行推算。"""

    def test_变量信息mini_b整行等值(self, tmp_path):
        db = _build_db(tmp_path, "mini.db", _mini_result())
        b_line = _def_line("flow3/mini.sv", "logic [3:0] b;")
        expected = SignalInfo(instance_path="mini", full_path="mini.b", name="b",
                              type_name="logic[3:0]", bit_width=4, kind="variable",
                              is_port=False, direction="",
                              definition_file=_file("flow3/mini.sv"),
                              definition_line=b_line)
        assert get_variable_info(db, "mini.b") == expected

    def test_变量信息端口行is_port转布尔(self, tmp_path):
        db = _build_db(tmp_path, "mini.db", _mini_result())
        info = get_variable_info(db, "mini.a")
        assert info.instance_path == "mini"
        assert info.full_path == "mini.a" and info.name == "a"
        assert info.type_name == "logic[3:0]" and info.bit_width == 4
        assert info.kind == "port" and info.is_port is True
        assert info.direction == "input"
        assert info.definition_file == _file("flow3/mini.sv")

    def test_赋值块always_ff整行等值(self, tmp_path):
        db = _build_db(tmp_path, "mini.db", _mini_result())
        result = _mini_result()
        blocks = get_assignment_blocks(db, "mini.b")
        assert blocks == [result.blocks[1]]  # index 1 → id 2(roundtrip)
        ff_line = _def_line("flow3/mini.sv", "always_ff")
        assert blocks[0].index == 1 and blocks[0].block_type == "always_ff"
        assert blocks[0].start_line == ff_line and blocks[0].end_line == ff_line
        assert blocks[0].source_text == _source_text("flow3/mini.sv", ff_line, ff_line)

    def test_trace_load升序去重(self, tmp_path):
        db = _build_db(tmp_path, "mini.db", _mini_result())
        # 库内两条读 a 的边驱动 y(先)/b(后),结果按 full_path 升序(§6 规则 5)
        assert trace_load(db, "mini.a") == ["mini.b", "mini.y"]
        # 同输入 → 同输出(每次调用独立引擎,无缓存状态)
        assert trace_load(db, "mini.a") == trace_load(db, "mini.a")

    def test_trace_driver含条件读(self, tmp_path):
        db = _build_db(tmp_path, "mini.db", _mini_result())
        # b <= a 的块内边 + @(posedge clk) 门控边(is_condition=1,§5.3)
        assert trace_driver(db, "mini.b") == ["mini.a", "mini.clk"]

    def test_信号存在但无匹配边返回空列表(self, tmp_path):
        db = _build_db(tmp_path, "mini.db", _mini_result())
        # clk 从不被驱动(仅被读):driver/赋值块空;load 非空,证明非"变量不存在"
        assert trace_driver(db, "mini.clk") == []
        assert get_assignment_blocks(db, "mini.clk") == []
        assert trace_load(db, "mini.clk") == ["mini.b"]


# ── 端口连接边方向映射(spec §5.1,with_instance 真实素材)──────────


class TestPortConnDirection:
    """spec §5.1:同一张边表按边类型取相反方向列;端口连接边含块与结果。"""

    def test_load父信号穿透In边(self, tmp_path):
        db = _build_db(tmp_path, "alu.db", _alu_result())
        # In 边 (alu_system.opcode → alu_system.u_core.opcode):driven 命中取 read
        assert trace_load(db, "alu_system.opcode") == ["alu_system.u_core.opcode"]

    def test_driver子输入端口取In边driven侧(self, tmp_path):
        db = _build_db(tmp_path, "alu.db", _alu_result())
        # 同一边反向:read 命中取 driven —— 子输入端口内部信号的驱动者是父信号
        assert trace_driver(db, "alu_system.u_core.opcode") == ["alu_system.opcode"]

    def test_load子输出端口取Out边read侧(self, tmp_path):
        db = _build_db(tmp_path, "alu.db", _alu_result())
        # Out 边 (alu_system.u_core.result → alu_system.core_result)
        assert trace_load(db, "alu_system.u_core.result") == ["alu_system.core_result"]

    def test_driver父中间信号取Out边driven侧(self, tmp_path):
        db = _build_db(tmp_path, "alu.db", _alu_result())
        assert trace_driver(db, "alu_system.core_result") == ["alu_system.u_core.result"]

    def test_赋值块含端口连接边read侧(self, tmp_path):
        db = _build_db(tmp_path, "alu.db", _alu_result())
        # §4.2 端口连接边以 read 为被驱动侧:core_result 由 u_core 实例化连接驱动
        result = _alu_result()
        assert get_assignment_blocks(db, "alu_system.core_result") == \
            [result.blocks[2]]
        assert get_assignment_blocks(db, "alu_system.u_core.opcode") == \
            [result.blocks[2]]
        conn = result.blocks[2]
        assert conn.index == 2 and conn.block_type == "port_connection"
        assert conn.instance_path == "alu_system"
        assert conn.source_file == _file("with_instance/alu_system.sv")


# ── base↔field 层级合并(spec §5.2,合成推演 + 真实嵌套 struct)──────


class TestStructMergeSynthetic:
    """spec §5.2 推演表:整 struct 读/写与字段读/写互为依赖的四条固化。"""

    def test_driver基变量聚合全部字段写(self, tmp_path):
        db = _build_db(tmp_path, "s.db", _struct_parse())
        assert trace_driver(db, "s.cfg_reg") == ["s.en_in", "s.other_cfg"]

    def test_driver字段行含祖先整struct赋值(self, tmp_path):
        db = _build_db(tmp_path, "s.db", _struct_parse())
        assert trace_driver(db, "s.cfg_reg.div") == ["s.other_cfg"]

    def test_load基变量含字段读(self, tmp_path):
        db = _build_db(tmp_path, "s.db", _struct_parse())
        assert trace_load(db, "s.cfg_reg") == ["s.y"]

    def test_赋值块字段行含整struct赋值块(self, tmp_path):
        db = _build_db(tmp_path, "s.db", _struct_parse())
        expected = _struct_parse().blocks
        assert get_assignment_blocks(db, "s.cfg_reg.div") == [expected[0]]

    def test_赋值块基变量聚合字段写块且按块id升序(self, tmp_path):
        db = _build_db(tmp_path, "s.db", _struct_parse())
        expected = _struct_parse().blocks
        # 块 0(整 struct 赋值)+ 块 1(字段写),按块 id 升序(§6 规则 5)
        assert get_assignment_blocks(db, "s.cfg_reg") == [expected[0], expected[1]]

    def test_load字段行含整struct读与字段读(self, tmp_path):
        db = _build_db(tmp_path, "s.db", _struct_parse())
        # 边 2(y = cfg_reg.div)的 read 是 div 自身 → 字段的 load 含 y
        assert trace_load(db, "s.cfg_reg.div") == ["s.y"]


class TestStructMergeReal:
    """spec §5.2:嵌套 struct 真实素材(csr),祖先两级与多边同块去重。"""

    def test_driver基变量聚合两级字段写(self, tmp_path):
        db = _build_db(tmp_path, "csr.db", _csr_result())
        # 7 条字段写(读 wr_data)+ 门控(clk/rst_n/wr_en/addr)全并入基变量
        assert trace_driver(db, "csr_regfile.cfg_reg") == [
            "csr_regfile.addr", "csr_regfile.clk", "csr_regfile.rst_n",
            "csr_regfile.wr_data", "csr_regfile.wr_en",
        ]

    def test_driver两级深字段行聚合基行门控边(self, tmp_path):
        db = _build_db(tmp_path, "csr.db", _csr_result())
        # cfg_reg.baud.div 的祖先链含 cfg_reg.baud 与 cfg_reg:基行的 clk/rst_n
        # 门控边(重置分支)也算字段的驱动 → 与基变量结果一致
        assert trace_driver(db, "csr_regfile.cfg_reg.baud.div") == [
            "csr_regfile.addr", "csr_regfile.clk", "csr_regfile.rst_n",
            "csr_regfile.wr_data", "csr_regfile.wr_en",
        ]

    def test_load基变量聚合子结构读(self, tmp_path):
        db = _build_db(tmp_path, "csr.db", _csr_result())
        # 整 struct 读(assign csr_cfg_o/cfg_debug = cfg_reg,rd_data 基行分支)
        # 与子结构读(assign baud_cfg_o = cfg_reg.baud,rd_data 读 cfg_reg.irq)
        assert trace_load(db, "csr_regfile.cfg_reg") == [
            "csr_regfile.baud_cfg_o", "csr_regfile.cfg_debug",
            "csr_regfile.csr_cfg_o", "csr_regfile.irq_cfg_o",
            "csr_regfile.rd_data",
        ]

    def test_赋值块同块多边DISTINCT一行(self, tmp_path):
        db = _build_db(tmp_path, "csr.db", _csr_result())
        # 寄存器读 always_comb 内多次赋值 rd_data(2 RHS + 2 门控共 4 边同块)
        assert get_assignment_blocks(db, "csr_regfile.rd_data") == \
            [_csr_result().blocks[2]]

    def test_赋值块基变量聚合全部字段写块(self, tmp_path):
        db = _build_db(tmp_path, "csr.db", _csr_result())
        # 写寄存器 always_ff 的 7 条字段写 + 基行门控边 → 恰一行
        assert get_assignment_blocks(db, "csr_regfile.cfg_reg") == \
            [_csr_result().blocks[0]]

    def test_字段行变量信息instance_path取自join(self, tmp_path):
        db = _build_db(tmp_path, "csr.db", _csr_result())
        # §6 规则 8:instance_path 走 instances join,不按 full_path 前缀切分
        info = get_variable_info(db, "csr_regfile.cfg_reg.baud.div")
        assert info.instance_path == "csr_regfile"
        assert info.name == "div" and info.kind == "field"
        assert info.type_name == "logic[15:0]" and info.bit_width == 16
        assert info.is_port is False


# ── 边界情况(spec §8)──────────────────────────────────────────────


class TestLikeEscape:
    """spec §5.2/§8:信号名含 '_' 时后裔 LIKE 必须转义,不误并兄弟信号。"""

    def test_下划线变量聚合不误并同位置X信号(self, tmp_path):
        db = _build_db(tmp_path, "u.db", _underscore_parse())
        # 不转义时 'u.b_2.%' 会误配 'u.bX2.hi'(x 在 _ 同位置)
        assert trace_load(db, "u.b_2") == ["u.z"]       # 兄弟字段读不混入
        assert trace_driver(db, "u.b_2") == ["u.b_2_src"]
        assert trace_load(db, "u.bX2") == ["u.y"]       # 对称方向同样成立


class TestNullBlockPortConn:
    """spec §8:block=NULL 的端口连接边不现于赋值块查询,load/driver 不受影响。"""

    def test_driver与load经NULL块边正常返回(self, tmp_path):
        db = _build_db(tmp_path, "nb.db", _nullblock_parse())
        assert trace_driver(db, "t.u.p") == ["t.p"]     # In 边 read 命中取 driven
        assert trace_load(db, "t.p") == ["t.u.p"]       # In 边 driven 命中取 read

    def test_赋值块查询丢弃NULL块边(self, tmp_path):
        db = _build_db(tmp_path, "nb.db", _nullblock_parse())
        assert get_assignment_blocks(db, "t.u.p") == []  # 仅 NULL 块边 → 空

    def test_同变量真实块边仍可返回(self, tmp_path):
        db = _build_db(tmp_path, "nb.db", _nullblock_parse())
        # t.u.q 同时有 Out 连接边(NULL 块)与块内边(块 0),JOIN 后只余后者
        expected = _nullblock_parse().blocks
        assert get_assignment_blocks(db, "t.u.q") == [expected[0]]


class TestSelfDependency:
    """spec §8:自依赖边(driven == read)load/driver 均含自身(compound 素材)。"""

    def test_复合赋值自依赖两方向(self, tmp_path):
        db = _build_db(tmp_path, "compound.db", _cached_parse(("flow2_edge/compound.sv",)))
        assert trace_driver(db, "compound_edge.acc") == \
            ["compound_edge.acc", "compound_edge.b"]
        assert trace_load(db, "compound_edge.acc") == \
            ["compound_edge.acc", "compound_edge.q"]

    def test_自依赖边的赋值块仅算一次(self, tmp_path):
        db = _build_db(tmp_path, "compound.db", _cached_parse(("flow2_edge/compound.sv",)))
        result = _cached_parse(("flow2_edge/compound.sv",))
        assert get_assignment_blocks(db, "compound_edge.acc") == [result.blocks[0]]
        assert get_assignment_blocks(db, "compound_edge.q") == [result.blocks[1]]


# ── 错误处理(spec §7)──────────────────────────────────────────────


class TestErrors:
    """spec §7:db 不存在/非库文件/空库/变量不存在,异常按契约直接爆出。"""

    _FUNCS = (get_variable_info, get_assignment_blocks, trace_load, trace_driver)

    def test_db不存在FileNotFoundError(self, tmp_path):
        missing = str(tmp_path / "no_such.db")
        for fn in self._FUNCS:
            with pytest.raises(FileNotFoundError):
                fn(missing, "mini.b")

    def test_db路径是目录FileNotFoundError(self, tmp_path):
        # §6 规则 1 的 isfile 校验先于连接:目录同样按"不存在"报错
        for fn in self._FUNCS:
            with pytest.raises(FileNotFoundError):
                fn(str(tmp_path), "mini.b")

    def test_db非sqlite文件DatabaseError(self, tmp_path):
        junk = tmp_path / "junk.db"
        junk.write_text("not a sqlite database", encoding="utf-8")
        # sqlite3 对该情形报 "file is not a database"(DatabaseError 族)
        for fn in self._FUNCS:
            with pytest.raises(DatabaseError):
                fn(str(junk), "mini.b")

    def test_库内无signals表OperationalError(self, tmp_path):
        empty_sqlite = str(tmp_path / "blank.db")
        with sqlite3.connect(empty_sqlite) as conn:
            conn.execute("CREATE TABLE junk (x INTEGER)")
        for fn in self._FUNCS:
            with pytest.raises(OperationalError):
                fn(empty_sqlite, "mini.b")

    def test_变量不存在ValueError带路径(self, tmp_path):
        db = _build_db(tmp_path, "mini.db", _mini_result())
        for fn in self._FUNCS:
            with pytest.raises(ValueError, match=r"变量不存在: mini\.zzz"):
                fn(db, "mini.zzz")
        # 实例路径(非信号行)同样按变量不存在处理
        with pytest.raises(ValueError, match=r"变量不存在: mini"):
            get_variable_info(db, "mini")

    def test_空库任意查询ValueError(self, tmp_path):
        db = _build_db(tmp_path, "empty.db", ParseResult([], [], [], []))
        for fn in self._FUNCS:
            with pytest.raises(ValueError, match=r"变量不存在: x"):
                fn(db, "x")
