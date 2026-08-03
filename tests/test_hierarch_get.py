"""
test_hierarch_get.py — 测试 hierarch_get.py 的公开一级函数：
  - find_instance_paths_for_file()
  - find_variable_paths()
"""

import os
import pytest

from hierarch_get import find_instance_paths_for_file, find_variable_paths


# ==============================================================================
# find_instance_paths_for_file
# ==============================================================================

class TestFindInstancePathsForFile:
    """find_instance_paths_for_file() 单元测试"""

    def test_查找adder_8bit的实例路径(self, hierarchy, test_fixture_dir):
        """adder_8bit.sv → ['alu_system.u_core.u_adder']。"""
        adder_path = os.path.join(test_fixture_dir, "adder_8bit.sv")
        result = find_instance_paths_for_file(hierarchy, adder_path)
        assert result == ["alu_system.u_core.u_adder"]

    def test_查找logic_unit的实例路径(self, hierarchy, test_fixture_dir):
        """logic_unit.sv → ['alu_system.u_core.u_logic']。"""
        logic_path = os.path.join(test_fixture_dir, "logic_unit.sv")
        result = find_instance_paths_for_file(hierarchy, logic_path)
        assert result == ["alu_system.u_core.u_logic"]

    def test_查找alu_core的实例路径(self, hierarchy, test_fixture_dir):
        """alu_core.sv → ['alu_system.u_core']。"""
        core_path = os.path.join(test_fixture_dir, "alu_core.sv")
        result = find_instance_paths_for_file(hierarchy, core_path)
        assert result == ["alu_system.u_core"]

    def test_查找alu_control的实例路径(self, hierarchy, test_fixture_dir):
        """alu_control.sv → ['alu_system.u_control']。"""
        ctrl_path = os.path.join(test_fixture_dir, "alu_control.sv")
        result = find_instance_paths_for_file(hierarchy, ctrl_path)
        assert result == ["alu_system.u_control"]

    def test_查找result_stage的实例路径(self, hierarchy, test_fixture_dir):
        """result_stage.sv → ['alu_system.u_result']。"""
        rs_path = os.path.join(test_fixture_dir, "result_stage.sv")
        result = find_instance_paths_for_file(hierarchy, rs_path)
        assert result == ["alu_system.u_result"]

    def test_查找顶层模块的实例路径(self, hierarchy, test_fixture_dir):
        """alu_system.sv → ['alu_system']。"""
        sys_path = os.path.join(test_fixture_dir, "alu_system.sv")
        result = find_instance_paths_for_file(hierarchy, sys_path)
        assert result == ["alu_system"]

    def test_支持绝对路径查找(self, hierarchy, test_fixture_dir):
        """绝对路径也应能匹配。"""
        abs_path = os.path.abspath(
            os.path.join(test_fixture_dir, "adder_8bit.sv")
        )
        result = find_instance_paths_for_file(hierarchy, abs_path)
        assert result == ["alu_system.u_core.u_adder"]

    def test_不匹配的文件返回空列表(self, hierarchy):
        """不存在的文件应返回空列表。"""
        result = find_instance_paths_for_file(hierarchy, "/nonexistent/file.sv")
        assert result == []

    def test_空层次字典返回空列表(self):
        """空字典应返回空列表。"""
        result = find_instance_paths_for_file({}, "adder_8bit.sv")
        assert result == []


# ==============================================================================
# find_variable_paths
# ==============================================================================

