"""命令行入口(架构外的调用方):将四大流程一级函数暴露为 CLI。

定位:doc/flow4_design_spec.md §9 将 CLI 划为调用方职责,本模块只串联
parse_filelist → extract_design → build_db 与四大查询函数,不触碰流程
内部契约。子命令:
    build <filelist> [-o DB]
    info|blocks|load|driver <db> <var> [--json]
输出通道:结果走 stdout、loguru 日志走 stderr;退出码:0 成功 / 1 已知
用户错误(filelist/db/变量不存在) / 2 用法错误;未预期异常直接爆出。
完整使用说明见 doc/readme.md。
"""

import argparse
import json
import os
import sys
from dataclasses import asdict, fields

from loguru import logger

from build_db import build_db
from datatypes import BlockInfo, SignalInfo
from extract import extract_design
from filelist import parse_filelist
from query import get_assignment_blocks, get_variable_info, trace_driver, trace_load

_SEP = "─" * 40

# SignalInfo 字段名 → 中文标签(仅文本输出;--json 用 dataclass 字段名)
_SIGNAL_LABELS: dict[str, str] = {
    "instance_path": "所在实例",
    "full_path": "完整路径",
    "name": "名称",
    "type_name": "类型",
    "bit_width": "位宽",
    "kind": "种类",
    "is_port": "是端口",
    "direction": "方向",
    "definition_file": "定义文件",
    "definition_line": "定义行",
}


def main(argv: list[str] | None = None) -> None:
    """CLI 入口:初始化 loguru sink,解析参数并分派(退出码约定见 doc/readme.md)。

    已知用户错误(db 文件/变量不存在)在此边界统一 logger.error + 退出码 1;
    filelist 缺失由 parse_filelist 内部 sys.exit(1) 结束(不变式一致);
    未知子命令/缺参由 argparse 以退出码 2 处理;未预期异常直接爆出 traceback。
    """
    _setup_logging()
    args = _build_parser().parse_args(argv)
    try:
        args.handler(args)
    except (FileNotFoundError, ValueError) as exc:
        logger.error(str(exc))
        sys.exit(1)


def _setup_logging() -> None:
    """loguru sink 归零后挂 stderr(INFO 起),保证结果(stdout)与日志分离。"""
    logger.remove()
    logger.add(sys.stderr, level="INFO")


def _build_parser() -> argparse.ArgumentParser:
    """构造主 parser:build + 四个查询子命令,各子命令绑定 handler。"""
    parser = argparse.ArgumentParser(
        description="trace_with_slang 命令行工具:"
        "build 解析 filelist 落库,info/blocks/load/driver 查询四大功能"
    )
    sub = parser.add_subparsers(required=True, metavar="子命令")

    p_build = sub.add_parser("build", help="解析 filelist 并生成 sqlite 库(流程①→②→③)")
    p_build.add_argument("filelist", metavar="FILELIST", help="filelist 文件路径")
    p_build.add_argument(
        "-o", "--output", dest="db", metavar="DB",
        help="输出 sqlite 库路径(缺省:filelist 同目录同名 + .sqlite)",
    )
    p_build.set_defaults(handler=_handle_build)

    _add_query_parser(sub, "info", _handle_info, "变量信息:类型/位宽/定义位置等")
    _add_query_parser(sub, "blocks", _handle_blocks, "赋值语句块:完整赋值该变量的语句块与源文本")
    _add_query_parser(sub, "load", _handle_load, "trace load:读取该变量的赋值块所驱动的信号")
    _add_query_parser(sub, "driver", _handle_driver, "trace driver:驱动该变量的赋值块内被读的信号")
    return parser


def _add_query_parser(
    sub: argparse._SubParsersAction,
    name: str,
    handler,
    help_text: str,
) -> None:
    """按统一模板构造查询子命令:位置参 db/var(镜像一级函数签名) + --json。"""
    p = sub.add_parser(name, help=help_text)
    p.add_argument("db", metavar="DB", help="sqlite 库文件路径(build 产出)")
    p.add_argument(
        "var", metavar="VAR_PATH",
        help="变量层次路径,如 alu_system.u_core.add_sum",
    )
    p.add_argument(
        "--json", action="store_true",
        help="以 JSON 输出(字段名为 dataclass 字段名)",
    )
    p.set_defaults(handler=handler)


