"""
test_hierarchy.py — 测试 hierarchy.py 的公开一级函数：
  - parse_filelist()
  - extract_hierarchy()
"""

import os
import pytest

from hierarchy import parse_filelist, extract_hierarchy


# ==============================================================================
# parse_filelist
# ==============================================================================

class TestParseFilelist:
    """parse_filelist() 单元测试"""

    def test_返回绝对路径列表(self, filelist_path, sv_files):
        """解析 filelist.f 应返回 6 个绝对路径。"""
        assert isinstance(sv_files, list)
        assert len(sv_files) == 6
        for f in sv_files:
            assert os.path.isabs(f), f"路径不是绝对路径: {f}"
            assert os.path.exists(f), f"文件不存在: {f}"
            assert f.endswith(".sv"), f"不是 .sv 文件: {f}"

    def test_保持文件列表顺序(self, filelist_path, sv_files):
        """返回的文件顺序应与 filelist.f 中的顺序一致（自底向上）。"""
        basenames = [os.path.basename(f) for f in sv_files]
        expected_order = [
            "adder_8bit.sv",
            "logic_unit.sv",
            "alu_core.sv",
            "alu_control.sv",
            "result_stage.sv",
            "alu_system.sv",
        ]
        assert basenames == expected_order, f"顺序不匹配: {basenames}"

    def test_路径解析基于filelist所在目录(self, filelist_path, sv_files, test_fixture_dir):
        """所有解析后的路径应位于 fixture 目录下。"""
        for f in sv_files:
            assert os.path.dirname(f) == test_fixture_dir, (
                f"路径不在 fixture 目录: {f}"
            )

    def test_跳过注释和空行(self, filelist_path, sv_files):
        """结果中不应包含注释行或空行内容。"""
        for f in sv_files:
            basename = os.path.basename(f)
            assert not basename.startswith("#"), f"结果包含注释: {f}"
            assert basename != "", f"结果包含空行路径: {f}"

    def test_仅注释和空行的文件列表返回空(self, tmp_path):
        """只有注释和空行的 filelist 应返回空列表。"""
        p = tmp_path / "comments_only.f"
        p.write_text("# only comments\n\n# nothing else\n")
        result = parse_filelist(str(p))
        assert result == []

    def test_文件不存在则退出(self, tmp_path):
        """不存在的 filelist 应调用 sys.exit(1)。"""
        bad_path = str(tmp_path / "nonexistent.f")
        with pytest.raises(SystemExit) as exc_info:
            parse_filelist(bad_path)
        assert exc_info.value.code == 1

    def test_缺失sv文件打印警告(self, tmp_path, capsys):
        """filelist 中指向不存在的 SV 文件应打印 stderr 警告但不中断。"""
        filelist = tmp_path / "test.f"
        filelist.write_text("nonexistent_module.sv\n")
        result = parse_filelist(str(filelist))
        assert result == []
        captured = capsys.readouterr()
        assert "警告" in captured.err or "warning" in captured.err.lower()


# ==============================================================================
# extract_hierarchy
# ==============================================================================

