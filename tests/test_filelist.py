"""流程① filelist 解析 — 单元测试

行为契约:doc/flow1_design_spec.md(parse_filelist 及私有子函数)。
目标模块:src/filelist.py(契约先行,实现尚不存在,收集期报 import 错误属预期)。
测试数据全部由 tmp_path 动态构造;期望路径一律用 os.path.abspath 构造,不硬编码。
"""

import os

import pytest

from filelist import (
    _assert_filelist_exists,
    _classify_token,
    _dedup,
    _expand_env,
    _is_skip_line,
    _read_lines,
    _resolve_abs_path,
    _scan_library_dir,
    parse_filelist,
)


# ── 断言辅助 ────────────────────────────────────────────────────────

def _basenames(paths: list[str]) -> list[str]:
    """输出路径列表 → 仅文件名列表,便于断言顺序。"""
    return [os.path.basename(p) for p in paths]


def _warn_messages(records: list[dict]) -> list[str]:
    """取全部 WARNING 记录的消息。"""
    return [r["message"] for r in records if r["level"].name == "WARNING"]


def _error_messages(records: list[dict]) -> list[str]:
    """取全部 ERROR 记录的消息。"""
    return [r["message"] for r in records if r["level"].name == "ERROR"]


def _assert_warning(records: list[dict], *keywords: str) -> None:
    """断言存在一条 WARNING,消息含任一关键词(宽松匹配,给实现留自由度)。"""
    msgs = _warn_messages(records)
    assert msgs, "应产生 WARNING,实际无任何 WARNING"
    assert any(any(k in m for k in keywords) for m in msgs), (
        f"未匹配到关键词 {keywords},实际消息: {msgs}"
    )


def _build_chain(make_file, make_filelist, depth: int) -> str:
    """构造 depth 层 -f 嵌套链,每层含一个 .sv 文件,返回顶层 1.f 的绝对路径。

    第 i 层文件列表 {i}.f 包含 f{i}.sv 与 -f {i+1}.f(末层无 -f)。
    """
    top: str = ""
    for i in range(1, depth + 1):
        lines: list[str] = [f"f{i}.sv"]
        if i < depth:
            lines.append(f"-f {i + 1}.f")
        created = make_filelist(f"{i}.f", *lines)
        make_file(f"f{i}.sv")
        if i == 1:
            top = str(created)  # 顶层 1.f,后续循环不得覆盖
    return top


