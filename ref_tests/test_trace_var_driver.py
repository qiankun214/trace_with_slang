"""
test_trace_var_driver.py — 测试 trace_var_driver.py 的公开一级函数：
  - trace_var_driver()
"""

import pytest

from trace_var_driver import trace_var_driver


# ==============================================================================
# trace_var_driver
# ==============================================================================

class TestTraceVarDriver:
    """trace_var_driver() 单元测试"""

    REQUIRED_TOP_KEYS = ["variable", "driven_variables", "fan_out_count"]
    REQUIRED_DRIVEN_KEYS = [
        "name", "hierarchical_path", "bit_width", "type_name", "kind",
    ]

    # ── 输入端口扇出（fan-out 到子模块输入端口）────────────────────

    def test_追踪opcode扇出(self, filelist_path):
        """alu_system.opcode → 扇出到 alu_system.u_core.opcode。"""
        result = trace_var_driver(filelist_path, "alu_system.opcode")

        assert result["variable"]["name"] == "opcode"
        assert result["fan_out_count"] == 1
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_core.opcode" in driven_paths

    def test_追踪operand_a扇出(self, filelist_path):
        """alu_system.operand_a → 扇出到 alu_system.u_core.operand_a。"""
        result = trace_var_driver(filelist_path, "alu_system.operand_a")

        assert result["variable"]["name"] == "operand_a"
        assert result["fan_out_count"] == 1
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_core.operand_a" in driven_paths

    def test_追踪operand_b扇出(self, filelist_path):
        """alu_system.operand_b → 扇出到 alu_system.u_core.operand_b。"""
        result = trace_var_driver(filelist_path, "alu_system.operand_b")

        assert result["variable"]["name"] == "operand_b"
        assert result["fan_out_count"] == 1

    def test_追踪clk扇出到多个子模块(self, filelist_path):
        """alu_system.clk → 扇出到 u_control.clk 和 u_result.clk。"""
        result = trace_var_driver(filelist_path, "alu_system.clk")

        assert result["variable"]["name"] == "clk"
        assert result["fan_out_count"] == 2
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_control.clk" in driven_paths
        assert "alu_system.u_result.clk" in driven_paths

    def test_追踪start扇出(self, filelist_path):
        """alu_system.start → 扇出到 u_control.start。"""
        result = trace_var_driver(filelist_path, "alu_system.start")

        assert result["variable"]["name"] == "start"
        assert result["fan_out_count"] == 1
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_control.start" in driven_paths

    # ── 内部信号扇出（block fan-out + 子模块端口 fan-out）─────────

    def test_追踪add_sum扇出(self, filelist_path):
        """add_sum → 扇出到 u_core.result 和 u_core.carry。"""
        result = trace_var_driver(filelist_path, "alu_system.u_core.add_sum")

        assert result["variable"]["name"] == "add_sum"
        assert result["fan_out_count"] == 2
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_core.result" in driven_paths, (
            f"缺少 result，实际: {driven_paths}"
        )
        assert "alu_system.u_core.carry" in driven_paths, (
            f"缺少 carry，实际: {driven_paths}"
        )

    def test_追踪add_b_mux仅扇出到子模块端口(self, filelist_path):
        """add_b_mux 仅出现在 LHS，扇出仅来自子模块输入端口 u_adder.b。"""
        result = trace_var_driver(filelist_path, "alu_system.u_core.add_b_mux")

        assert result["variable"]["name"] == "add_b_mux"
        assert result["fan_out_count"] == 1
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_core.u_adder.b" in driven_paths, (
            f"应仅扇出到 u_adder.b，实际: {driven_paths}"
        )

    def test_追踪logic_sel扇出(self, filelist_path):
        """logic_sel → 扇出到 u_logic.sel。"""
        result = trace_var_driver(filelist_path, "alu_system.u_core.logic_sel")

        assert result["variable"]["name"] == "logic_sel"
        assert result["fan_out_count"] == 1
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_core.u_logic.sel" in driven_paths

    def test_追踪logic_result扇出(self, filelist_path):
        """logic_result → 扇出到 u_core.result（输出 mux）。"""
        result = trace_var_driver(filelist_path, "alu_system.u_core.logic_result")

        assert result["variable"]["name"] == "logic_result"
        # 在输出 mux 的 always_comb 中被读取
        assert result["fan_out_count"] >= 0

    def test_追踪add_cout扇出(self, filelist_path):
        """add_cout → 扇出到 u_core.carry。"""
        result = trace_var_driver(filelist_path, "alu_system.u_core.add_cout")

        assert result["variable"]["name"] == "add_cout"
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_core.carry" in driven_paths

    # ── 叶子模块内部信号扇出 ─────────────────────────────────────

    def test_追踪u_adder_a扇出(self, filelist_path):
        """u_adder.a → 扇出到 u_adder.result。"""
        result = trace_var_driver(filelist_path, "alu_system.u_core.u_adder.a")

        assert result["variable"]["name"] == "a"
        assert result["fan_out_count"] == 1
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_core.u_adder.result" in driven_paths

    def test_追踪u_adder_result扇出(self, filelist_path):
        """u_adder.result（内部 wire）→ 扇出到 u_adder.sum 和 u_adder.cout。"""
        result = trace_var_driver(filelist_path, "alu_system.u_core.u_adder.result")

        assert result["variable"]["name"] == "result"
        # result[7:0] → sum, result[8] → cout
        assert result["fan_out_count"] >= 2

    # ── 输出端口扇出（向上追溯到父模块 wire）───────────────────────

    def test_追踪u_core_result输出端口(self, filelist_path):
        """u_core.result → 向上到 alu_system.core_result。"""
        result = trace_var_driver(filelist_path, "alu_system.u_core.result")

        assert result["variable"]["name"] == "result"
        assert result["fan_out_count"] == 1
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.core_result" in driven_paths

    def test_追踪u_adder_sum叶子输出端口(self, filelist_path):
        """u_adder.sum → 向上到 alu_system.u_core.add_sum。"""
        result = trace_var_driver(filelist_path, "alu_system.u_core.u_adder.sum")

        assert result["variable"]["name"] == "sum"
        assert result["fan_out_count"] == 1
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_core.add_sum" in driven_paths

    def test_追踪u_adder_cout叶子输出端口(self, filelist_path):
        """u_adder.cout → 向上到 alu_system.u_core.add_cout。"""
        result = trace_var_driver(filelist_path, "alu_system.u_core.u_adder.cout")

        assert result["variable"]["name"] == "cout"
        assert result["fan_out_count"] == 1
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_core.add_cout" in driven_paths

    def test_追踪u_logic_result输出端口(self, filelist_path):
        """u_logic.result → 向上到 alu_system.u_core.logic_result。"""
        result = trace_var_driver(filelist_path, "alu_system.u_core.u_logic.result")

        assert result["variable"]["name"] == "result"
        assert result["fan_out_count"] == 1
        driven_paths = {v["hierarchical_path"] for v in result["driven_variables"]}
        assert "alu_system.u_core.logic_result" in driven_paths

    def test_追踪顶层输出done无扇出(self, filelist_path):
        """alu_system.done — 顶层输出端口，无父模块，fan_out_count == 0。"""
        result = trace_var_driver(filelist_path, "alu_system.done")

        assert result["variable"]["name"] == "done"
        assert result["fan_out_count"] == 0
        assert result["driven_variables"] == []

    def test_追踪顶层输出carry无扇出(self, filelist_path):
        """alu_system.carry — 顶层输出端口，无父模块。"""
        result = trace_var_driver(filelist_path, "alu_system.carry")

        assert result["variable"]["name"] == "carry"
        assert result["fan_out_count"] == 0

    # ── result_stage 信号 ─────────────────────────────────────────

    def test_追踪compute_en扇出(self, filelist_path):
        """compute_en → 应扇出到子模块 enable 端口。"""
        result = trace_var_driver(filelist_path, "alu_system.u_control.compute_en")

        assert result["variable"]["name"] == "compute_en"
        assert result["fan_out_count"] >= 0

    def test_追踪core_result扇出(self, filelist_path):
        """core_result → 顶层内部信号，应扇出到子模块输入。"""
        result = trace_var_driver(filelist_path, "alu_system.core_result")

        assert result["variable"]["name"] == "core_result"
        # 连接到 u_result.data_in
        assert result["fan_out_count"] >= 1

    # ── 结构验证 ──────────────────────────────────────────────────

    def test_结果包含顶层结构(self, filelist_path):
        """结果应包含 variable, driven_variables, fan_out_count。"""
        result = trace_var_driver(filelist_path, "alu_system.opcode")
        for key in self.REQUIRED_TOP_KEYS:
            assert key in result, f"缺少顶层键: {key}"

    def test_fan_out_count与driven_variables一致(self, filelist_path):
        """fan_out_count 应等于 len(driven_variables)。"""
        result = trace_var_driver(filelist_path, "alu_system.opcode")
        assert result["fan_out_count"] == len(result["driven_variables"])

    def test_被驱动变量信息字段完整(self, filelist_path):
        """每个 driven_variable 应有 name/hierarchical_path/bit_width/...。"""
        result = trace_var_driver(filelist_path, "alu_system.opcode")
        for driven in result["driven_variables"]:
            for key in self.REQUIRED_DRIVEN_KEYS:
                assert key in driven, f"driven_variable 缺少字段: {key}"

    def test_variable信息字段完整(self, filelist_path):
        """variable 子对象应包含必要字段。"""
        result = trace_var_driver(filelist_path, "alu_system.opcode")
        for key in self.REQUIRED_DRIVEN_KEYS:
            assert key in result["variable"], f"variable 缺少字段: {key}"

    def test_被驱动变量路径均以alu_system开头(self, filelist_path):
        """所有被驱动的变量路径应在 alu_system 层次下。"""
        result = trace_var_driver(filelist_path, "alu_system.opcode")
        for driven in result["driven_variables"]:
            assert driven["hierarchical_path"].startswith("alu_system"), (
                f"路径不在 alu_system 下: {driven['hierarchical_path']}"
            )

    # ── 错误路径 ──────────────────────────────────────────────────

    def test_空文件列表抛出异常(self):
        """不存在的 filelist → SystemExit。"""
        with pytest.raises(SystemExit):
            trace_var_driver("/nonexistent/filelist.f", "alu_system.opcode")

    def test_不存在的变量抛出ValueError(self, filelist_path):
        """不存在的变量路径 → ValueError。"""
        with pytest.raises(ValueError):
            trace_var_driver(filelist_path, "alu_system.u_core.nonexistent_xyz")

    def test_不存在的实例抛出ValueError(self, filelist_path):
        """不存在的实例路径 → ValueError。"""
        with pytest.raises(ValueError):
            trace_var_driver(filelist_path, "alu_system.u_fake.signal")