def _handle_build(args: argparse.Namespace) -> None:
    """build 子命令:串联 parse_filelist → extract_design → build_db。"""
    db_path = args.db if args.db is not None else _default_db_path(args.filelist)
    sv_files = parse_filelist(args.filelist)  # filelist 缺失时内部 sys.exit(1)
    result = extract_design(sv_files)
    build_db(result, db_path)
    logger.info(f"数据库已生成: {db_path}")


def _default_db_path(filelist_path: str) -> str:
    """默认库路径:filelist 同目录、同文件名 stem + .sqlite。"""
    directory = os.path.dirname(os.path.abspath(filelist_path))
    stem = os.path.splitext(os.path.basename(filelist_path))[0]
    return os.path.join(directory, stem + ".sqlite")


def _handle_info(args: argparse.Namespace) -> None:
    """info 子命令:变量信息(文本或 JSON)。"""
    info = get_variable_info(args.db, args.var)
    if args.json:
        print(_dump_json(asdict(info)))
    else:
        print(_format_signal(info))


def _handle_blocks(args: argparse.Namespace) -> None:
    """blocks 子命令:赋值语句块列表(文本或 JSON)。"""
    blocks = get_assignment_blocks(args.db, args.var)
    if args.json:
        print(_dump_json([asdict(block) for block in blocks]))
    else:
        print(_format_blocks(blocks))


def _handle_load(args: argparse.Namespace) -> None:
    """load 子命令:trace_load 路径列表(文本或 JSON)。"""
    _print_paths(trace_load(args.db, args.var), args.json)


def _handle_driver(args: argparse.Namespace) -> None:
    """driver 子命令:trace_driver 路径列表(文本或 JSON)。"""
    _print_paths(trace_driver(args.db, args.var), args.json)


def _print_paths(paths: list[str], use_json: bool) -> None:
    """按 --json 与否打印路径列表(文本为每行一个,便于管道消费)。"""
    if use_json:
        print(_dump_json(paths))
    else:
        print(_format_paths(paths))


def _format_signal(info: SignalInfo) -> str:
    """SignalInfo → 中文标签键值对文本块(字段序即 dataclass 声明序)。"""
    lines = ["变量信息"]
    for field in fields(SignalInfo):
        value = getattr(info, field.name)
        if field.name == "is_port":
            value = "是" if value else "否"
        lines.append(f"  {_SIGNAL_LABELS[field.name]}  : {value}")
    return "\n".join(lines)


def _format_blocks(blocks: list[BlockInfo]) -> str:
    """BlockInfo 列表 → 分隔文本块;source_text 原样输出,不加缩进与行号。"""
    if not blocks:
        return "该变量没有匹配的赋值语句块"
    lines = [f"赋值语句块: 共 {len(blocks)} 个"]
    for i, block in enumerate(blocks, 1):
        lines.append(_SEP)
        lines.append(f"块 {i}/{len(blocks)}  类型: {block.block_type}")
        lines.append(f"  实例路径  : {block.instance_path}")
        lines.append(f"  源文件    : {block.source_file}")
        lines.append(f"  行号      : {block.start_line}-{block.end_line}")
        lines.append("  ── 源文本 ──")
        lines.append(block.source_text)
    lines.append(_SEP)
    return "\n".join(lines)


def _format_paths(paths: list[str]) -> str:
    """路径列表 → 每行一个;空列表输出提示行(非错误,退出码仍为 0)。"""
    return "\n".join(paths) if paths else "没有匹配的信号"


def _dump_json(obj) -> str:
    """对象 → 缩进 JSON(ensure_ascii=False 保中文可读)。"""
    return json.dumps(obj, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
