"""流程② pyslang 解析与信息提取 — 单元测试

行为契约:doc/flow2_design_spec.md(extract_* 五个公开函数及 ParseResult 数据模型)。
目标模块:src/extract.py(公开函数)与 src/datatypes.py(数据模型)。
测试仅通过公开 API 校验行为,不读取 src/ 实现代码;SV 输入全部来自仓库 test/。
"""

from pathlib import Path

import pytest

from datatypes import BlockInfo, DepEdge, InstanceInfo, ParseResult, PortInfo, SignalInfo
from extract import (
    extract_blocks,
    extract_dep_edges,
    extract_design,
    extract_hierarchy,
    extract_signals,
)


# ── 仓库 SV 素材定位 ──────────────────────────────────────────────

_TEST_ROOT = Path(__file__).resolve().parent.parent / "test"


def _file(*parts: str) -> str:
    """按 test/ 目录下的相对路径返回规范化绝对路径。"""
    return str(_TEST_ROOT.joinpath(*parts).resolve())


def _sv_files(rel_dir: str) -> list[str]:
    """返回 rel_dir 下全部 .sv 文件的绝对路径(排序,保证确定性)。"""
    return sorted(str(p) for p in (_TEST_ROOT / rel_dir).glob("*.sv"))


def _read_lines(path: str) -> list[str]:
    """按行读取固定 SV 素材(供 source_text / definition_line 期望推算)。"""
    return Path(path).read_text(encoding="utf-8").splitlines()


def _signal_map(signals: list[SignalInfo]) -> dict[str, SignalInfo]:
    """full_path → SignalInfo 映射。"""
    return {s.full_path: s for s in signals}


def _sig(edge: DepEdge) -> tuple[str, str, bool, bool]:
    """DepEdge → 不含块对象的语义键。"""
    return (edge.driven_signal, edge.read_signal, edge.is_condition, edge.is_port_conn)


def _sig_keys(edges: list[DepEdge]) -> set[tuple[str, str, bool, bool]]:
    """DepEdge 列表 → 语义键集合。"""
    return {_sig(e) for e in edges}


def _full_key(edge: DepEdge) -> tuple[str, str, int | None, bool, bool]:
    """DepEdge → 含块 index 的完整键(跨次编译可比,块身份仅限单次内)。"""
    return (edge.driven_signal, edge.read_signal, edge.block.index if edge.block else None,
            edge.is_condition, edge.is_port_conn)


def _full_keys(edges: list[DepEdge]) -> list[tuple[str, str, int | None, bool, bool]]:
    """DepEdge 列表 → 排序后的完整键列表。"""
    return sorted(_full_key(e) for e in edges)


def _warn_messages(records: list[dict]) -> list[str]:
    """取全部 WARNING 记录消息。"""
    return [r["message"] for r in records if r["level"].name == "WARNING"]


def _error_messages(records: list[dict]) -> list[str]:
    """取全部 ERROR 记录消息。"""
    return [r["message"] for r in records if r["level"].name == "ERROR"]


def _debug_messages(records: list[dict]) -> list[str]:
    """取全部 DEBUG 记录消息。"""
    return [r["message"] for r in records if r["level"].name == "DEBUG"]


def _assert_edges_resolve(result: ParseResult) -> None:
    """契约 §5.9:产出的边两端必须都命中信号表(full_path)。"""
    valid = {s.full_path for s in result.signals}
    for edge in result.dep_edges:
        assert edge.driven_signal in valid, edge
        assert edge.read_signal in valid, edge
        if edge.block is not None:
            assert isinstance(edge.block, BlockInfo)


def _assert_block_text(block: BlockInfo) -> None:
    """契约 §1.6/§5 规则 7:source_text 即源文件起止行范围文本。"""
    lines = _read_lines(block.source_file)
    expected = "\n".join(lines[block.start_line - 1:block.end_line])
    assert block.source_text == expected, block


