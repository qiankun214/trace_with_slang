"""test_cli.py — CLI 层(架构外调用方)行为单元测试。

直接调用 cli.main(argv)(进程内,与 tests/test_filelist.py 的 SystemExit
断言同法),经 capsys 断言 stdout 结果、stderr 日志与退出码契约
(0 成功 / 1 已知用户错误 / 2 用法错误)。
素材:test/with_instance/filelist.f(ALU 三层)与 test/flow3/mini.sv;
查询断言期望值由真库实测而来(load/driver 见 flow4 语义)。
"""

import json
from dataclasses import fields
from pathlib import Path

import pytest

from cli import main
from datatypes import BlockInfo, SignalInfo

_TEST_ROOT = Path(__file__).resolve().parent.parent / "test"
_ALU_FILELIST = str(_TEST_ROOT / "with_instance" / "filelist.f")
_ALU_VAR = "alu_system.u_core.add_sum"
_MINI_SV = str(_TEST_ROOT / "flow3" / "mini.sv")
_MINI_VAR = "mini.a"


@pytest.fixture
def alu_db(tmp_path) -> str:
    """用 ALU 仓库素材经 cli build 建库,返回 db 绝对路径(查询用例共用)。"""
    db = str(tmp_path / "alu.sqlite")
    main(["build", _ALU_FILELIST, "-o", db])
    return db


@pytest.fixture
def mini_db(tmp_path) -> str:
    """引用 test/flow3/mini.sv 建库(空匹配结果场景,mini.a 只读不被驱动)。"""
    filelist = tmp_path / "mini.f"
    filelist.write_text(_MINI_SV + "\n", encoding="utf-8")
    db = str(tmp_path / "mini.sqlite")
    main(["build", str(filelist), "-o", db])
    return db


class TestBuild:
    """build 子命令:落库位置、告警与退出码。"""

    def test_默认库路径同目录同stem(self, make_file, make_filelist, capsys):
        make_file("a.sv", "module a;\nendmodule\n")
        fl = make_filelist("top.f", "a.sv")
        main(["build", str(fl)])
        assert (fl.parent / "top.sqlite").is_file()
        assert "数据库已生成" in capsys.readouterr().err

    def test_指定o路径落库(self, make_file, make_filelist):
        make_file("a.sv", "module a;\nendmodule\n")
        fl = make_filelist("top.f", "a.sv")
        db_dir = fl.parent / "out"
        db_dir.mkdir()  # 库层契约:父目录须已存在,sqlite 不自动建目录
        db = db_dir / "custom.db"
        main(["build", str(fl), "-o", str(db)])
        assert db.is_file()

    def test_缺失sv文件告警仍建库(self, make_file, make_filelist, capsys):
        make_file("a.sv", "module a;\nendmodule\n")
        fl = make_filelist("top.f", "a.sv", "missing.sv")
        db = fl.parent / "top.sqlite"
        main(["build", str(fl)])
        assert db.is_file()
        assert "文件缺失/不存在" in capsys.readouterr().err

    def test_filelist不存在退出码1(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["build", str(tmp_path / "nope.f")])
        assert exc_info.value.code == 1
        assert "filelist 不存在" in capsys.readouterr().err

    def test_建库后info可查端到端(self, tmp_path, capsys):
        """build → info 串联闭环:同进程两次 main 调用。"""
        db = str(tmp_path / "alu.sqlite")
        main(["build", _ALU_FILELIST, "-o", db])
        capsys.readouterr()  # 丢弃 build 日志,只断言 info 的 stdout
        main(["info", db, _ALU_VAR])
        out = capsys.readouterr().out
        assert "变量信息" in out
        assert _ALU_VAR in out