class TestBasic:
    """普通路径行的解析行为(DS §4.2/§4.3/§4.10 与 §5)"""

    def test_相对路径解析为绝对路径(self, make_file, make_filelist):
        """相对路径应基于 filelist 所在目录解析为绝对路径(DS §4.2)。"""
        make_file("a.sv")
        fl = make_filelist("list.f", "a.sv")
        result = parse_filelist(str(fl))
        assert result == [os.path.abspath(str(fl.parent / "a.sv"))]
        assert all(os.path.isabs(p) for p in result)

    def test_含父目录相对路径解析(self, make_file, make_filelist):
        """相对路径含 ../ 时应基于 filelist 目录解析并规范化(DS §6)。"""
        make_file("a.sv")
        fl = make_filelist("sub/list.f", "../a.sv")
        result = parse_filelist(str(fl))
        assert result == [os.path.abspath(str(fl.parent.parent / "a.sv"))]
        assert ".." not in result[0]

    def test_保序输出(self, make_file, make_filelist):
        """输出顺序应保持文件在 filelist 中的出现顺序(DS §4.10)。"""
        for name in ("b.sv", "a.sv", "c.sv"):
            make_file(name)
        fl = make_filelist("list.f", "b.sv", "a.sv", "c.sv")
        assert _basenames(parse_filelist(str(fl))) == ["b.sv", "a.sv", "c.sv"]

    def test_跳过空行与注释(self, make_file, make_filelist):
        """空行、# 与 // 注释行应被跳过(DS §4.3)。"""
        make_file("a.sv")
        fl = make_filelist("list.f", "", "   ", "# comment", "  # indent", "// c", "//c", "a.sv")
        assert parse_filelist(str(fl)) == [os.path.abspath(str(fl.parent / "a.sv"))]

    def test_纯注释空行返回空列表(self, make_filelist):
        """仅含注释/空行的 filelist 应返回空列表(DS §6)。"""
        fl = make_filelist("list.f", "# only comments", "", "// nothing else")
        assert parse_filelist(str(fl)) == []

    def test_filelist不存在则报错退出(self, tmp_path, log_records):
        """filelist 路径不存在应 logger.error 并以退出码 1 终止(DS §5)。"""
        bad = tmp_path / "nonexistent.f"
        with pytest.raises(SystemExit) as exc_info:
            parse_filelist(str(bad))
        assert exc_info.value.code == 1
        assert any("不存在" in m and str(bad) in m for m in _error_messages(log_records))

    def test_目录当filelist告警跳过(self, tmp_path, log_records):
        """已存在目录作为 filelist 路径:存在性校验通过,内部按非文件
        告警跳过返回空列表,不抛 IOError(规格未定义,仅验健壮性)。"""
        assert parse_filelist(str(tmp_path)) == []
        _assert_warning(log_records, "不存在", "跳过")

    def test_缺失sv文件告警并跳过其余(self, make_file, make_filelist, log_records):
        """单个 .sv 缺失应告警并跳过,其余行继续解析(DS §5)。"""
        make_file("a.sv")
        fl = make_filelist("list.f", "missing.sv", "a.sv")
        result = parse_filelist(str(fl))
        assert result == [os.path.abspath(str(fl.parent / "a.sv"))]
        assert any("missing.sv" in m for m in _warn_messages(log_records))

    def test_全部缺失返回空列表且逐条告警(self, make_filelist, log_records):
        """全部文件缺失时返回空列表,且逐条告警不吞并(DS §6/§5)。"""
        fl = make_filelist("list.f", "m1.sv", "m2.sv", "m3.sv")
        assert parse_filelist(str(fl)) == []
        assert len(_warn_messages(log_records)) == 3

    def test_多行重复路径去重(self, make_file, make_filelist):
        """同一文件多行出现应去重,仅保留首次出现(DS §4.10)。"""
        make_file("a.sv")
        fl = make_filelist("list.f", "a.sv", "a.sv", "a.sv")
        assert parse_filelist(str(fl)) == [os.path.abspath(str(fl.parent / "a.sv"))]

    def test_同路径不同写法去重(self, make_file, make_filelist):
        """a.sv 与 ./a.sv 归一化后是同一路径,应去重(DS §6)。"""
        make_file("a.sv")
        fl = make_filelist("list.f", "a.sv", "./a.sv")
        assert parse_filelist(str(fl)) == [os.path.abspath(str(fl.parent / "a.sv"))]

    def test_空文件返回空列表(self, make_file):
        """0 字节的 filelist 应返回空列表。"""
        fl = make_file("empty.f")
        assert parse_filelist(str(fl)) == []

    def test_utf8中文注释与文件名(self, make_file, make_filelist):
        """UTF-8 中文注释与中文文件名应正常解析(DS §2 按 UTF-8 读取)。"""
        make_file("模块.sv")
        fl = make_filelist("list.f", "# 中文注释", "模块.sv")
        assert parse_filelist(str(fl)) == [os.path.abspath(str(fl.parent / "模块.sv"))]