def _alu_files() -> list[str]:
    """with_instance 全部文件(唯一顶层 alu_system)。"""
    return _sv_files("with_instance")


def _csr_pair() -> list[str]:
    """csr_pkg + csr_regfile,顶层为 csr_regfile(独立顶层)。"""
    return [_file("with_struct/csr_pkg.sv"), _file("with_struct/csr_regfile.sv")]


# ── 基础契约:空输入 / 诊断 / 错误处理 ─────────────────────────────

class TestBasics:
    """DS §1.2/§2/§5/§7:空输入、诊断汇总、错误直抛。"""

    def test_空列表返回空ParseResult(self):
        result = extract_design([])
        assert isinstance(result, ParseResult)
        assert result.instances == []
        assert result.signals == []
        assert result.blocks == []
        assert result.dep_edges == []

    def test_空列表分组函数均返回空(self):
        assert extract_hierarchy([]) == []
        assert extract_signals([]) == []
        assert extract_blocks([]) == []
        assert extract_dep_edges([]) == []

    def test_仅package文件返回空结果(self):
        result = extract_design([_file("with_struct/csr_pkg.sv")])
        assert result.instances == result.signals == result.blocks == result.dep_edges == []

    def test_文件不存在直接抛出OSError(self, tmp_path):
        """DS §7:流程①已过滤的文件缺失属程序错误,不吞异常。"""
        missing = str(tmp_path / "missing_flow2.sv")
        with pytest.raises(OSError):
            extract_design([missing])

    def test_编译警告仍继续提取(self, log_records):
        """DS §5.3:存在 WARNING 诊断时打印汇总并继续提取。"""
        result = extract_design(_alu_files())
        assert result.instances and result.signals and result.blocks
        warn_msgs = _warn_messages(log_records)
        assert any("编译诊断" in m and "WARNING" in m for m in warn_msgs)

    def test_编译错误继续提取且子模块不进树(self, log_records):
        """DS §5.3/§7:仅父文件编译,ERROR 汇总 + 不完整告警 + 缺失子模块告警。"""
        result = extract_design([_file("with_instance/alu_system.sv")])
        err_msgs = _error_messages(log_records)
        warn_msgs = _warn_messages(log_records)
        assert any("编译诊断" in m and "ERROR" in m for m in err_msgs)
        assert any("不完整" in m for m in warn_msgs)
        assert any("缺失" in m for m in warn_msgs)
        paths = [i.path for i in result.instances]
        assert paths == ["alu_system"]

    def test_同一输入双跑结果可复现(self):
        """DS §4:四组列表顺序确定、可复现。"""
        first = extract_design(_alu_files())
        second = extract_design(_alu_files())
        assert first == second


# ── 实例层次 ──────────────────────────────────────────────────────

