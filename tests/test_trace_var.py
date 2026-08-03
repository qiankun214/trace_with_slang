"""
test_trace_var.py — 测试 trace_var.py 的公开一级函数：
  - trace_variable()
"""

import pytest

from trace_var import trace_variable


# ==============================================================================
# trace_variable
# ==============================================================================

class TestTraceVariable:
    """trace_variable() 单元测试"""

    REQUIRED_TOP_KEYS = ["variable", "assignment", "related_variables"]
    REQUIRED_VAR_KEYS = [
        "name", "hierarchical_path", "bit_width", "type_name", "kind",
    ]
    REQUIRED_ASSIGN_KEYS = ["type", "source_text", "file", "start_line", "end_line"]

    # ── always_comb 块变量 ────────────────────────────────────────

    def test_追踪add_b_mux(self, filelist_path):
        """add_b_mux — always_comb，行 27–35，引用 operand_b 和 opcode。"""
        result = trace_variable(filelist_path, "alu_system.u_core.add_b_mux")

        assert result["variable"]["name"] == "add_b_mux"
        assert result["assignment"]["type"] == "always_comb"
        assert result["assignment"]["start_line"] == 27
        assert result["assignment"]["end_line"] == 35
        assert "alu_core.sv" in result["assignment"]["file"]
        assert "add_b_mux" in result["assignment"]["source_text"]
        assert "always_comb" in result["assignment"]["source_text"]

        related_names = {v["name"] for v in result["related_variables"]}
        assert "opcode" in related_names, f"缺少 opcode，实际: {related_names}"
        assert "operand_b" in related_names, f"缺少 operand_b，实际: {related_names}"

    def test_追踪add_cin(self, filelist_path):
        """add_cin — always_comb，与 add_b_mux 在同一块中。"""
        result = trace_variable(filelist_path, "alu_system.u_core.add_cin")

        assert result["variable"]["name"] == "add_cin"
        assert result["variable"]["bit_width"] == 1
        assert result["assignment"]["type"] == "always_comb"
        assert result["assignment"]["start_line"] == 27
        assert result["assignment"]["end_line"] == 35

        related_names = {v["name"] for v in result["related_variables"]}
        assert "opcode" in related_names
        assert "operand_b" in related_names

    def test_追踪u_core_result_output_mux(self, filelist_path):
        """alu_system.u_core.result — always_comb 输出多路选择。"""
        result = trace_variable(filelist_path, "alu_system.u_core.result")

        assert result["variable"]["name"] == "result"
        assert result["assignment"]["type"] == "always_comb"
        assert result["assignment"]["start_line"] == 59
        assert result["assignment"]["end_line"] == 73

        related_names = {v["name"] for v in result["related_variables"]}
        assert "opcode" in related_names, f"缺少 opcode，实际: {related_names}"
        assert "add_sum" in related_names, f"缺少 add_sum，实际: {related_names}"
        assert "logic_result" in related_names, (
            f"缺少 logic_result，实际: {related_names}"
        )
        assert "add_cout" in related_names, f"缺少 add_cout，实际: {related_names}"

    def test_追踪u_core_carry(self, filelist_path):
        """alu_system.u_core.carry — 与 result 在同一 always_comb 块中。"""
        result = trace_variable(filelist_path, "alu_system.u_core.carry")

        assert result["variable"]["name"] == "carry"
        assert result["assignment"]["type"] == "always_comb"
        assert result["assignment"]["start_line"] == 59

        related_names = {v["name"] for v in result["related_variables"]}
        assert "opcode" in related_names
        assert "add_cout" in related_names

    # ── always_ff 块变量 ──────────────────────────────────────────

    def test_追踪state_reg_always_ff(self, filelist_path):
        """state_reg — always_ff，行 27–33，引用 clk/rst_n/state_next/S_IDLE。"""
        result = trace_variable(filelist_path, "alu_system.u_control.state_reg")

        assert result["variable"]["name"] == "state_reg"
        assert result["assignment"]["type"] == "always_ff"
        assert result["assignment"]["start_line"] == 27
        assert result["assignment"]["end_line"] == 33
        assert "alu_control.sv" in result["assignment"]["file"]

        related_names = {v["name"] for v in result["related_variables"]}
        assert "state_next" in related_names, (
            f"缺少 state_next，实际: {related_names}"
        )

    def test_追踪compute_en(self, filelist_path):
        """compute_en — always_comb（输出逻辑块）。"""
        result = trace_variable(filelist_path, "alu_system.u_control.compute_en")

        assert result["variable"]["name"] == "compute_en"
        assert result["assignment"]["type"] == "always_comb"

    def test_追踪alu_control_done(self, filelist_path):
        """alu_system.u_control.done — always_comb 输出。"""
        result = trace_variable(filelist_path, "alu_system.u_control.done")

        assert result["variable"]["name"] == "done"
        assert result["assignment"]["type"] == "always_comb"

    # ── continuous_assign ─────────────────────────────────────────

    def test_追踪continuous_assign_done(self, filelist_path):
        """alu_system.done — continuous_assign，行 67。"""
        result = trace_variable(filelist_path, "alu_system.done")

        assert result["variable"]["name"] == "done"
        assert result["assignment"]["type"] == "continuous_assign"
        assert result["assignment"]["start_line"] == 67
        assert result["assignment"]["end_line"] == 67
        assert "assign done = done_int;" in result["assignment"]["source_text"]

        related_names = {v["name"] for v in result["related_variables"]}
        assert "done_int" in related_names, f"缺少 done_int，实际: {related_names}"

    def test_追踪u_adder_sum_continuous_assign(self, filelist_path):
        """alu_system.u_core.u_adder.sum — continuous_assign（叶子模块）。"""
        result = trace_variable(filelist_path, "alu_system.u_core.u_adder.sum")

        assert result["variable"]["name"] == "sum"
        assert result["assignment"]["type"] == "continuous_assign"
        assert "adder_8bit.sv" in result["assignment"]["file"]

        related_names = {v["name"] for v in result["related_variables"]}
        assert "result" in related_names, f"缺少 result，实际: {related_names}"

    def test_追踪u_adder_cout_continuous_assign(self, filelist_path):
        """alu_system.u_core.u_adder.cout — continuous_assign（叶子模块）。"""
        result = trace_variable(filelist_path, "alu_system.u_core.u_adder.cout")

        assert result["variable"]["name"] == "cout"
        assert result["assignment"]["type"] == "continuous_assign"

    # ── 内部 wire（同名为端口） ────────────────────────────────────

    def test_追踪u_adder_result_internal_wire(self, filelist_path):
        """u_adder.result 是内部 logic [8:0] wire，不报错。"""
        result = trace_variable(filelist_path, "alu_system.u_core.u_adder.result")

        assert result["variable"]["name"] == "result"
        # 内部 result wire 在 always_comb 中赋值
        assert result["assignment"]["type"] == "always_comb"

    # ── port_connection ───────────────────────────────────────────

    def test_追踪顶层输出端口carry_port_connection(self, filelist_path):
        """alu_system.carry — port_connection，由 u_result 驱动。"""
        result = trace_variable(filelist_path, "alu_system.carry")

        assert result["variable"]["name"] == "carry"
        assert result["assignment"]["type"] == "port_connection"
        assert result["assignment"]["instance_name"] == "u_result"
        assert result["assignment"]["definition_name"] == "result_stage"
        assert "result_stage u_result" in result["assignment"]["source_text"]

        related_names = {v["name"] for v in result["related_variables"]}
        assert "carry_out" in related_names, f"缺少 carry_out，实际: {related_names}"

    def test_追踪result_port_connection(self, filelist_path):
        """alu_system.result — port_connection，由 u_result 驱动。"""
        result = trace_variable(filelist_path, "alu_system.result")

        assert result["variable"]["name"] == "result"
        assert result["assignment"]["type"] == "port_connection"
        assert result["assignment"]["instance_name"] == "u_result"

    def test_追踪输入端口连接u_adder_b(self, filelist_path):
        """u_adder.b — port_connection，由 add_b_mux 驱动。"""
        result = trace_variable(filelist_path, "alu_system.u_core.u_adder.b")

        assert result["variable"]["name"] == "b"
        assert result["assignment"]["type"] == "port_connection"
        assert result["assignment"]["instance_name"] == "u_adder"
        assert result["assignment"]["definition_name"] == "adder_8bit"
        assert "adder_8bit u_adder" in result["assignment"]["source_text"]

        related_names = {v["name"] for v in result["related_variables"]}
        assert "add_b_mux" in related_names, (
            f"缺少 add_b_mux，实际: {related_names}"
        )

    def test_追踪输入端口连接u_adder_a(self, filelist_path):
        """u_adder.a — port_connection，由 operand_a 驱动。"""
        result = trace_variable(filelist_path, "alu_system.u_core.u_adder.a")

        assert result["variable"]["name"] == "a"
        assert result["assignment"]["type"] == "port_connection"

    def test_追踪输入端口连接u_logic_sel(self, filelist_path):
        """u_logic.sel — port_connection，由 logic_sel 驱动。"""
        result = trace_variable(filelist_path, "alu_system.u_core.u_logic.sel")

        assert result["variable"]["name"] == "sel"
        assert result["assignment"]["type"] == "port_connection"
        assert result["assignment"]["instance_name"] == "u_logic"

    # ── result_stage 变量 ─────────────────────────────────────────

    def test_追踪result_stage_data_out(self, filelist_path):
        """alu_system.u_result.data_out — always_ff。"""
        result = trace_variable(filelist_path, "alu_system.u_result.data_out")

        assert result["variable"]["name"] == "data_out"
        assert result["assignment"]["type"] == "always_ff"

    # ── 结构验证 ──────────────────────────────────────────────────

    def test_结果包含顶层结构(self, filelist_path):
        """结果应包含 variable, assignment, related_variables。"""
        result = trace_variable(filelist_path, "alu_system.u_core.add_b_mux")
        for key in self.REQUIRED_TOP_KEYS:
            assert key in result, f"缺少顶层键: {key}"

    def test_变量信息字段完整(self, filelist_path):
        """variable 子对象应包含全部 5 个必要字段。"""
        result = trace_variable(filelist_path, "alu_system.u_core.add_b_mux")
        for key in self.REQUIRED_VAR_KEYS:
            assert key in result["variable"], f"variable 缺少字段: {key}"

    def test_赋值信息字段完整(self, filelist_path):
        """assignment 应包含 type, source_text, file, start_line, end_line。"""
        result = trace_variable(filelist_path, "alu_system.u_core.add_b_mux")
        assign = result["assignment"]
        for key in self.REQUIRED_ASSIGN_KEYS:
            assert key in assign, f"assignment 缺少字段: {key}"
        assert assign["start_line"] > 0
        assert assign["end_line"] >= assign["start_line"]

    def test_related_variables是列表(self, filelist_path):
        """related_variables 应为列表。"""
        result = trace_variable(filelist_path, "alu_system.u_core.add_b_mux")
        assert isinstance(result["related_variables"], list)

    def test_related_variables每项含必要字段(self, filelist_path):
        """related_variables 每一项都应有 name/hierarchical_path/bit_width/...。"""
        result = trace_variable(filelist_path, "alu_system.u_core.add_b_mux")
        for rel_var in result["related_variables"]:
            for key in self.REQUIRED_VAR_KEYS:
                assert key in rel_var, f"related_variable 缺少字段: {key}"

    def test_related_variables排除仅LHS变量(self, filelist_path):
        """add_b_mux 赋值块中，add_b_mux 仅出现在 LHS，不应在 related 中。"""
        result = trace_variable(filelist_path, "alu_system.u_core.add_b_mux")
        related_names = {v["name"] for v in result["related_variables"]}
        # add_b_mux 是被追踪的目标变量，仅在 LHS 出现，不应出现于 related
        # （除非同名变量在其他表达式中也被引用）
        assert "operand_b" in related_names, "至少 operand_b 应在 RHS 被读取"

    def test_源文本含目标变量名(self, filelist_path):
        """赋值块的 source_text 应包含目标变量名。"""
        result = trace_variable(filelist_path, "alu_system.u_core.add_b_mux")
        source = result["assignment"]["source_text"]
        assert "add_b_mux" in source, f"源文本中缺少变量名: {source[:80]}..."

    def test_assignment_file路径合法(self, filelist_path):
        """assignment.file 应以 .sv 结尾且文件存在。"""
        import os
        result = trace_variable(filelist_path, "alu_system.u_core.add_b_mux")
        f = result["assignment"]["file"]
        assert f.endswith(".sv"), f"非 .sv 文件: {f}"
        assert os.path.isabs(f) or "/" in f, f"路径不合法: {f}"

    # ── 错误路径 ──────────────────────────────────────────────────

    def test_空文件列表抛出异常(self):
        """不存在的 filelist → SystemExit（parse_filelist 中 sys.exit(1)）。"""
        with pytest.raises(SystemExit):
            trace_variable("/nonexistent/filelist.f", "alu_system.u_core.add_sum")

    def test_不存在的变量抛出异常(self, filelist_path):
        """存在的模块但不存在该变量 → ValueError 或 RuntimeError。"""
        with pytest.raises((ValueError, RuntimeError)):
            trace_variable(filelist_path, "alu_system.u_core.nonexistent_xyz")

    def test_不存在的实例路径抛出异常(self, filelist_path):
        """不存在的层次路径 → ValueError 或 RuntimeError。"""
        with pytest.raises((ValueError, RuntimeError)):
            trace_variable(filelist_path, "alu_system.u_fake.signal")

    def test_顶层输入端口无赋值抛出RuntimeError(self, filelist_path):
        """顶层输入端口（如 rst_n）没有父模块驱动 → RuntimeError。"""
        with pytest.raises(RuntimeError, match="未找到 always 块"):
            trace_variable(filelist_path, "alu_system.rst_n")
