"""流程① filelist 解析。

读取 filelist 文件,解析出 .sv 文件绝对路径列表(含 -v/-y 引入的库文件),
作为流程②(pyslang 解析)的输入。行为契约见 doc/flow1_design_spec.md。
"""

import os
import sys
from dataclasses import dataclass

from loguru import logger

#: -f 嵌套 filelist 的最大递归层数(根为第 1 层),超出则告警并跳过该引用
_MAX_FILELIST_DEPTH = 32


@dataclass
class _ExpansionContext:
    """-f 递归展开上下文:已展开 filelist 集合与当前递归层数(根为 1)。

    整个展开树共享同一个 seen 集合(循环引用检测/跨分支去重);
    进入子 filelist 时经 child() 派生新上下文(层数 +1),seen 保持共享。
    """

    seen: set[str]
    depth: int = 1

    def child(self) -> "_ExpansionContext":
        """派生进入子 filelist 的上下文:递归层数 +1,seen 集合共享。"""
        return _ExpansionContext(self.seen, self.depth + 1)


@dataclass
class _TokenCursor:
    """token 流游标:token 序列与当前处理位置,供状态机按序消费。

    take_arg() 取当前选项后的参数 token 并前移 2 位;缺参时告警返回 None,
    位置不动(调用方自行前移跳过该选项 token)。
    """

    tokens: list[str]
    pos: int = 0

    def at_end(self) -> bool:
        """是否已消费完全部 token。"""
        return self.pos >= len(self.tokens)

    def current(self) -> str:
        """当前待处理 token。"""
        return self.tokens[self.pos]

    def advance(self, n: int = 1) -> None:
        """后移 n 个 token。"""
        self.pos += n

    def take_arg(self) -> str | None:
        """取当前选项后的参数 token 并前进;无参数可取时告警并返回 None。"""
        if self.pos + 1 >= len(self.tokens):
            logger.warning(f"选项缺少参数,跳过: {self.tokens[self.pos]}")
            return None
        self.pos += 2
        return self.tokens[self.pos - 1]


def parse_filelist(filelist_path: str) -> list[str]:
    """解析 filelist 得到 .sv 绝对路径列表(一级函数)。

    Args:
        filelist_path: filelist 文件路径;不存在时报错并以退出码 1 终止。

    Returns:
        .sv 文件绝对路径列表,按展开顺序合并并去重(保持首次出现顺序);
        包含普通行与 -v/-y 引入的库文件。
    """
    _assert_filelist_exists(filelist_path)
    return _dedup(_expand_filelist(filelist_path))


def _assert_filelist_exists(filelist_path: str) -> None:
    """校验 filelist 路径存在;不存在时 logger.error 报错并以退出码 1 终止。"""
    if not os.path.exists(filelist_path):
        logger.error(f"filelist 不存在: {filelist_path}")
        sys.exit(1)


def _read_lines(filelist_path: str) -> list[str]:
    """按 UTF-8 读取文件全部原始行(返回不含行尾换行符的列表)。"""
    with open(filelist_path, encoding="utf-8") as f:
        return f.read().splitlines()


def _is_skip_line(line: str) -> bool:
    """判断行是否应跳过:去除首尾空白后为空(空行)或以 # 或 // 开头(注释行)。"""
    stripped = line.strip()
    return not stripped or stripped.startswith("#") or stripped.startswith("//")


def _classify_token(token: str) -> str:
    """对 token 分类:path(普通路径)/ flag_f / flag_v / flag_y / other_option。"""
    if token == "-f":
        return "flag_f"
    if token == "-v":
        return "flag_v"
    if token == "-y":
        return "flag_y"
    if token.startswith("-") or token.startswith("+"):
        return "other_option"
    return "path"


def _expand_env(entry: str) -> str:
    """展开路径中的环境变量($VAR/${VAR}),未定义展开为空串(语义同 os.path.expandvars)。"""
    return os.path.expandvars(entry)


def _expand_filelist(filelist_path: str, seen: set[str] | None = None) -> list[str]:
    """递归展开单个 filelist(§2 流程主体)。

    Args:
        filelist_path: filelist 文件路径;规范化到绝对路径后作为展开基准与
            循环引用检测的 key。
        seen: 已展开 filelist 集合,用于循环引用检测;None 时自动创建。

    Returns:
        .sv 文件绝对路径列表,去重(保持首次出现顺序)。
    """
    if seen is None:
        seen = set()
    return _expand_filelist_inner(os.path.abspath(filelist_path), _ExpansionContext(seen))


def _expand_filelist_inner(filelist_path: str, ctx: _ExpansionContext) -> list[str]:
    """单个 filelist 的展开实现;ctx.depth 为当前递归层数(根为 1)。

    递归进入子 filelist 时经 ctx.child() 派生上下文(层数 +1,seen 共享)。
    """
    if filelist_path in ctx.seen:
        logger.warning(f"filelist 循环引用,跳过: {filelist_path}")
        return []
    if not os.path.isfile(filelist_path):
        logger.warning(f"filelist 不存在,跳过: {filelist_path}")
        return []
    ctx.seen.add(filelist_path)
    return _process_tokens(
        _collect_tokens(filelist_path),
        base_dir=os.path.dirname(filelist_path),
        ctx=ctx,
    )