class TestFlagF:
    """-f 嵌套 filelist 展开(DS §4.5–§4.7)"""

    def test_嵌套展开且子filelist相对自身目录(self, make_file, make_filelist):
        """-f 子 filelist 内的相对路径应基于子 filelist 所在目录解析(DS §4.2)。"""
        make_file("sub/b.sv")
        make_filelist("sub/sub.f", "b.sv")
        top = make_filelist("top.f", "-f sub/sub.f")
        result = parse_filelist(str(top))
        assert result == [os.path.abspath(str(top.parent / "sub" / "b.sv"))]

    def test_参数跨行(self, make_file, make_filelist):
        """-f 参数可位于下一行(DS §4.5)。"""
        make_file("sub/b.sv")
        make_filelist("sub/sub.f", "b.sv")
        top = make_filelist("top.f", "-f", "sub/sub.f")
        assert parse_filelist(str(top)) == [os.path.abspath(str(top.parent / "sub" / "b.sv"))]

    def test_相对f参数告警但仍解析(self, make_file, make_filelist, log_records):
        """相对 -f 参数应告警,但仍基于本目录解析并递归展开(DS §4.6)。"""
        make_file("sub/b.sv")
        make_filelist("sub/sub.f", "b.sv")
        top = make_filelist("top.f", "-f sub/sub.f")
        result = parse_filelist(str(top))
        assert result == [os.path.abspath(str(top.parent / "sub" / "b.sv"))]
        _assert_warning(log_records, "相对")

    def test_绝对f参数不告警(self, make_file, make_filelist, log_records):
        """绝对路径的 -f 参数不应触发"相对路径"告警。"""
        make_file("b.sv")
        sub = make_filelist("sub.f", "b.sv")
        top = make_filelist("top.f", f"-f {sub}")
        assert parse_filelist(str(top)) == [os.path.abspath(str(sub.parent / "b.sv"))]
        assert not any("相对" in m for m in _warn_messages(log_records))

    def test_循环引用告警并跳过(self, make_file, make_filelist, log_records):
        """a→b→a 循环引用应告警并跳过该引用,不死循环(DS §4.7)。"""
        make_file("a1.sv")
        make_filelist("a.f", "a1.sv", "-f b.f")
        make_filelist("b.f", "-f a.f")
        top = make_filelist("top.f", "-f a.f")
        result = parse_filelist(str(top))
        assert _basenames(result) == ["a1.sv"]
        _assert_warning(log_records, "循环", "已展开")

    def test_自引用告警并跳过(self, make_file, make_filelist, log_records):
        """filelist 引用自身应告警并跳过,不死循环(DS §4.7)。"""
        make_file("a1.sv")
        a = make_filelist("a.f", "a1.sv", "-f a.f")
        assert parse_filelist(str(a)) == [os.path.abspath(str(a.parent / "a1.sv"))]
        _assert_warning(log_records, "循环", "已展开")

    def test_菱形引用只展开一次(self, make_file, make_filelist, log_records):
        """两个父 filelist 共享同一子 filelist 时,内容只展开一次,第二次引用告警。

        测的是 seen 集合跨递归共享,与"循环 a→b→a"是不同机制。
        """
        for name in ("a.sv", "c1.sv", "z.sv"):
            make_file(name)
        make_filelist("c.f", "c1.sv")
        make_filelist("a.f", "-f c.f")
        make_filelist("b.f", "-f c.f")
        top = make_filelist("top.f", "a.sv", "-f a.f", "-f b.f", "z.sv")
        assert _basenames(parse_filelist(str(top))) == ["a.sv", "c1.sv", "z.sv"]
        _assert_warning(log_records, "已展开", "循环")

    def test_深度31层全部展开(self, make_file, make_filelist):
        """31 层嵌套链应全部展开(≤32 层限制)(DS §4.6)。"""
        top = _build_chain(make_file, make_filelist, 31)
        assert len(parse_filelist(top)) == 31

    def test_深度35层底层被跳过(self, make_file, make_filelist, log_records):
        """35 层嵌套链超过 32 层限制,最深层被跳过并告警(DS §4.6)。

        不断言精确数量:两种层数计数约定(root 算 0 或 1)下 f31 都在、f35 都不在。
        """
        top = _build_chain(make_file, make_filelist, 35)
        result = parse_filelist(top)
        assert any(os.path.basename(p) == "f31.sv" for p in result)
        assert not any(os.path.basename(p) == "f35.sv" for p in result)
        _assert_warning(log_records, "深度", "层数", "递归")

    def test_嵌套去重(self, make_file, make_filelist):
        """父与子 filelist 都含同一文件时只保留一次(DS §4.10)。"""
        make_file("x.sv")
        make_filelist("child.f", "x.sv")
        top = make_filelist("top.f", "x.sv", "-f child.f")
        assert parse_filelist(str(top)) == [os.path.abspath(str(top.parent / "x.sv"))]

    def test_交织顺序(self, make_file, make_filelist):
        """嵌套展开按流式顺序交织:子文件展开结果插入父文件的 -f 位置(DS §4.4)。"""
        for name in ("a1.sv", "a2.sv", "b1.sv", "b2.sv"):
            make_file(name)
        make_filelist("b.f", "b1.sv", "b2.sv")
        make_filelist("a.f", "a1.sv", "-f b.f", "a2.sv")
        top = make_filelist("top.f", "-f a.f")
        assert _basenames(parse_filelist(str(top))) == ["a1.sv", "b1.sv", "b2.sv", "a2.sv"]

    def test_行尾孤立f不崩溃(self, make_file, make_filelist):
        """行尾孤立 -f(无参数)不应抛异常,其余行照常解析(规格未定义,仅验健壮性)。"""
        make_file("a.sv")
        top = make_filelist("top.f", "a.sv", "-f")
        assert parse_filelist(str(top)) == [os.path.abspath(str(top.parent / "a.sv"))]

    def test_f指向不存在子filelist退出(self, make_filelist, log_records):
        """-f 指向不存在的子 filelist 按 error + exit(1) 处理。

        契约解释:递归展开时进入 _assert_filelist_exists(DS §5 表未单列此项)。
        """
        top = make_filelist("top.f", "-f sub/nonexistent.f")
        with pytest.raises(SystemExit) as exc_info:
            parse_filelist(str(top))
        assert exc_info.value.code == 1
        assert _error_messages(log_records)