class TestExtractHierarchy:
    """extract_hierarchy() 单元测试"""

    EXPECTED_PATHS = [
        "alu_system",
        "alu_system.u_control",
        "alu_system.u_core",
        "alu_system.u_result",
        "alu_system.u_core.u_adder",
        "alu_system.u_core.u_logic",
    ]

    REQUIRED_ENTRY_KEYS = ["module", "file", "ast", "ports"]
    REQUIRED_PORT_KEYS = ["name", "direction", "width"]

    def test_返回字典(self, hierarchy):
        """extract_hierarchy 应该返回 dict。"""
        assert isinstance(hierarchy, dict)

    def test_包含预期的层次路径(self, hierarchy):
        """返回的层次字典应包含全部 6 个预期路径。"""
        for path in self.EXPECTED_PATHS:
            assert path in hierarchy, f"缺少层次路径: {path}"

    def test_层次路径数量为6(self, hierarchy):
        """只有 6 个实例（3 级层次、3+2+1 个模块）。"""
        assert len(hierarchy) == 6

    def test_顶层模块名正确(self, hierarchy):
        """顶层条目 module 字段应为 'alu_system'。"""
        assert hierarchy["alu_system"]["module"] == "alu_system"

    def test_alu_core模块名正确(self, hierarchy):
        """alu_system.u_core 的 module 应为 'alu_core'。"""
        assert hierarchy["alu_system.u_core"]["module"] == "alu_core"

    def test_alu_control模块名正确(self, hierarchy):
        """alu_system.u_control 的 module 应为 'alu_control'。"""
        assert hierarchy["alu_system.u_control"]["module"] == "alu_control"

    def test_result_stage模块名正确(self, hierarchy):
        """alu_system.u_result 的 module 应为 'result_stage'。"""
        assert hierarchy["alu_system.u_result"]["module"] == "result_stage"

    def test_adder_8bit模块名正确(self, hierarchy):
        """alu_system.u_core.u_adder 的 module 应为 'adder_8bit'。"""
        assert hierarchy["alu_system.u_core.u_adder"]["module"] == "adder_8bit"

    def test_logic_unit模块名正确(self, hierarchy):
        """alu_system.u_core.u_logic 的 module 应为 'logic_unit'。"""
        assert hierarchy["alu_system.u_core.u_logic"]["module"] == "logic_unit"

    def test_条目结构正确(self, hierarchy):
        """每个条目的值应包含 module, file, ast, ports 四个键。"""
        for path, entry in hierarchy.items():
            for key in self.REQUIRED_ENTRY_KEYS:
                assert key in entry, f"{path} 缺少键: {key}"

    def test_ast_是有效的InstanceBodySymbol(self, hierarchy):
        """每个条目的 ast 应为 pyslang InstanceBodySymbol。"""
        from pyslang import ast as pyslang_ast

        for path, entry in hierarchy.items():
            ast_obj = entry["ast"]
            assert ast_obj is not None, f"{path} 的 ast 为 None"
            assert isinstance(
                ast_obj, pyslang_ast.InstanceBodySymbol
            ), f"{path} 的 ast 类型错误: {type(ast_obj)}"

    def test_文件路径以sv结尾(self, hierarchy):
        """每个条目的 file 应以 .sv 结尾。"""
        for path, entry in hierarchy.items():
            assert entry["file"].endswith(".sv"), (
                f"{path} 的文件不以 .sv 结尾: {entry['file']}"
            )

    def test_文件路径对应正确的源文件(self, hierarchy):
        """每个实例的 file 应对应其定义所在的源文件。"""
        expected_files = {
            "alu_system":                "alu_system.sv",
            "alu_system.u_control":      "alu_control.sv",
            "alu_system.u_core":         "alu_core.sv",
            "alu_system.u_result":       "result_stage.sv",
            "alu_system.u_core.u_adder": "adder_8bit.sv",
            "alu_system.u_core.u_logic": "logic_unit.sv",
        }
        for path, expected_basename in expected_files.items():
            actual = os.path.basename(hierarchy[path]["file"])
            assert actual == expected_basename, (
                f"{path} 文件应为 {expected_basename}，实际为 {actual}"
            )

    def test_端口含必要字段(self, hierarchy):
        """每个端口应包含 name, direction, width。"""
        for path, entry in hierarchy.items():
            for port in entry["ports"]:
                for key in self.REQUIRED_PORT_KEYS:
                    assert key in port, (
                        f"{path} 端口 {port.get('name', '?')} 缺少键: {key}"
                    )

    def test_端口方向为合法值(self, hierarchy):
        """端口 direction 应为 input / output / inout / ref 之一。"""
        valid_dirs = {"input", "output", "inout", "ref"}
        for path, entry in hierarchy.items():
            for port in entry["ports"]:
                assert port["direction"] in valid_dirs, (
                    f"{path} 端口 {port['name']} 方向无效: {port['direction']}"
                )

    def test_顶层模块端口数量为9(self, hierarchy):
        """alu_system 应有 9 个端口。"""
        ports = hierarchy["alu_system"]["ports"]
        assert len(ports) == 9, f"alu_system 端口数应为 9，实际为 {len(ports)}"

    def test_顶层模块端口名称与方向(self, hierarchy):
        """验证 alu_system 的关键端口名称和方向。"""
        ports = {p["name"]: p for p in hierarchy["alu_system"]["ports"]}

        # 输入端口
        assert ports["clk"]["direction"] == "input"
        assert ports["clk"]["width"] == 1
        assert ports["rst_n"]["direction"] == "input"
        assert ports["rst_n"]["width"] == 1
        assert ports["operand_a"]["direction"] == "input"
        assert ports["operand_a"]["width"] == 8
        assert ports["operand_b"]["direction"] == "input"
        assert ports["operand_b"]["width"] == 8
        assert ports["opcode"]["direction"] == "input"
        assert ports["opcode"]["width"] == 3
        assert ports["start"]["direction"] == "input"
        assert ports["start"]["width"] == 1

        # 输出端口
        assert ports["result"]["direction"] == "output"
        assert ports["result"]["width"] == 8
        assert ports["carry"]["direction"] == "output"
        assert ports["carry"]["width"] == 1
        assert ports["done"]["direction"] == "output"
        assert ports["done"]["width"] == 1

    def test_alu_core端口数量为5(self, hierarchy):
        """alu_core 应有 5 个端口。"""
        ports = hierarchy["alu_system.u_core"]["ports"]
        assert len(ports) == 5, f"alu_core 端口数应为 5，实际为 {len(ports)}"

    def test_adder_8bit端口数量为5(self, hierarchy):
        """adder_8bit 应有 5 个端口。"""
        ports = hierarchy["alu_system.u_core.u_adder"]["ports"]
        assert len(ports) == 5, f"adder_8bit 端口数应为 5，实际为 {len(ports)}"

    def test_adder_8bit端口名称与方向(self, hierarchy):
        """验证 adder_8bit 的端口。"""
        ports = {p["name"]: p for p in hierarchy["alu_system.u_core.u_adder"]["ports"]}
        assert ports["a"]["direction"] == "input"
        assert ports["a"]["width"] == 8
        assert ports["b"]["direction"] == "input"
        assert ports["b"]["width"] == 8
        assert ports["cin"]["direction"] == "input"
        assert ports["cin"]["width"] == 1
        assert ports["sum"]["direction"] == "output"
        assert ports["sum"]["width"] == 8
        assert ports["cout"]["direction"] == "output"
        assert ports["cout"]["width"] == 1

    def test_result_stage端口名称与方向(self, hierarchy):
        """验证 result_stage 的端口。"""
        ports = {p["name"]: p for p in hierarchy["alu_system.u_result"]["ports"]}
        assert ports["clk"]["direction"] == "input"
        assert ports["rst_n"]["direction"] == "input"
        assert ports["en"]["direction"] == "input"
        assert ports["data_in"]["direction"] == "input"
        assert ports["data_in"]["width"] == 8
        assert ports["carry_in"]["direction"] == "input"
        assert ports["data_out"]["direction"] == "output"
        assert ports["data_out"]["width"] == 8
        assert ports["carry_out"]["direction"] == "output"

    def test_空输入返回空字典(self):
        """传入空列表应返回空字典。"""
        result = extract_hierarchy([])
        assert result == {}