def _collect_tokens(filelist_path: str) -> list[str]:
    """逐行读取 filelist,过滤空行/注释行后按空白拆分为 token 序列(保持行序)。"""
    tokens: list[str] = []
    for line in _read_lines(filelist_path):
        if not _is_skip_line(line):
            tokens.extend(line.split())
    return tokens


def _process_tokens(
    tokens: list[str], base_dir: str, ctx: _ExpansionContext
) -> list[str]:
    """按 token 流序处理单个 filelist 的全部 token(§2 状态机主体)。

    按 token 类别分发给对应的处理函数,汇总各自新增路径后去重返回;
    各处理函数通过共享的 _TokenCursor 顺序消费并推进 token 流。
    """
    cursor = _TokenCursor(tokens)
    result: list[str] = []
    while not cursor.at_end():
        kind = _classify_token(cursor.current())
        if kind == "flag_f":
            extra = _handle_flag_f(cursor, base_dir, ctx)
        elif kind == "flag_v":
            extra = _handle_flag_v(cursor, base_dir)
        elif kind == "flag_y":
            extra = _handle_flag_y(cursor, base_dir)
        elif kind == "other_option":
            extra = _handle_other_option(cursor)
        else:  # path
            extra = _handle_path(cursor, base_dir)
        result.extend(extra)
    return _dedup(result)


def _handle_flag_f(
    cursor: _TokenCursor, base_dir: str, ctx: _ExpansionContext
) -> list[str]:
    """处理 -f <子filelist>:展开环境变量、校验存在后递归展开子 filelist。"""
    arg = cursor.take_arg()
    if arg is None:
        cursor.advance(1)
        return []
    if not os.path.isabs(_expand_env(arg)):
        logger.warning(f"filelist 相对路径,基于当前目录解析: {arg}")
    child = _resolve_abs_path(base_dir, arg)
    _assert_filelist_exists(child)
    if ctx.depth + 1 > _MAX_FILELIST_DEPTH:
        logger.warning(f"filelist 递归层数超过 {_MAX_FILELIST_DEPTH},跳过: {child}")
        return []
    if child in ctx.seen:
        logger.warning(f"filelist 循环引用,跳过: {child}")
        return []
    return _expand_filelist_inner(child, ctx.child())


def _handle_flag_v(cursor: _TokenCursor, base_dir: str) -> list[str]:
    """处理 -v <库文件>:同普通路径,存在则加入,缺失告警跳过。"""
    arg = cursor.take_arg()
    if arg is None:
        cursor.advance(1)
        return []
    path = _resolve_abs_path(base_dir, arg)
    if os.path.isfile(path):
        return [path]
    logger.warning(f"文件缺失/不存在,跳过: {path}")
    return []


def _handle_flag_y(cursor: _TokenCursor, base_dir: str) -> list[str]:
    """处理 -y <库目录>:目录存在则扫描其下 .sv/.v 文件(非递归),缺失告警跳过。"""
    arg = cursor.take_arg()
    if arg is None:
        cursor.advance(1)
        return []
    dir_path = _resolve_abs_path(base_dir, arg)
    if os.path.isdir(dir_path):
        return _scan_library_dir(dir_path)
    logger.warning(f"库目录不存在,跳过: {dir_path}")
    return []


def _handle_other_option(cursor: _TokenCursor) -> list[str]:
    """处理未知选项:+ 开头(plusarg)自包含跳过;其他 - 选项连后一参数一并跳过。"""
    token = cursor.current()
    logger.warning(f"未知选项,跳过: {token}")
    cursor.advance(2 if token.startswith("-") else 1)
    return []


def _handle_path(cursor: _TokenCursor, base_dir: str) -> list[str]:
    """处理普通路径 token:展开环境变量后基于 base_dir 解析,存在则加入。"""
    path = _resolve_abs_path(base_dir, cursor.current())
    cursor.advance(1)
    if os.path.isfile(path):
        return [path]
    logger.warning(f"文件缺失/不存在,跳过: {path}")
    return []


def _resolve_abs_path(base_dir: str, entry: str) -> str:
    """展开环境变量后,将 entry 基于 base_dir 解析为规范化绝对路径。"""
    return os.path.abspath(os.path.join(base_dir, _expand_env(entry)))


def _scan_library_dir(dir_path: str) -> list[str]:
    """扫描目录下所有 .sv/.v 文件(非递归),按文件名排序返回绝对路径列表。"""
    names = sorted(
        name
        for name in os.listdir(dir_path)
        if (name.endswith(".sv") or name.endswith(".v"))
        and os.path.isfile(os.path.join(dir_path, name))
    )
    return [os.path.join(dir_path, name) for name in names]


def _dedup(paths: list[str]) -> list[str]:
    """去除重复路径,保持首次出现顺序。"""
    result: list[str] = []
    seen_paths: set[str] = set()
    for path in paths:
        if path not in seen_paths:
            seen_paths.add(path)
            result.append(path)
    return result