class TestFlagV:
    """-v 库文件(DS §2/§4.5/§5)"""

    def test_基本解析(self, make_file, make_filelist):
        """-v 引入的库文件与普通行混排,保持出现顺序。"""
        make_file("a.sv")
        make_file("lib/lib_a.sv")
        top = make_filelist("top.f", "a.sv", "-v lib/lib_a.sv")
        result = parse_filelist(str(top))
        assert _basenames(result) == ["a.sv", "lib_a.sv"]
        assert all(os.path.isabs(p) for p in result)

    def test_缺失v文件告警(self, make_file, make_filelist, log_records):
        """-v 文件缺失应告警跳过,其余行照常(DS §5)。"""
        make_file("a.sv")
        top = make_filelist("top.f", "-v missing_lib.sv", "a.sv")
        assert _basenames(parse_filelist(str(top))) == ["a.sv"]
        _assert_warning(log_records, "不存在", "缺失")

    def test_参数跨行(self, make_file, make_filelist):
        """-v 参数可位于下一行(DS §4.5)。"""
        make_file("lib/lib_a.sv")
        top = make_filelist("top.f", "-v", "lib/lib_a.sv")
        assert parse_filelist(str(top)) == [os.path.abspath(str(top.parent / "lib" / "lib_a.sv"))]

    def test_普通行与v重复去重(self, make_file, make_filelist):
        """同一文件经普通行与 -v 重复出现时只保留一次(DS §6)。"""
        make_file("a.sv")
        top = make_filelist("top.f", "a.sv", "-v a.sv")
        assert parse_filelist(str(top)) == [os.path.abspath(str(top.parent / "a.sv"))]

    def test_行尾孤立v不崩溃(self, make_file, make_filelist, log_records):
        """行尾孤立 -v(无参数)不应抛异常,其余行照常解析(规格未定义,仅验健壮性)。"""
        make_file("a.sv")
        top = make_filelist("top.f", "a.sv", "-v")
        assert parse_filelist(str(top)) == [os.path.abspath(str(top.parent / "a.sv"))]
        assert any("-v" in m for m in _warn_messages(log_records))


