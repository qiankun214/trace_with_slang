"""conftest.py — 流程① filelist 解析 测试共享 fixtures

提供文件构造 factory fixture 与 loguru 日志捕获 fixture。
注意:本文件禁止 import filelist —— 实现尚不存在(src/ 待建),
顶部 import 会让整个收集阶段失败,连 fixture 都无法加载。
"""

from pathlib import Path

import pytest
from loguru import logger


@pytest.fixture
def make_file(tmp_path):
    """按相对路径在 tmp_path 下创建文件(自动建父目录),返回 Path。

    用法:make_file("sub/a.sv", "# 内容")
    """
    def _make(rel: str, content: str = "") -> Path:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p
    return _make


@pytest.fixture
def make_filelist(make_file):
    """按行内容创建 filelist,自动以换行拼接,返回 Path。

    用法:make_filelist("top.f", "-f sub.f", "a.sv")
    """
    def _make(rel: str, *lines: str) -> Path:
        return make_file(rel, "\n".join(lines) + "\n")
    return _make


class _RecordSink:
    """loguru 对象型 sink:write() 收到带 .record 的 Message,逐条收集。"""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def write(self, message) -> None:  # noqa: N802 — loguru 回调接口名
        self.records.append(message.record)


@pytest.fixture
def log_records():
    """捕获 loguru 日志记录列表(list[dict],含 "message" 与 "level".name)。

    loguru 默认不接入 pytest caplog,必须自建 sink;
    logger.remove() 清默认 stderr sink 与任何残留,finally 中清理防跨测试污染。
    sink 挂载属调用方职责(DS §5:流程内不初始化 sink)。
    """
    sink = _RecordSink()
    logger.remove()
    logger.add(sink, level="DEBUG")  # DEBUG 保证 ERROR/WARNING 全捕获
    try:
        yield sink.records
    finally:
        logger.remove()