class TestHierarchy:
    """DS §1.4/§4/§8:DFS 实例树、端口、多顶层、同模块多实例。"""

    def test_alu三层次实例树DFS顺序(self):
        result = extract_design(_alu_files())
        actual = [(i.path, i.module_name, i.depth) for i in result.instances]
        expected = [
            ("alu_system", "alu_system", 1),
            ("alu_system.u_control", "alu_control", 2),
            ("alu_system.u_core", "alu_core", 2),
            ("alu_system.u_core.u_adder", "adder_8bit", 3),
            ("alu_system.u_core.u_logic", "logic_unit", 3),
            ("alu_system.u_result", "result_stage", 2),
        ]
        assert actual == expected

    def test_顶层path与模块名一致(self):
        top = [i for i in extract_design(_alu_files()).instances if i.depth == 1]
        assert [(i.path, i.name, i.module_name) for i in top] == [
            ("alu_system", "alu_system", "alu_system"),
        ]

    def test_u_core端口声明与位宽(self):
        result = extract_design(_alu_files())
        core = next(i for i in result.instances if i.path == "alu_system.u_core")
        assert core.ports == [
            PortInfo(name="operand_a", direction="input", bit_width=8),
            PortInfo(name="operand_b", direction="input", bit_width=8),
            PortInfo(name="opcode", direction="input", bit_width=3),
            PortInfo(name="result", direction="output", bit_width=8),
            PortInfo(name="carry", direction="output", bit_width=1),
        ]

    def test_实例file为模块定义文件(self):
        result = extract_design(_alu_files())
        adder = next(i for i in result.instances if i.path == "alu_system.u_core.u_adder")
        assert adder.file == _file("with_instance/adder_8bit.sv")
        assert adder.module_name == "adder_8bit"

    def test_多顶层模块均收录(self):
        result = extract_design(_sv_files("with_struct"))
        tops = sorted((i.path, i.module_name) for i in result.instances if i.depth == 1)
        assert tops == [("csr_system", "csr_system"), ("data_pipeline", "data_pipeline")]

    def test_同一模块两处实例化(self):
        files = [_file("flow2_edge/dup_leaf.sv"), _file("flow2_edge/dup_top.sv")]
        result = extract_design(files)
        dups = [i for i in result.instances if i.path.startswith("dup_top.u")]
        assert [(i.path, i.module_name, i.depth) for i in dups] == [
            ("dup_top.u1", "dup_leaf", 2),
            ("dup_top.u2", "dup_leaf", 2),
        ]
        signals = _signal_map(result.signals)
        assert "dup_top.u1.a" in signals and "dup_top.u2.a" in signals

    def test_缺失子模块定义时仅顶层进树(self):
        """DS §5 规则 4:UninstantiatedDef 不进实例树(告警在错误处理类覆盖)。"""
        instances = extract_hierarchy([_file("with_instance/alu_system.sv")])
        assert [i.path for i in instances] == ["alu_system"]

    def test_分组函数与总成instances一致(self):
        files = _alu_files()
        assert extract_hierarchy(files) == extract_design(files).instances


# ── 信号 ──────────────────────────────────────────────────────────

class TestSignals:
    """DS §1.5/§5 规则 5–6/§8:端口合并、struct 展开、full_path 唯一。"""

    def test_ANSI端口与同名内部变量合并为一行(self):
        result = extract_design(_alu_files())
        smap = _signal_map(result.signals)
        port_a = smap["alu_system.u_core.u_adder.a"]
        assert (port_a.type_name, port_a.bit_width, port_a.kind) == ("logic[7:0]", 8, "port")
        assert port_a.is_port is True
        assert port_a.direction == "input"
        var_result = smap["alu_system.u_core.u_adder.result"]
        assert (var_result.type_name, var_result.bit_width, var_result.kind) == (
            "logic[8:0]", 9, "variable",
        )
        assert var_result.is_port is False
        assert var_result.direction == ""

    def test_full_path全量唯一(self):
        result = extract_design(_sv_files("with_struct"))
        paths = [s.full_path for s in result.signals]
        assert len(paths) == len(set(paths))

    def test_内部变量定义位置(self):
        result = extract_design(_alu_files())
        smap = _signal_map(result.signals)
        var = smap["alu_system.u_core.u_adder.result"]
        adder_lines = _read_lines(_file("with_instance/adder_8bit.sv"))
        decl_line = next(
            i for i, line in enumerate(adder_lines, 1) if "logic [8:0] result;" in line
        )
        assert var.definition_file == _file("with_instance/adder_8bit.sv")
        assert var.definition_line == decl_line

    def test_struct字段递归展开(self):
        result = extract_design(_csr_pair())
        smap = _signal_map(result.signals)
        base = smap["csr_regfile.cfg_reg"]
        assert (base.kind, base.type_name, base.bit_width) == (
            "variable", "csr_pkg::csr_cfg_t", 27,
        )
        baud = smap["csr_regfile.cfg_reg.baud"]
        assert (baud.kind, baud.type_name, baud.bit_width) == (
            "field", "csr_pkg::baud_cfg_t", 20,
        )
        div = smap["csr_regfile.cfg_reg.baud.div"]
        assert (div.kind, div.name, div.type_name, div.bit_width) == (
            "field", "div", "logic[15:0]", 16,
        )
        prio = smap["csr_regfile.cfg_reg.irq.prio_level"]
        assert (prio.kind, prio.type_name, prio.bit_width) == ("field", "logic[3:0]", 4)
        assert prio.is_port is False and prio.direction == ""

    def test_struct字段定义位置继承基变量(self):
        result = extract_design(_csr_pair())
        smap = _signal_map(result.signals)
        base = smap["csr_regfile.cfg_reg"]
        for full_path in (
            "csr_regfile.cfg_reg.baud",
            "csr_regfile.cfg_reg.baud.div",
            "csr_regfile.cfg_reg.irq.prio_level",
        ):
            field = smap[full_path]
            assert field.definition_file == base.definition_file
            assert field.definition_line == base.definition_line

    def test_分组函数与总成signals一致(self):
        files = _csr_pair()
        assert extract_signals(files) == extract_design(files).signals