class TestQuery:
    """四个查询子命令:文本与 --json 输出、空结果、错误路径。"""

    def test_info文本含中文标签与字段值(self, alu_db, capsys):
        main(["info", alu_db, _ALU_VAR])
        out = capsys.readouterr().out
        assert "变量信息" in out
        assert "完整路径  : " + _ALU_VAR in out
        assert "是端口  : 否" in out
        assert "定义文件  : " + str(_TEST_ROOT / "with_instance" / "alu_core.sv") in out

    def test_info_json字段名为dataclass字段名(self, alu_db, capsys):
        main(["info", alu_db, _ALU_VAR, "--json"])
        obj = json.loads(capsys.readouterr().out)
        assert set(obj.keys()) == {f.name for f in fields(SignalInfo)}
        assert obj["full_path"] == _ALU_VAR
        assert obj["is_port"] is False

    def test_blocks文本含块类型行号与源文本(self, alu_db, capsys):
        main(["blocks", alu_db, _ALU_VAR])
        out = capsys.readouterr().out
        assert "赋值语句块: 共 1 个" in out
        assert "类型: port_connection" in out
        assert "42-48" in out
        assert "adder_8bit u_adder (" in out  # source_text 原样打印

    def test_blocks_json对象数组含source_text(self, alu_db, capsys):
        main(["blocks", alu_db, _ALU_VAR, "--json"])
        obj = json.loads(capsys.readouterr().out)
        assert isinstance(obj, list) and len(obj) == 1
        assert set(obj[0].keys()) == {f.name for f in fields(BlockInfo)}
        assert "\n" in obj[0]["source_text"]

    def test_load文本每行一个路径(self, alu_db, capsys):
        main(["load", alu_db, _ALU_VAR])
        assert capsys.readouterr().out.splitlines() == ["alu_system.u_core.result"]

    def test_load_json字符串数组(self, alu_db, capsys):
        main(["load", alu_db, _ALU_VAR, "--json"])
        assert json.loads(capsys.readouterr().out) == ["alu_system.u_core.result"]

    def test_driver文本每行一个路径(self, alu_db, capsys):
        main(["driver", alu_db, _ALU_VAR])
        out = capsys.readouterr().out.splitlines()
        assert out == ["alu_system.u_core.u_adder.sum"]

    def test_driver_json字符串数组(self, alu_db, capsys):
        main(["driver", alu_db, _ALU_VAR, "--json"])
        assert json.loads(capsys.readouterr().out) == ["alu_system.u_core.u_adder.sum"]

    def test_无匹配块与边输出提示且退出码0(self, mini_db, capsys):
        """mini.a 是 input 端口,不被任何块驱动:块/边为空但非错误。"""
        main(["blocks", mini_db, _MINI_VAR])
        assert capsys.readouterr().out.strip() == "该变量没有匹配的赋值语句块"
        main(["driver", mini_db, _MINI_VAR])
        assert capsys.readouterr().out.strip() == "没有匹配的信号"

    def test_db不存在退出码1(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["info", str(tmp_path / "nope.sqlite"), _ALU_VAR])
        assert exc_info.value.code == 1
        assert "数据库文件不存在" in capsys.readouterr().err

    def test_变量不存在退出码1(self, alu_db, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["load", alu_db, "alu_system.nope.var"])
        assert exc_info.value.code == 1
        assert "变量不存在" in capsys.readouterr().err

    def test_日志走stderr不污染stdout(self, alu_db, capsys):
        """查询输出为纯结果:stdout 无 loguru 级别标记(JSON 可解析即证)。"""
        main(["load", alu_db, _ALU_VAR])
        out = capsys.readouterr().out
        assert "ERROR" not in out and "INFO" not in out and "WARNING" not in out
        assert out.splitlines() == ["alu_system.u_core.result"]


class TestArgparse:
    """参数用法:argparse 默认退出码 2,help 列出全部子命令。"""

    def test_无子命令退出码2(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 2

    def test_未知子命令退出码2(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["nope"])
        assert exc_info.value.code == 2

    def test_缺位置参数退出码2(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["info", str(tmp_path / "x.sqlite")])
        assert exc_info.value.code == 2

    def test_help列出全部子命令退出码0(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        for name in ("build", "info", "blocks", "load", "driver"):
            assert name in out
