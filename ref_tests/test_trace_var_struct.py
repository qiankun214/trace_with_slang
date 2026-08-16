"""
test_trace_var_struct.py — trace_variable() 的 struct 检测回归测试
（test/with_struct/ 固件：CSR 系统 4 级层次，5 个 struct 场景）

场景划分（与 filelist.f 注释对应）：
  S1  csr_regfile  — 结构体实例化在模块内部 (internal struct signals)
  S2  baud_gen     — 结构体例化在端口上 (struct ports)
  S3  intr_handler — 结构体定义在模块内部 (local typedef struct)
  S4  csr_pkg      — 结构体定义在集中的SV文件 (package shared types)
  S5  irq_arbiter  — 结构体嵌套 (nested struct field access)

断言约定：
  - related_variables 顺序无序（set 迭代序）→ 一律用集合比较，
    再用 _related_map() 按 name 逐项断言 path/bit_width/type_name/kind
  - 块级赋值（always_ff/always_comb/continuous_assign）的 assignment
    不含 instance_name/definition_name 键，仅 port_connection 有
  - 整 struct 端口/信号 kind=variable，字段（field）kind=field
"""

import pytest

from trace_var import trace_variable

# 被测变量信息的必要字段
REQUIRED_VAR_KEYS = [
    "name", "hierarchical_path", "bit_width", "type_name", "kind",
]


def _related_map(result):
    """related_variables 无序，按 name 建字典便于逐项断言。"""
    return {v["name"]: v for v in result["related_variables"]}


# ==============================================================================
# S1 — 内部 struct 信号（csr_regfile.sv）
# ==============================================================================

class TestStructS1Internal:
    """S1 内部 struct 信号：cfg_reg（嵌套）、status_sync（整结构赋值）"""

    def test_追踪内部struct寄存器cfg_reg(self, struct_filelist_path):
        """cfg_reg — 内部嵌套 struct 寄存器，always_ff 写逻辑，27bit。"""
        result = trace_variable(struct_filelist_path, "csr_system.u_regfile.cfg_reg")

        var = result["variable"]
        assert var["name"] == "cfg_reg"
        assert var["bit_width"] == 27
        assert var["type_name"] == "csr_pkg::csr_cfg_t"
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "always_ff"
        assert assign["start_line"] == 35
        assert assign["end_line"] == 50
        assert "csr_regfile.sv" in assign["file"]
        assert "instance_name" not in assign, "块级赋值不应有 instance_name"

        related = _related_map(result)
        assert set(related) == {"clk", "rst_n", "wr_en", "wr_data", "addr"}
        # LHS 字段（div/oversample/mode/en_tx_done 等）全部排除，无字段项
        for v in related.values():
            assert v["kind"] == "variable", f"字段不应出现在 related: {v}"

    def test_追踪内部struct字段baud_div(self, struct_filelist_path):
        """cfg_reg.baud.div — 三层字段 LHS 追踪，落在整块 always_ff。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_regfile.cfg_reg.baud.div"
        )

        var = result["variable"]
        assert var["name"] == "div"
        assert var["bit_width"] == 16
        assert var["type_name"] == "logic[15:0]"
        assert var["kind"] == "field"
        assert var["hierarchical_path"] == "csr_system.u_regfile.cfg_reg.baud.div"

        assign = result["assignment"]
        assert assign["type"] == "always_ff"
        assert assign["start_line"] == 35
        assert assign["end_line"] == 50

        assert set(_related_map(result)) == {"clk", "rst_n", "wr_en", "wr_data", "addr"}

    def test_追踪内部struct中间字段baud(self, struct_filelist_path):
        """cfg_reg.baud — 一级字段，位宽 20，类型为嵌套的子结构体。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_regfile.cfg_reg.baud"
        )

        var = result["variable"]
        assert var["name"] == "baud"
        assert var["bit_width"] == 20
        assert var["type_name"] == "csr_pkg::baud_cfg_t"
        assert var["kind"] == "field"

        assert result["assignment"]["type"] == "always_ff"
        assert set(_related_map(result)) == {"clk", "rst_n", "wr_en", "wr_data", "addr"}

    def test_追踪内部struct信号status_sync(self, struct_filelist_path):
        """status_sync — 整结构赋值，RHS status_i（整结构 → 基变量）。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_regfile.status_sync"
        )

        var = result["variable"]
        assert var["name"] == "status_sync"
        assert var["bit_width"] == 5
        assert var["type_name"] == "csr_pkg::csr_status_t"
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "always_ff"
        assert assign["start_line"] == 53
        assert assign["end_line"] == 58

        related = _related_map(result)
        assert set(related) == {"clk", "rst_n", "status_i"}
        # RHS 是整结构 NamedValue → 报基变量 status_i
        assert related["status_i"]["kind"] == "variable"
        assert related["status_i"]["bit_width"] == 5
        assert related["status_i"]["type_name"] == "csr_pkg::csr_status_t"

    def test_追踪struct转向量输出cfg_debug(self, struct_filelist_path):
        """cfg_debug = cfg_reg — struct → 27bit 向量位流，related 报基变量。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_regfile.cfg_debug"
        )

        var = result["variable"]
        assert var["name"] == "cfg_debug"
        assert var["bit_width"] == 27
        assert var["type_name"] == "logic[26:0]"
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "continuous_assign"
        assert assign["start_line"] == 81
        assert assign["end_line"] == 81

        related = _related_map(result)
        assert set(related) == {"cfg_reg"}, f"应只有 cfg_reg，实际: {set(related)}"
        assert related["cfg_reg"]["kind"] == "variable"
        assert related["cfg_reg"]["bit_width"] == 27
        assert related["cfg_reg"]["type_name"] == "csr_pkg::csr_cfg_t"