class TestFlagY:
    """-y 库目录扫描(DS §4.9/§6)"""

    def test_扫描sv与v按文件名排序(self, make_file, make_filelist):
        """-y 目录下 .sv/.v 文件按文件名排序加入(DS §4.9)。"""
        for name in ("z.sv", "m.sv", "a.v"):
            make_file(f"lib/{name}")
        top = make_filelist("top.f", "-y lib")
        assert _basenames(parse_filelist(str(top))) == ["a.v", "m.sv", "z.sv"]

    def test_非递归忽略子目录(self, make_file, make_filelist):
        """-y 只扫描直接文件,不递归子目录(DS §4.9)。"""
        make_file("lib/sub/x.sv")
        make_file("lib/b.sv")
        top = make_filelist("top.f", "-y lib")
        assert _basenames(parse_filelist(str(top))) == ["b.sv"]

    def test_忽略非sv文件(self, make_file, make_filelist):
        """-y 忽略非 .sv/.v 文件(DS §4.9)。"""
        make_file("lib/note.txt")
        make_file("lib/noext")
        make_file("lib/c.sv")
        top = make_filelist("top.f", "-y lib")
        assert _basenames(parse_filelist(str(top))) == ["c.sv"]

    def test_空目录无输出(self, tmp_path, make_filelist):
        """-y 指向存在的空目录时不产生任何文件(DS §6)。"""
        (tmp_path / "empty_lib").mkdir()
        top = make_filelist("top.f", "-y empty_lib")
        assert parse_filelist(str(top)) == []

    def test_目录不存在告警跳过(self, make_file, make_filelist, log_records):
        """-y 目录不存在应告警跳过,其余行照常(DS §5)。"""
        make_file("a.sv")
        top = make_filelist("top.f", "a.sv", "-y nodir")
        assert _basenames(parse_filelist(str(top))) == ["a.sv"]
        _assert_warning(log_records, "不存在")

    def test_与普通行混用顺序(self, make_file, make_filelist):
        """-y 库文件按流式位置插入普通行之间(DS §4.4)。"""
        for name in ("a.sv", "b.sv"):
            make_file(name)
        make_file("lib/m.sv")
        top = make_filelist("top.f", "a.sv", "-y lib", "b.sv")
        assert _basenames(parse_filelist(str(top))) == ["a.sv", "m.sv", "b.sv"]

    def test_行尾孤立y不崩溃(self, make_file, make_filelist, log_records):
        """行尾孤立 -y(无参数)不应抛异常,其余行照常解析(规格未定义,仅验健壮性)。"""
        make_file("a.sv")
        top = make_filelist("top.f", "a.sv", "-y")
        assert parse_filelist(str(top)) == [os.path.abspath(str(top.parent / "a.sv"))]
        assert any("-y" in m for m in _warn_messages(log_records))


class TestEnvVar:
    """路径中环境变量展开(DS §4.2/§6);专属变量名,不碰 HOME"""

    def test_美元变量展开(self, tmp_path, monkeypatch, make_file, make_filelist):
        """$VAR 形式的环境变量应在解析前展开。"""
        monkeypatch.setenv("FL1", str(tmp_path))
        make_file("a.sv")
        top = make_filelist("top.f", "$FL1/a.sv")
        assert parse_filelist(str(top)) == [os.path.abspath(str(tmp_path / "a.sv"))]

    def test_花括号变量展开(self, tmp_path, monkeypatch, make_file, make_filelist):
        """${VAR} 形式的环境变量应展开(DS §6)。"""
        monkeypatch.setenv("FL1", str(tmp_path))
        make_file("a.sv")
        top = make_filelist("top.f", "${FL1}/a.sv")
        assert parse_filelist(str(top)) == [os.path.abspath(str(tmp_path / "a.sv"))]

    def test_未定义变量展开为空后按缺失处理(self, make_filelist, log_records):
        """未定义环境变量展开为空串,路径不存在 → 告警跳过(DS §5)。"""
        top = make_filelist("top.f", "$FL_NOT_SET/a.sv")
        assert parse_filelist(str(top)) == []
        _assert_warning(log_records, "不存在")

    def test_裸未定义变量不泄漏基准目录(self, make_filelist, log_records):
        """裸未定义变量行不得把 filelist 所在目录本身当路径加入(DS §5)。

        按实际语义变量保持原样 → 路径 base_dir/$FL_NOT_SET 不存在 → 跳过;
        若实现改为"展开为空串",不判空时 join(base_dir, "") 会命中 base_dir
        本身(存在!会被静默加入)——两种实现下本用例都守卫此行为。
        """
        top = make_filelist("top.f", "$FL_NOT_SET")
        assert parse_filelist(str(top)) == []
        _assert_warning(log_records, "不存在", "为空")

    def test_变量用于f参数(self, tmp_path, monkeypatch, make_file, make_filelist):
        """环境变量可用于 -f 参数。"""
        monkeypatch.setenv("FL_SUB", str(tmp_path / "sub"))
        make_file("sub/b.sv")
        make_filelist("sub/sub.f", "b.sv")
        top = make_filelist("top.f", "-f $FL_SUB/sub.f")
        assert parse_filelist(str(top)) == [os.path.abspath(str(tmp_path / "sub" / "b.sv"))]

    def test_变量用于v参数(self, tmp_path, monkeypatch, make_file, make_filelist):
        """环境变量可用于 -v 参数。"""
        monkeypatch.setenv("FL_LIB", str(tmp_path / "lib"))
        make_file("lib/lib_a.sv")
        top = make_filelist("top.f", "-v $FL_LIB/lib_a.sv")
        assert parse_filelist(str(top)) == [os.path.abspath(str(tmp_path / "lib" / "lib_a.sv"))]

    def test_变量用于y参数(self, tmp_path, monkeypatch, make_file, make_filelist):
        """环境变量可用于 -y 参数。"""
        monkeypatch.setenv("FL_DIR", str(tmp_path / "lib"))
        make_file("lib/m.sv")
        top = make_filelist("top.f", "-y $FL_DIR")
        assert parse_filelist(str(top)) == [os.path.abspath(str(tmp_path / "lib" / "m.sv"))]

    def test_f参数变量展开为绝对路径不告警(
        self, tmp_path, monkeypatch, make_file, make_filelist, log_records
    ):
        """env 展开先于相对路径判定:-f 参数展开为绝对路径后不应触发"相对"告警(DS §4.2)。"""
        monkeypatch.setenv("FL_ABS", str(tmp_path / "sub"))
        make_file("sub/b.sv")
        make_filelist("sub/sub.f", "b.sv")
        top = make_filelist("top.f", "-f $FL_ABS/sub.f")
        parse_filelist(str(top))
        assert not any("相对" in m for m in _warn_messages(log_records))