class TestFindVariablePaths:
    """find_variable_paths() 单元测试"""

    # ── adder_8bit 变量 ────────────────────────────────────────────

    def test_查找adder中sum变量(self, hierarchy, test_fixture_dir):
        """adder_8bit.sv + 'sum' → ['alu_system.u_core.u_adder.sum']。"""
        adder_path = os.path.join(test_fixture_dir, "adder_8bit.sv")
        result = find_variable_paths(hierarchy, adder_path, "sum")
        assert result == ["alu_system.u_core.u_adder.sum"]

    def test_查找adder中cout变量(self, hierarchy, test_fixture_dir):
        """adder_8bit.sv + 'cout' → ['alu_system.u_core.u_adder.cout']。"""
        adder_path = os.path.join(test_fixture_dir, "adder_8bit.sv")
        result = find_variable_paths(hierarchy, adder_path, "cout")
        assert result == ["alu_system.u_core.u_adder.cout"]

    def test_查找adder中a变量(self, hierarchy, test_fixture_dir):
        """adder_8bit.sv + 'a' → ['alu_system.u_core.u_adder.a']。"""
        adder_path = os.path.join(test_fixture_dir, "adder_8bit.sv")
        result = find_variable_paths(hierarchy, adder_path, "a")
        assert result == ["alu_system.u_core.u_adder.a"]

    def test_查找adder中b变量(self, hierarchy, test_fixture_dir):
        """adder_8bit.sv + 'b' → ['alu_system.u_core.u_adder.b']。"""
        adder_path = os.path.join(test_fixture_dir, "adder_8bit.sv")
        result = find_variable_paths(hierarchy, adder_path, "b")
        assert result == ["alu_system.u_core.u_adder.b"]

    def test_查找adder中cin变量(self, hierarchy, test_fixture_dir):
        """adder_8bit.sv + 'cin' → ['alu_system.u_core.u_adder.cin']。"""
        adder_path = os.path.join(test_fixture_dir, "adder_8bit.sv")
        result = find_variable_paths(hierarchy, adder_path, "cin")
        assert result == ["alu_system.u_core.u_adder.cin"]

    def test_查找adder中result变量(self, hierarchy, test_fixture_dir):
        """adder_8bit.sv + 'result' → result 是内部 wire，也在 adder 中。"""
        adder_path = os.path.join(test_fixture_dir, "adder_8bit.sv")
        result = find_variable_paths(hierarchy, adder_path, "result")
        assert "alu_system.u_core.u_adder.result" in result

    # ── logic_unit 变量 ────────────────────────────────────────────

    def test_查找logic_unit中result变量(self, hierarchy, test_fixture_dir):
        """logic_unit.sv + 'result' → ['alu_system.u_core.u_logic.result']。"""
        logic_path = os.path.join(test_fixture_dir, "logic_unit.sv")
        result = find_variable_paths(hierarchy, logic_path, "result")
        assert result == ["alu_system.u_core.u_logic.result"]

    def test_查找logic_unit中sel变量(self, hierarchy, test_fixture_dir):
        """logic_unit.sv + 'sel' → ['alu_system.u_core.u_logic.sel']。"""
        logic_path = os.path.join(test_fixture_dir, "logic_unit.sv")
        result = find_variable_paths(hierarchy, logic_path, "sel")
        assert result == ["alu_system.u_core.u_logic.sel"]

    def test_查找logic_unit中a变量(self, hierarchy, test_fixture_dir):
        """logic_unit.sv + 'a' → ['alu_system.u_core.u_logic.a']。"""
        logic_path = os.path.join(test_fixture_dir, "logic_unit.sv")
        result = find_variable_paths(hierarchy, logic_path, "a")
        assert result == ["alu_system.u_core.u_logic.a"]

    # ── alu_core 内部变量 ─────────────────────────────────────────

    def test_查找alu_core中add_sum(self, hierarchy, test_fixture_dir):
        """alu_core.sv + 'add_sum' → ['alu_system.u_core.add_sum']。"""
        core_path = os.path.join(test_fixture_dir, "alu_core.sv")
        result = find_variable_paths(hierarchy, core_path, "add_sum")
        assert result == ["alu_system.u_core.add_sum"]

    def test_查找alu_core中opcode(self, hierarchy, test_fixture_dir):
        """alu_core.sv + 'opcode' → ['alu_system.u_core.opcode']。"""
        core_path = os.path.join(test_fixture_dir, "alu_core.sv")
        result = find_variable_paths(hierarchy, core_path, "opcode")
        assert result == ["alu_system.u_core.opcode"]

    def test_查找alu_core中operand_a(self, hierarchy, test_fixture_dir):
        """alu_core.sv + 'operand_a' → ['alu_system.u_core.operand_a']。"""
        core_path = os.path.join(test_fixture_dir, "alu_core.sv")
        result = find_variable_paths(hierarchy, core_path, "operand_a")
        assert result == ["alu_system.u_core.operand_a"]

    # ── 顶层模块变量 ──────────────────────────────────────────────

    def test_查找alu_system中done(self, hierarchy, test_fixture_dir):
        """alu_system.sv + 'done' → ['alu_system.done']。"""
        sys_path = os.path.join(test_fixture_dir, "alu_system.sv")
        result = find_variable_paths(hierarchy, sys_path, "done")
        assert result == ["alu_system.done"]

    def test_查找alu_system中core_result(self, hierarchy, test_fixture_dir):
        """alu_system.sv + 'core_result' → 顶层内部信号。"""
        sys_path = os.path.join(test_fixture_dir, "alu_system.sv")
        result = find_variable_paths(hierarchy, sys_path, "core_result")
        assert len(result) >= 1

    # ── 边界情况 ──────────────────────────────────────────────────

    def test_不存在的变量返回空列表(self, hierarchy, test_fixture_dir):
        """存在的文件但变量不存在应返回空列表。"""
        adder_path = os.path.join(test_fixture_dir, "adder_8bit.sv")
        result = find_variable_paths(hierarchy, adder_path, "nonexistent_var_xyz")
        assert result == []

    def test_文件不在层次中返回空列表(self, hierarchy):
        """不存在的文件应返回空列表。"""
        result = find_variable_paths(hierarchy, "/nonexistent/file.sv", "sum")
        assert result == []

    def test_空层次字典返回空列表(self):
        """空字典应返回空列表。"""
        result = find_variable_paths({}, "adder_8bit.sv", "sum")
        assert result == []