# ==============================================================================
# S2 — struct 端口（baud_gen.sv / csr_regfile 输出端口）
# ==============================================================================

class TestStructS2Ports:
    """S2 struct 端口：输入端口 related 恒空；输出端口连续赋值取字段"""

    def test_追踪struct输入端口cfg_i(self, struct_filelist_path):
        """u_baud.cfg_i — struct 输入端口，port_connection，related 为空。"""
        result = trace_variable(struct_filelist_path, "csr_system.u_baud.cfg_i")

        var = result["variable"]
        assert var["name"] == "cfg_i"
        assert var["bit_width"] == 20
        assert var["type_name"] == "csr_pkg::baud_cfg_t"
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "port_connection"
        assert assign["start_line"] == 77
        assert assign["end_line"] == 83
        assert "csr_system.sv" in assign["file"]
        assert assign["instance_name"] == "u_baud"
        assert assign["definition_name"] == "baud_gen"

        assert result["related_variables"] == [], (
            f"输入端口应无相关变量，实际: {result['related_variables']}"
        )

    def test_追踪struct输入端口字段cfg_i_div(self, struct_filelist_path):
        """u_baud.cfg_i.div — 输入端口字段，同样走 port_connection 且 related 空。"""
        result = trace_variable(struct_filelist_path, "csr_system.u_baud.cfg_i.div")

        var = result["variable"]
        assert var["name"] == "div"
        assert var["bit_width"] == 16
        assert var["type_name"] == "logic[15:0]"
        assert var["kind"] == "field"

        assign = result["assignment"]
        assert assign["type"] == "port_connection"
        assert assign["instance_name"] == "u_baud"
        assert assign["definition_name"] == "baud_gen"

        assert result["related_variables"] == []

    def test_追踪struct字段读取baud_tick_o(self, struct_filelist_path):
        """baud_tick_o — always_ff 中读取 cfg_i.div（RHS 字段访问）。"""
        result = trace_variable(struct_filelist_path, "csr_system.u_baud.baud_tick_o")

        var = result["variable"]
        assert var["name"] == "baud_tick_o"
        assert var["bit_width"] == 1
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "always_ff"
        assert assign["start_line"] == 24
        assert assign["end_line"] == 38
        assert "baud_gen.sv" in assign["file"]

        related = _related_map(result)
        assert set(related) == {"div", "counter", "clk", "rst_n"}
        # RHS 字段访问：只含字段 div，不含基变量 cfg_i、不含未读的 oversample/mode
        assert related["div"]["kind"] == "field"
        assert related["div"]["bit_width"] == 16
        assert related["div"]["type_name"] == "logic[15:0]"
        assert related["div"]["hierarchical_path"] == (
            "csr_system.u_baud.cfg_i.div"
        ), f"字段路径错误: {related['div']['hierarchical_path']}"
        assert "cfg_i" not in related

    def test_追踪struct输出端口baud_cfg_o(self, struct_filelist_path):
        """baud_cfg_o = cfg_reg.baud — related 只含字段 baud，路径修正为实例路径。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_regfile.baud_cfg_o"
        )

        var = result["variable"]
        assert var["name"] == "baud_cfg_o"
        assert var["bit_width"] == 20
        assert var["type_name"] == "csr_pkg::baud_cfg_t"
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "continuous_assign"
        assert assign["start_line"] == 76
        assert assign["end_line"] == 76

        related = _related_map(result)
        assert set(related) == {"baud"}, f"应只有字段 baud，实际: {set(related)}"
        assert related["baud"]["kind"] == "field"
        assert related["baud"]["bit_width"] == 20
        assert related["baud"]["type_name"] == "csr_pkg::baud_cfg_t"
        # 路径指向实例化的 cfg_reg 变量，而不是类型定义路径（csr_pkg.baud）
        assert related["baud"]["hierarchical_path"] == (
            "csr_system.u_regfile.cfg_reg.baud"
        ), f"路径修正失败: {related['baud']['hierarchical_path']}"

    def test_struct字段related中无基变量cfg_reg(self, struct_filelist_path):
        """cfg_reg 是 MemberAccess 链的基变量，不应作为独立变量出现。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_regfile.baud_cfg_o"
        )
        related_names = set(_related_map(result))
        assert "cfg_reg" not in related_names, (
            f"cfg_reg 不应出现在 related 中，实际: {related_names}"
        )

    def test_追踪struct输入端口status_i(self, struct_filelist_path):
        """u_regfile.status_i — struct 输入端口，related 为空。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_regfile.status_i"
        )

        var = result["variable"]
        assert var["name"] == "status_i"
        assert var["bit_width"] == 5
        assert var["type_name"] == "csr_pkg::csr_status_t"
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "port_connection"
        assert assign["start_line"] == 60
        assert assign["end_line"] == 73
        assert assign["instance_name"] == "u_regfile"
        assert assign["definition_name"] == "csr_regfile"

        assert result["related_variables"] == []


# ==============================================================================
# S3 — 模块内 typedef struct（intr_handler.sv）
# ==============================================================================

class TestStructS3LocalTypedef:
    """S3 模块内私有 typedef：intr_status_local_t（非 csr_pkg:: 前缀）"""

    def test_追踪模块内typedef信号status_synced(self, struct_filelist_path):
        """status_synced — 模块内 typedef 类型，type_name 带模块前缀。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_intr.status_synced"
        )

        var = result["variable"]
        assert var["name"] == "status_synced"
        assert var["bit_width"] == 5
        assert var["type_name"] == "intr_handler.intr_status_local_t", (
            f"模块内 typedef 类型名应带模块前缀: {var['type_name']}"
        )
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "always_ff"
        assert assign["start_line"] == 41
        assert assign["end_line"] == 49
        assert "intr_handler.sv" in assign["file"]

        related = _related_map(result)
        assert set(related) == {
            "clk", "rst_n", "tx_done_i", "rx_ready_i", "err_i", "fifo_level_i",
        }
        for v in related.values():
            assert v["kind"] == "variable"

    def test_追踪模块内typedef字段tx_done_s(self, struct_filelist_path):
        """status_synced.tx_done_s — 模块内 typedef 字段，1bit。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_intr.status_synced.tx_done_s"
        )

        var = result["variable"]
        assert var["name"] == "tx_done_s"
        assert var["bit_width"] == 1
        assert var["type_name"] == "logic"
        assert var["kind"] == "field"
        assert var["hierarchical_path"] == "csr_system.u_intr.status_synced.tx_done_s"

        assign = result["assignment"]
        assert assign["type"] == "always_ff"
        assert assign["start_line"] == 41
        assert assign["end_line"] == 49

        assert set(_related_map(result)) == {
            "clk", "rst_n", "tx_done_i", "rx_ready_i", "err_i", "fifo_level_i",
        }

    def test_追踪组合输出intr_o(self, struct_filelist_path):
        """intr_o — always_comb 读取 6 个 struct 字段，基变量不出现。"""
        result = trace_variable(struct_filelist_path, "csr_system.u_intr.intr_o")

        var = result["variable"]
        assert var["name"] == "intr_o"
        assert var["bit_width"] == 1
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "always_comb"
        assert assign["start_line"] == 52
        assert assign["end_line"] == 61
        assert "intr_handler.sv" in assign["file"]

        related = _related_map(result)
        assert set(related) == {
            "en_tx_done", "en_rx_done", "en_err",
            "tx_done_s", "rx_ready_s", "err_s",
        }, f"应恰有 6 个字段，实际: {set(related)}"
        # 基变量 irq_cfg_i / status_synced 不应作为独立变量出现
        assert "irq_cfg_i" not in related
        assert "status_synced" not in related
        # 逐项断言字段路径（irq_cfg_i 的使能位 + status_synced 的状态位）
        expected_paths = {
            "en_tx_done": "csr_system.u_intr.irq_cfg_i.en_tx_done",
            "en_rx_done": "csr_system.u_intr.irq_cfg_i.en_rx_done",
            "en_err": "csr_system.u_intr.irq_cfg_i.en_err",
            "tx_done_s": "csr_system.u_intr.status_synced.tx_done_s",
            "rx_ready_s": "csr_system.u_intr.status_synced.rx_ready_s",
            "err_s": "csr_system.u_intr.status_synced.err_s",
        }
        for name, expected in expected_paths.items():
            v = related[name]
            assert v["kind"] == "field", f"{name} 应为 field: {v}"
            assert v["hierarchical_path"] == expected, (
                f"{name} 路径错误: {v['hierarchical_path']}"
            )

    def test_追踪typedef输入端口irq_cfg_i(self, struct_filelist_path):
        """u_intr.irq_cfg_i — struct 输入端口，related 为空。"""
        result = trace_variable(struct_filelist_path, "csr_system.u_intr.irq_cfg_i")

        var = result["variable"]
        assert var["name"] == "irq_cfg_i"
        assert var["bit_width"] == 7
        assert var["type_name"] == "csr_pkg::irq_cfg_t"
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "port_connection"
        assert assign["start_line"] == 95
        assert assign["end_line"] == 106
        assert assign["instance_name"] == "u_intr"
        assert assign["definition_name"] == "intr_handler"

        assert result["related_variables"] == []

    def test_追踪标量输入端口fifo_level_i(self, struct_filelist_path):
        """fifo_level_i — 标量输入端口，驱动在父模块实例化处，related 为空。"""
        result = trace_variable(struct_filelist_path, "csr_system.u_intr.fifo_level_i")

        var = result["variable"]
        assert var["name"] == "fifo_level_i"
        assert var["bit_width"] == 2

        assign = result["assignment"]
        assert assign["type"] == "port_connection"
        assert assign["instance_name"] == "u_intr"
        assert assign["definition_name"] == "intr_handler"
        # 赋值位置是实例化语句（csr_system.sv 中 u_intr 的端口连接）
        assert "csr_system.sv" in assign["file"]

        assert result["related_variables"] == [], (
            f"输入端口应无相关变量，实际: {result['related_variables']}"
        )


# ==============================================================================
# S4 — package 类型（csr_pkg.sv）
# ==============================================================================

class TestStructS4PackageTypes:
    """S4 package 共享类型：csr_pkg:: 前缀、嵌套结构体整体输出"""

    def test_追踪package类型端口字段baud_cfg_o_div(self, struct_filelist_path):
        """baud_cfg_o.div — 输出端口字段，赋值是模块内 continuous_assign。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_regfile.baud_cfg_o.div"
        )

        var = result["variable"]
        assert var["name"] == "div"
        assert var["bit_width"] == 16
        assert var["type_name"] == "logic[15:0]"
        assert var["kind"] == "field"

        assign = result["assignment"]
        assert assign["type"] == "continuous_assign"
        assert assign["start_line"] == 76
        assert assign["end_line"] == 76

        related = _related_map(result)
        assert set(related) == {"baud"}
        assert related["baud"]["hierarchical_path"] == (
            "csr_system.u_regfile.cfg_reg.baud"
        )

    def test_追踪package类型输出irq_cfg_o(self, struct_filelist_path):
        """irq_cfg_o = cfg_reg.irq — 7bit package 类型，related 只含字段 irq。"""
        result = trace_variable(struct_filelist_path, "csr_system.u_regfile.irq_cfg_o")

        var = result["variable"]
        assert var["name"] == "irq_cfg_o"
        assert var["bit_width"] == 7
        assert var["type_name"] == "csr_pkg::irq_cfg_t"
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "continuous_assign"
        assert assign["start_line"] == 77
        assert assign["end_line"] == 77

        related = _related_map(result)
        assert set(related) == {"irq"}, f"应只有字段 irq，实际: {set(related)}"
        assert related["irq"]["kind"] == "field"
        assert related["irq"]["bit_width"] == 7
        assert related["irq"]["type_name"] == "csr_pkg::irq_cfg_t"
        assert related["irq"]["hierarchical_path"] == (
            "csr_system.u_regfile.cfg_reg.irq"
        )

    def test_追踪嵌套package类型输出csr_cfg_o(self, struct_filelist_path):
        """csr_cfg_o = cfg_reg — 完整嵌套结构体 RHS → related 报基变量。"""
        result = trace_variable(struct_filelist_path, "csr_system.u_regfile.csr_cfg_o")

        var = result["variable"]
        assert var["name"] == "csr_cfg_o"
        assert var["bit_width"] == 27
        assert var["type_name"] == "csr_pkg::csr_cfg_t"
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "continuous_assign"
        assert assign["start_line"] == 78
        assert assign["end_line"] == 78

        related = _related_map(result)
        assert set(related) == {"cfg_reg"}, f"应只有 cfg_reg，实际: {set(related)}"
        assert related["cfg_reg"]["kind"] == "variable"
        assert related["cfg_reg"]["bit_width"] == 27
        assert related["cfg_reg"]["type_name"] == "csr_pkg::csr_cfg_t"

    def test_追踪顶层struct打包status_pack(self, struct_filelist_path):
        """status_pack — 顶层 4 条字段连续赋值合并为跨度 54-57。"""
        result = trace_variable(struct_filelist_path, "csr_system.status_pack")

        var = result["variable"]
        assert var["name"] == "status_pack"
        assert var["bit_width"] == 5
        assert var["type_name"] == "csr_pkg::csr_status_t"
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "continuous_assign"
        assert assign["start_line"] == 54
        assert assign["end_line"] == 57
        assert "csr_system.sv" in assign["file"]
        source = assign["source_text"]
        assert "status_pack.tx_busy" in source, f"源文本缺少首条赋值: {source[:60]}..."
        assert "status_pack.parity_err" in source, f"源文本缺少末条赋值: {source[:60]}..."

        # 字段 LHS 全部排除，只保留 4 个顶层输入
        assert set(_related_map(result)) == {
            "tx_busy_i", "rx_ready_i", "fifo_level_i", "err_i",
        }