# ── 赋值语句块 ────────────────────────────────────────────────────

class TestBlocks:
    """DS §1.6/§4/§5 规则 7–8:块类型、源文本、index、port_connection 归属。"""

    def test_块类型与源文本行切片(self):
        result = extract_design(_csr_pair())
        assert [b.block_type for b in result.blocks] == [
            "always_ff", "always_ff", "always_comb",
            "assign", "assign", "assign", "assign",
        ]
        assert all(Path(b.source_file).name == "csr_regfile.sv" for b in result.blocks)
        for block in result.blocks:
            _assert_block_text(block)

    def test_block_index全局连续唯一(self):
        for files in (_alu_files(), _csr_pair()):
            result = extract_design(files)
            assert [b.index for b in result.blocks] == list(range(len(result.blocks)))

    def test_port_connection块归属父实例并排末尾(self):
        result = extract_design(_alu_files())
        grouped: dict[str, list[str]] = {}
        for block in result.blocks:
            grouped.setdefault(block.instance_path, []).append(block.block_type)
        assert grouped["alu_system"] == [
            "assign", "port_connection", "port_connection", "port_connection",
        ]
        assert grouped["alu_system.u_core"] == [
            "always_comb", "assign", "always_comb",
            "port_connection", "port_connection",
        ]

    def test_port_connection源文本为实例化语句(self):
        result = extract_design(_alu_files())
        u_core_conn = next(
            b for b in result.blocks
            if b.instance_path == "alu_system.u_core" and b.block_type == "port_connection"
            and "u_adder" in b.source_text
        )
        assert u_core_conn.source_file == _file("with_instance/alu_core.sv")
        assert u_core_conn.source_text.lstrip().startswith("adder_8bit u_adder")
        top_core_conn = next(
            b for b in result.blocks
            if b.instance_path == "alu_system" and b.block_type == "port_connection"
            and "u_core" in b.source_text
        )
        assert top_core_conn.source_file == _file("with_instance/alu_system.sv")
        assert top_core_conn.source_text.lstrip().startswith("alu_core u_core")

    def test_子实例块被过滤(self):
        """DS §5 规则 7:body.visit 穿透子实例,必须只保留本实例直接块。"""
        result = extract_design(_alu_files())
        core_blocks = [b for b in result.blocks if b.instance_path == "alu_system.u_core"]
        assert core_blocks
        assert {b.source_file for b in core_blocks} == {
            _file("with_instance/alu_core.sv"),
        }

    def test_always_latch_initial_final类型映射(self):
        result = extract_design([_file("flow2_edge/misc_blocks.sv")])
        assert [b.block_type for b in result.blocks] == [
            "always_latch", "initial", "final",
        ]

    def test_分组函数与总成blocks一致(self):
        files = _alu_files()
        assert extract_blocks(files) == extract_design(files).blocks


# ── 依赖边 ────────────────────────────────────────────────────────

