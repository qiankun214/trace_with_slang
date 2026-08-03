"""
test_hierarchy_var.py — 测试 hierarchy_var.py 的公开一级函数：
  - find_hierarch_var()
"""

import pytest

from hierarchy_var import find_hierarch_var


# ==============================================================================
# find_hierarch_var
# ==============================================================================

class TestFindHierarchVar:
    """find_hierarch_var() 单元测试"""

    REQUIRED_KEYS = [
        "name", "type_name", "bit_width", "kind",
        "hierarchical_path", "instance_path",
    ]

    # ── 内部信号 ──────────────────────────────────────────────────

    def test_查找add_sum(self, hierarchy):
        """alu_system.u_core.add_sum — 位宽 8。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.add_sum")
        assert result["name"] == "add_sum"
        assert result["bit_width"] == 8
        assert result["type_name"] == "logic[7:0]"
        assert result["instance_path"] == "alu_system.u_core"

    def test_查找add_b_mux(self, hierarchy):
        """alu_system.u_core.add_b_mux — 位宽 8。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.add_b_mux")
        assert result["name"] == "add_b_mux"
        assert result["bit_width"] == 8
        assert result["type_name"] == "logic[7:0]"

    def test_查找add_cin(self, hierarchy):
        """alu_system.u_core.add_cin — 标量、位宽 1。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.add_cin")
        assert result["name"] == "add_cin"
        assert result["bit_width"] == 1
        assert result["type_name"] == "logic"

    def test_查找add_cout(self, hierarchy):
        """alu_system.u_core.add_cout — 标量、位宽 1。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.add_cout")
        assert result["name"] == "add_cout"
        assert result["bit_width"] == 1

    def test_查找logic_sel(self, hierarchy):
        """alu_system.u_core.logic_sel — 位宽 2。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.logic_sel")
        assert result["name"] == "logic_sel"
        assert result["bit_width"] == 2
        assert result["type_name"] == "logic[1:0]"

    def test_查找logic_result(self, hierarchy):
        """alu_system.u_core.logic_result — 位宽 8。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.logic_result")
        assert result["name"] == "logic_result"
        assert result["bit_width"] == 8

    # ── 枚举类型 ──────────────────────────────────────────────────

    def test_查找枚举类型state_reg(self, hierarchy):
        """alu_system.u_control.state_reg — 位宽 2、枚举类型。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_control.state_reg")
        assert result["name"] == "state_reg"
        assert result["bit_width"] == 2
        assert "state_t" in result["type_name"], (
            f"type_name 应包含 'state_t': {result['type_name']}"
        )

    def test_查找state_next(self, hierarchy):
        """alu_system.u_control.state_next — 枚举类型。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_control.state_next")
        assert result["name"] == "state_next"
        assert "state_t" in result["type_name"]

    # ── 端口 ──────────────────────────────────────────────────────

    def test_查找输入端口opcode(self, hierarchy):
        """alu_system.opcode — 位宽 3。"""
        result = find_hierarch_var(hierarchy, "alu_system.opcode")
        assert result["name"] == "opcode"
        assert result["bit_width"] == 3
        assert result["type_name"] == "logic[2:0]"
        assert result["instance_path"] == "alu_system"

    def test_查找标量端口done(self, hierarchy):
        """alu_system.done — 标量输出端口。"""
        result = find_hierarch_var(hierarchy, "alu_system.done")
        assert result["name"] == "done"
        assert result["bit_width"] == 1
        assert result["type_name"] == "logic"

    def test_查找标量端口clk(self, hierarchy):
        """alu_system.clk — 标量输入端口。"""
        result = find_hierarch_var(hierarchy, "alu_system.clk")
        assert result["name"] == "clk"
        assert result["bit_width"] == 1

    def test_查找8位输入端口operand_a(self, hierarchy):
        """alu_system.operand_a — 位宽 8。"""
        result = find_hierarch_var(hierarchy, "alu_system.operand_a")
        assert result["name"] == "operand_a"
        assert result["bit_width"] == 8

    def test_查找输出端口result(self, hierarchy):
        """alu_system.u_core.result — 位宽 8。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.result")
        assert result["name"] == "result"
        assert result["bit_width"] == 8
        assert result["instance_path"] == "alu_system.u_core"

    def test_查找carry输出端口(self, hierarchy):
        """alu_system.u_core.carry — 标量输出。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.carry")
        assert result["name"] == "carry"
        assert result["bit_width"] == 1

    # ── 叶子模块变量 ──────────────────────────────────────────────

    def test_查找叶子模块sum(self, hierarchy):
        """alu_system.u_core.u_adder.sum — 位宽 8。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.u_adder.sum")
        assert result["name"] == "sum"
        assert result["bit_width"] == 8
        assert result["instance_path"] == "alu_system.u_core.u_adder"

    def test_查找叶子模块a输入(self, hierarchy):
        """alu_system.u_core.u_adder.a — 位宽 8。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.u_adder.a")
        assert result["name"] == "a"
        assert result["bit_width"] == 8

    def test_查找叶子模块cin(self, hierarchy):
        """alu_system.u_core.u_adder.cin — 标量。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.u_adder.cin")
        assert result["name"] == "cin"
        assert result["bit_width"] == 1

    def test_查找logic_unit_result(self, hierarchy):
        """alu_system.u_core.u_logic.result — 位宽 8。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.u_logic.result")
        assert result["name"] == "result"
        assert result["bit_width"] == 8
        assert result["instance_path"] == "alu_system.u_core.u_logic"

    def test_查找logic_unit_sel(self, hierarchy):
        """alu_system.u_core.u_logic.sel — 位宽 2。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.u_logic.sel")
        assert result["name"] == "sel"
        assert result["bit_width"] == 2

    # ── result_stage 变量 ─────────────────────────────────────────

    def test_查找result_stage_data_out(self, hierarchy):
        """alu_system.u_result.data_out — 位宽 8。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_result.data_out")
        assert result["name"] == "data_out"
        assert result["bit_width"] == 8
        assert result["instance_path"] == "alu_system.u_result"

    def test_查找result_stage_en(self, hierarchy):
        """alu_system.u_result.en — 标量。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_result.en")
        assert result["name"] == "en"
        assert result["bit_width"] == 1

    # ── 结构验证 ──────────────────────────────────────────────────

    def test_返回结果包含所有必要字段(self, hierarchy):
        """返回的 dict 应包含全部 6 个必要字段。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.add_sum")
        for key in self.REQUIRED_KEYS:
            assert key in result, f"缺少字段: {key}"

    def test_type_name非空字符串(self, hierarchy):
        """type_name 应为非空字符串。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.add_sum")
        assert isinstance(result["type_name"], str)
        assert len(result["type_name"]) > 0

    def test_hierarchical_path等于输入路径(self, hierarchy):
        """返回的 hierarchical_path 应等于输入的 var_path。"""
        var_path = "alu_system.u_core.add_b_mux"
        result = find_hierarch_var(hierarchy, var_path)
        assert result["hierarchical_path"] == var_path

    def test_kind为合法值(self, hierarchy):
        """kind 应为 variable/net/parameter 等合法符号种类。"""
        result = find_hierarch_var(hierarchy, "alu_system.u_core.add_sum")
        assert result["kind"] in (
            "variable", "net", "parameter", "enum_value",
            "genvar", "field", "modport",
        )

    # ── 错误路径 ──────────────────────────────────────────────────

    def test_路径段数不足抛出ValueError(self, hierarchy):
        """单段路径应抛出 ValueError。"""
        with pytest.raises(ValueError, match="至少需要两段"):
            find_hierarch_var(hierarchy, "alu_system")

    def test_不存在的实例路径抛出ValueError(self, hierarchy):
        """不存在的实例路径应抛出 ValueError。"""
        with pytest.raises(ValueError, match="层次路径不存在"):
            find_hierarch_var(hierarchy, "alu_system.u_fake.add_sum")

    def test_不存在的变量抛出ValueError(self, hierarchy):
        """存在的实例但变量不存在应抛出 ValueError。"""
        with pytest.raises(ValueError, match="未找到"):
            find_hierarch_var(hierarchy, "alu_system.u_core.nonexistent_var")

    def test_空层次字典抛出ValueError(self):
        """空层次字典应抛出 ValueError。"""
        with pytest.raises(ValueError):
            find_hierarch_var({}, "alu_system.u_core.add_sum")