class TestUnknownOption:
    """未知选项处理(DS §4.8)"""

    def test_plusarg自包含跳过(self, make_file, make_filelist, log_records):
        """+ 开头 plusarg 自包含跳过,不影响后续行(DS §4.8)。"""
        make_file("a.sv")
        top = make_filelist("top.f", "+incdir+/rtl", "a.sv")
        assert parse_filelist(str(top)) == [os.path.abspath(str(top.parent / "a.sv"))]
        _assert_warning(log_records, "+incdir", "选项", "未知")

    def test_plusarg不吞下个token(self, make_file, make_filelist):
        """plusarg 只跳自身,不吞下一个 token(与未知 - 选项吞参数相对照)。"""
        make_file("top.sv")
        top = make_filelist("top.f", "+incdir+rtl", "top.sv")
        assert parse_filelist(str(top)) == [os.path.abspath(str(top.parent / "top.sv"))]

    def test_未知减号选项跳过自身与参数(self, make_filelist, log_records):
        """未知 - 选项跳过自身及其后一个参数,参数不报"文件缺失"(DS §4.8)。"""
        top = make_filelist("top.f", "-xyz_unknown foo.sv")
        assert parse_filelist(str(top)) == []
        _assert_warning(log_records, "未知", "选项", "-xyz_unknown")
        assert not any("foo.sv" in m for m in _warn_messages(log_records))

    def test_未知选项跨行吞参数(self, make_filelist, log_records):
        """未知 - 选项按 token 流式处理,跨行吞掉下一行参数。

        契约解释:DS §4.8 只写"跳过其后一个参数",跨行语义未明说,
        §4.5 的跨行规则只写给 -f/-v/-y;本用例按 token 流模型推论。
        """
        make_filelist("top.sv")
        top = make_filelist("top.f", "-xyz", "top.sv")
        assert parse_filelist(str(top)) == []
        assert not any("top.sv" in m for m in _warn_messages(log_records))


