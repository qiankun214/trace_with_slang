"""
conftest.py — pytest 共享 fixtures

提供 session 级别的 fixture，避免每个测试重复编译 SV 文件。
extract_hierarchy 调用 pyslang 编译，耗时较长，因此使用 session 作用域。
"""

import os
import pytest

# conftest.py 位于 tests/ 目录，项目根目录在其父目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def test_fixture_dir():
    """test/with_instance/ 目录的绝对路径。"""
    return os.path.join(_PROJECT_ROOT, "test", "with_instance")


@pytest.fixture(scope="session")
def filelist_path(test_fixture_dir):
    """test/with_instance/filelist.f 的绝对路径。"""
    return os.path.join(test_fixture_dir, "filelist.f")


@pytest.fixture(scope="session")
def sv_files(filelist_path):
    """parse_filelist() 的结果 — SV 文件的绝对路径列表。"""
    from hierarchy import parse_filelist

    return parse_filelist(filelist_path)


@pytest.fixture(scope="session")
def hierarchy(sv_files):
    """extract_hierarchy() 的结果 — 完整的层次字典。"""
    from hierarchy import extract_hierarchy

    return extract_hierarchy(sv_files)