class TestDepEdges:
    """DS §5 规则 9–10/§6:两通道赋值依赖与跨模块端口连接。"""

    def test_连续赋值通道1RHS读(self):
        result = extract_design(_alu_files())
        edge = next(
            e for e in result.dep_edges
            if _sig(e) == (
                "alu_system.u_core.u_adder.sum",
                "alu_system.u_core.u_adder.result",
                False,
                False,
            )
        )
        assert edge.block is not None and edge.block.block_type == "assign"

    def test_时序块timed与条件门控(self):
        result = extract_design(_alu_files())
        keys = _sig_keys(result.dep_edges)
        pre = "alu_system.u_result."
        assert (pre + "data_out", pre + "clk", True, False) in keys
        assert (pre + "data_out", pre + "en", True, False) in keys
        assert (pre + "data_out", pre + "data_in", False, False) in keys

    def test_条件不过宽(self):
        """DS §6.1/ref.md §5.5:if 条件只广播给分支内赋值,不误伤同块无关语句。"""
        result = extract_design([_file("test_interface/sequence_ctrl.sv")])
        keys = _sig_keys(result.dep_edges)
        assert ("sequence_ctrl.state_next", "sequence_ctrl.start", True, False) in keys
        assert ("sequence_ctrl.done", "sequence_ctrl.start", True, False) not in keys
        assert ("sequence_ctrl.done", "sequence_ctrl.ack", True, False) not in keys

    def test_case表达式门控广播(self):
        result = extract_design(_csr_pair())
        keys = _sig_keys(result.dep_edges)
        assert ("csr_regfile.rd_data", "csr_regfile.addr", True, False) in keys
        assert ("csr_regfile.rd_valid", "csr_regfile.addr", True, False) in keys

    def test_三元RHS三操作数均读(self):
        """DS §6.1 通道1:三元 ?: 三个操作数都算读取。"""
        result = extract_design([_file("smoke/simple_alu.sv")])
        keys = _sig_keys(result.dep_edges)
        assert ("simple_alu.carry", "simple_alu.op", False, False) in keys
        assert ("simple_alu.carry", "simple_alu.add_sub_result", False, False) in keys

    def test_struct字段写只驱动叶子行(self):
        result = extract_design(_csr_pair())
        keys = _sig_keys(result.dep_edges)
        assert ("csr_regfile.cfg_reg.baud.div", "csr_regfile.wr_data", False, False) in keys
        assert ("csr_regfile.cfg_reg", "csr_regfile.wr_data", False, False) not in keys

    def test_整struct读以基行参与(self):
        result = extract_design(_csr_pair())
        keys = _sig_keys(result.dep_edges)
        assert ("csr_regfile.csr_cfg_o", "csr_regfile.cfg_reg", False, False) in keys

    def test_复合赋值隐式自依赖(self):
        """DS §6.1:isCompound 时 LHS 计入隐式读,产生自依赖边。"""
        result = extract_design([_file("flow2_edge/compound.sv")])
        assert _sig_keys(result.dep_edges) == {
            ("compound_edge.acc", "compound_edge.acc", False, False),
            ("compound_edge.acc", "compound_edge.b", False, False),
            ("compound_edge.q", "compound_edge.acc", False, False),
        }

    def test_for循环_自增_下标读_门控(self):
        """DS §6.1/§6.3:i=0/i++/i<n 与 LHS Select 下标读均按规则建边。"""
        result = extract_design([_file("flow2_edge/loop_array.sv")])
        pre = "loop_array_edge."
        assert _sig_keys(result.dep_edges) == {
            (pre + "i", pre + "clk", True, False),
            (pre + "i", pre + "i", False, False),
            (pre + "q", pre + "clk", True, False),
            (pre + "q", pre + "d", False, False),
            (pre + "q", pre + "i", False, False),
            (pre + "q", pre + "i", True, False),
            (pre + "q", pre + "n", True, False),
        }

    def test_局部循环变量依赖边被丢弃(self, log_records):
        """DS §5 规则 9:迭代变量不在信号表中,读边丢弃并 debug 记录。"""
        result = extract_design([_file("flow2_edge/local_loop.sv")])
        pre = "local_loop_edge."
        assert _sig_keys(result.dep_edges) == {
            (pre + "q", pre + "clk", True, False),
            (pre + "q", pre + "d", False, False),
            (pre + "q", pre + "n", True, False),
        }
        debug_msgs = _debug_messages(log_records)
        assert any("local_loop_edge.k" in m for m in debug_msgs)

    def test_latch_initial_final块内边(self):
        result = extract_design([_file("flow2_edge/misc_blocks.sv")])
        pre = "misc_blocks."
        assert _sig_keys(result.dep_edges) == {
            (pre + "x", pre + "a", True, False),
            (pre + "x", pre + "t", False, False),
            (pre + "z", pre + "x", False, False),
        }

    def test_端口连接InOut方向与块绑定(self):
        """DS §6.2:In 边父→子、Out 边子→父,均绑定父实例 port_connection 块。"""
        result = extract_design(_alu_files())
        keys = _sig_keys(result.dep_edges)
        in_edge = next(
            e for e in result.dep_edges
            if _sig(e) == ("alu_system.opcode", "alu_system.u_core.opcode", False, True)
        )
        out_edge = next(
            e for e in result.dep_edges
            if _sig(e) == ("alu_system.u_core.result", "alu_system.core_result", False, True)
        )
        assert ("alu_system.u_control.compute_en", "alu_system.compute_en", False, True) in keys
        assert ("alu_system.clk", "alu_system.u_control.clk", False, True) in keys
        for edge in (in_edge, out_edge):
            assert edge.block is not None
            assert edge.block.instance_path == "alu_system"
            assert edge.block.block_type == "port_connection"
            assert edge.block in result.blocks

    def test_空端口连接不产边并debug记录(self, log_records):
        result = extract_design(_sv_files("with_struct"))
        empty_names = (
            "csr_system.u_decode.reg_sel",
            "csr_system.u_decode.reg_we",
        )
        port_conn_sigs = {
            (e.driven_signal, e.read_signal)
            for e in result.dep_edges
            if e.is_port_conn
            and any(name in e.driven_signal or name in e.read_signal
                    for name in empty_names)
        }
        assert port_conn_sigs == set()
        assert any("u_decode.reg_sel" in m for m in _debug_messages(log_records))

    def test_inout_ref连接告警跳过(self, log_records):
        """DS §6.2/§7:InOut/Ref 不在本次范围,告警跳过且不产端口连接边。"""
        result = extract_design([_file("flow2_edge/inout_ref.sv")])
        assert not any(e.is_port_conn for e in result.dep_edges)
        warn_msgs = _warn_messages(log_records)
        assert any("u_io.io" in m for m in warn_msgs)
        assert any("u_ref.x" in m for m in warn_msgs)

    def test_边端点全部命中信号表(self):
        for files in (
            _csr_pair(),
            [_file("flow2_edge/dup_leaf.sv"), _file("flow2_edge/dup_top.sv")],
            [_file("flow2_edge/compound.sv")],
            [_file("flow2_edge/loop_array.sv")],
            [_file("flow2_edge/local_loop.sv")],
            [_file("flow2_edge/misc_blocks.sv")],
            [_file("flow2_edge/inout_ref.sv")],
        ):
            _assert_edges_resolve(extract_design(files))

    def test_边键去重且双跑一致(self):
        files = _alu_files()
        first = extract_design(files)
        second = extract_design(files)
        keys_first = [_full_key(e) for e in first.dep_edges]
        assert len(keys_first) == len(set(keys_first))
        assert keys_first == [_full_key(e) for e in second.dep_edges]

    def test_分组函数与总成dep_edges一致(self):
        files = _alu_files()
        design_keys = _full_keys(extract_design(files).dep_edges)
        group_keys = _full_keys(extract_dep_edges(files))
        assert design_keys == group_keys