class TestPrivateHelpers:
    """私有子函数的纯函数单元测试(DS §3)"""

    @pytest.mark.parametrize(
        "line",
        ["", "   ", "# c", "  # c", "// c", "  // c", "#"],
        ids=["空行", "空白行", "井号注释", "缩进井号注释", "双斜杠注释", "缩进双斜杠注释", "裸井号"],
    )
    def test_is_skip_line_跳过行(self, line: str):
        """空行与 # / // 注释行应判定为跳过(DS §4.3)。"""
        assert _is_skip_line(line) is True

    @pytest.mark.parametrize(
        "line",
        ["a.sv", "  a.sv  ", "-f x.f"],
        ids=["普通路径", "带空白路径", "选项行"],
    )
    def test_is_skip_line_有效行(self, line: str):
        """非注释有效行不应跳过。"""
        assert _is_skip_line(line) is False

    @pytest.mark.parametrize(
        ("token", "expected"),
        [
            ("a.sv", "path"),
            ("rtl/a.sv", "path"),
            ("/abs/a.sv", "path"),
            ("-f", "flag_f"),
            ("-v", "flag_v"),
            ("-y", "flag_y"),
            ("-F", "other_option"),
            ("--x", "other_option"),
            ("+incdir+rtl", "other_option"),
        ],
        ids=["相对路径", "带目录路径", "绝对路径", "-f", "-v", "-y", "-F大写", "长选项", "plusarg"],
    )
    def test_classify_token(self, token: str, expected: str):
        """token 应分类为 path / flag_f / flag_v / flag_y / other_option(DS §3)。"""
        assert _classify_token(token) == expected

    @pytest.mark.parametrize(
        ("entry", "expected"),
        [
            ("$TEST_VAR/a", "x/a"),
            ("${TEST_VAR}/a", "x/a"),
            ("a_$TEST_VAR", "a_x"),
            ("$UNDEFINED_VAR_9", "$UNDEFINED_VAR_9"),
            ("$UNDEFINED_VAR_9/a", "$UNDEFINED_VAR_9/a"),
        ],
        ids=["美元形式", "花括号形式", "内嵌拼接", "未定义变量", "未定义变量带后缀"],
    )
    def test_expand_env(self, monkeypatch, entry: str, expected: str):
        """$VAR/${VAR} 展开、未定义变量保持原样、内嵌拼接(语义同 os.path.expandvars)。

        注:DS 写"未定义展开为空串",但 Python ≥3.12 的 os.path.expandvars
        对未定义变量保持原样(实测 3.14.4),规格内部矛盾,经确认按实际语义;
        端到端行为两种语义收敛(解析后均按缺失告警跳过)。
        """
        monkeypatch.setenv("TEST_VAR", "x")
        assert _expand_env(entry) == expected

    @pytest.mark.parametrize(
        ("base", "entry", "expected"),
        [
            ("/b", "a.sv", "/b/a.sv"),
            ("/b", "a/../b.sv", "/b/b.sv"),
            ("/b", "/abs/x.sv", "/abs/x.sv"),
        ],
        ids=["相对路径", "含父目录规范化", "绝对路径不变"],
    )
    def test_resolve_abs_path(self, base: str, entry: str, expected: str):
        """相对路径基于 base_dir 解析为规范化绝对路径;绝对路径原样保留(DS §4.2)。"""
        assert _resolve_abs_path(base, entry) == expected

    def test_resolve_abs_path_env展开(self, monkeypatch):
        """_resolve_abs_path 应先展开环境变量再解析(DS §4.2)。"""
        monkeypatch.setenv("FL_BASE", "/env_base")
        assert _resolve_abs_path("/b", "$FL_BASE/a.sv") == "/env_base/a.sv"

    @pytest.mark.parametrize(
        ("paths", "expected"),
        [
            (["a", "b", "a", "c", "b"], ["a", "b", "c"]),
            ([], []),
            (["a"], ["a"]),
        ],
        ids=["重复保序", "空列表", "单元素"],
    )
    def test_dedup(self, paths: list[str], expected: list[str]):
        """去重并保持首次出现顺序(DS §4.10)。"""
        assert _dedup(paths) == expected

    def test_scan_library_dir(self, tmp_path):
        """_scan_library_dir 只收 .sv/.v、非递归、按文件名排序(DS §4.9)。"""
        d = tmp_path / "lib"
        d.mkdir()
        (d / "z.sv").touch()
        (d / "m.sv").touch()
        (d / "a.v").touch()
        (d / "note.txt").touch()
        (d / "sub").mkdir()
        (d / "sub" / "x.sv").touch()
        assert _basenames(_scan_library_dir(str(d))) == ["a.v", "m.sv", "z.sv"]

    def test_read_lines_utf8(self, make_file):
        """_read_lines 按 UTF-8 逐行读取,内容原样保留(DS §2)。

        不钉死是否剥离行尾换行符(两种 split 风格都容忍),只验内容。
        """
        fl = make_file("list.f", "# 中文注释\n模块.sv\n")
        lines = [ln.rstrip("\n") for ln in _read_lines(str(fl))]
        assert "# 中文注释" in lines
        assert "模块.sv" in lines

    def test_assert_filelist_exists报错退出(self, tmp_path, log_records):
        """_assert_filelist_exists 对不存在路径应 logger.error + exit(1)(DS §5)。"""
        with pytest.raises(SystemExit) as exc_info:
            _assert_filelist_exists(str(tmp_path / "nonexistent.f"))
        assert exc_info.value.code == 1
        assert _error_messages(log_records)