# ==============================================================================
# S5 — 嵌套 struct 字段访问（irq_arbiter.sv）
# ==============================================================================

class TestStructS5Nested:
    """S5 嵌套 struct：csr_cfg_t 嵌套 baud_cfg_t + irq_cfg_t"""

    def test_追踪嵌套字段访问irq_grant(self, struct_filelist_path):
        """irq_grant — always_ff 中两层字段访问，related 含中间字段+叶子字段。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_intr.u_arbiter.irq_grant"
        )

        var = result["variable"]
        assert var["name"] == "irq_grant"
        assert var["bit_width"] == 1
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "always_ff"
        assert assign["start_line"] == 23
        assert assign["end_line"] == 35
        assert "irq_arbiter.sv" in assign["file"]

        related = _related_map(result)
        # 4 个字段（2 中间 + 2 叶子）+ 3 个标量，基变量 full_cfg_i 不出现
        assert set(related) == {
            "baud", "irq", "mode", "prio_level", "irq_req", "clk", "rst_n",
        }, f"应恰有 7 项，实际: {set(related)}"
        assert "full_cfg_i" not in related, "基变量 full_cfg_i 不应出现"

        # 中间字段（一级访问）：baud / irq
        assert related["baud"]["kind"] == "field"
        assert related["baud"]["bit_width"] == 20
        assert related["baud"]["type_name"] == "csr_pkg::baud_cfg_t"
        assert related["baud"]["hierarchical_path"] == (
            "csr_system.u_intr.u_arbiter.full_cfg_i.baud"
        )
        assert related["irq"]["kind"] == "field"
        assert related["irq"]["bit_width"] == 7
        assert related["irq"]["type_name"] == "csr_pkg::irq_cfg_t"
        assert related["irq"]["hierarchical_path"] == (
            "csr_system.u_intr.u_arbiter.full_cfg_i.irq"
        )

        # 叶子字段（两层访问）：mode / prio_level
        assert related["mode"]["kind"] == "field"
        assert related["mode"]["bit_width"] == 1
        assert related["mode"]["hierarchical_path"] == (
            "csr_system.u_intr.u_arbiter.full_cfg_i.baud.mode"
        )
        assert related["prio_level"]["kind"] == "field"
        assert related["prio_level"]["bit_width"] == 4
        assert related["prio_level"]["type_name"] == "logic[3:0]"
        assert related["prio_level"]["hierarchical_path"] == (
            "csr_system.u_intr.u_arbiter.full_cfg_i.irq.prio_level"
        )

        # 标量输入
        assert related["irq_req"]["kind"] == "variable"
        assert related["clk"]["kind"] == "variable"
        assert related["rst_n"]["kind"] == "variable"

    def test_追踪嵌套输入端口字段mode(self, struct_filelist_path):
        """full_cfg_i.baud.mode — 两层嵌套输入端口字段，related 为空。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_intr.u_arbiter.full_cfg_i.baud.mode"
        )

        var = result["variable"]
        assert var["name"] == "mode"
        assert var["bit_width"] == 1
        assert var["type_name"] == "logic"
        assert var["kind"] == "field"
        assert var["hierarchical_path"] == (
            "csr_system.u_intr.u_arbiter.full_cfg_i.baud.mode"
        )

        assign = result["assignment"]
        assert assign["type"] == "port_connection"
        assert assign["start_line"] == 64
        assert assign["end_line"] == 70
        assert assign["instance_name"] == "u_arbiter"
        assert assign["definition_name"] == "irq_arbiter"

        assert result["related_variables"] == []

    def test_追踪嵌套输入端口字段prio_level(self, struct_filelist_path):
        """full_cfg_i.irq.prio_level — 两层嵌套字段，4bit。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_intr.u_arbiter.full_cfg_i.irq.prio_level"
        )

        var = result["variable"]
        assert var["name"] == "prio_level"
        assert var["bit_width"] == 4
        assert var["type_name"] == "logic[3:0]"
        assert var["kind"] == "field"

        assert result["assignment"]["type"] == "port_connection"
        assert result["assignment"]["instance_name"] == "u_arbiter"
        assert result["related_variables"] == []

    def test_追踪嵌套struct输入端口full_cfg_i(self, struct_filelist_path):
        """u_arbiter.full_cfg_i — 嵌套 struct 输入端口，27bit，related 为空。"""
        result = trace_variable(
            struct_filelist_path, "csr_system.u_intr.u_arbiter.full_cfg_i"
        )

        var = result["variable"]
        assert var["name"] == "full_cfg_i"
        assert var["bit_width"] == 27
        assert var["type_name"] == "csr_pkg::csr_cfg_t"
        assert var["kind"] == "variable"

        assign = result["assignment"]
        assert assign["type"] == "port_connection"
        assert assign["start_line"] == 64
        assert assign["end_line"] == 70
        assert assign["instance_name"] == "u_arbiter"
        assert assign["definition_name"] == "irq_arbiter"

        assert result["related_variables"] == []


# ==============================================================================
# 错误路径
# ==============================================================================

class TestStructErrorPaths:
    """with_struct 固件的错误路径：不存在的实例/变量/字段"""

    def test_错误实例路径u_regfile_u_baud抛出ValueError(self, struct_filelist_path):
        """u_baud 实际在顶层 csr_system 下，不在 u_regfile 下。"""
        with pytest.raises(ValueError):
            trace_variable(
                struct_filelist_path, "csr_system.u_regfile.u_baud.baud_tick_o"
            )

    def test_不存在的嵌套字段抛出ValueError(self, struct_filelist_path):
        """cfg_reg.baud.nonexistent — 存在的变量但字段不存在。"""
        with pytest.raises(ValueError):
            trace_variable(
                struct_filelist_path, "csr_system.u_regfile.cfg_reg.baud.nonexistent"
            )

    def test_输入端口不存在的字段抛出ValueError(self, struct_filelist_path):
        """cfg_i.nonexistent — 输入端口上不存在的字段。"""
        with pytest.raises(ValueError):
            trace_variable(struct_filelist_path, "csr_system.u_baud.cfg_i.nonexistent")

    def test_输出端口不存在的字段抛出ValueError(self, struct_filelist_path):
        """baud_cfg_o.div2 — 输出端口上不存在的字段。"""
        with pytest.raises(ValueError):
            trace_variable(
                struct_filelist_path, "csr_system.u_regfile.baud_cfg_o.div2"
            )

    def test_顶层不存在的变量抛出ValueError(self, struct_filelist_path):
        """csr_system.nonexistent_sig — 顶层不存在的信号。"""
        with pytest.raises(ValueError):
            trace_variable(struct_filelist_path, "csr_system.nonexistent_sig")
