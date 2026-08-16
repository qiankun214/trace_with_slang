#!/usr/bin/env python3
"""
hierarch_get.py - 按文件和变量名查询实例化层次路径

功能：
  1. 输入 filelist 和目标 SV 文件路径，找到该文件对应的模块在层次树中的
     所有实例化路径
  2. 输入 filelist、目标 SV 文件路径和变量名，返回该变量在所有实例化
     路径下的完整层次名称

路径格式：
  <top的module名>.<实例化名>.<实例化名>
  变量路径在末尾追加变量名：<top的module名>.<实例化名>.<变量名>

用法（程序化调用）：
  from hierarchy import parse_filelist, extract_hierarchy
  from hierarch_get import find_instance_paths_for_file, find_variable_paths

  h = extract_hierarchy(parse_filelist('filelist.f'))
  paths = find_instance_paths_for_file(h, 'adder_8bit.sv')
  var_paths = find_variable_paths(h, 'adder_8bit.sv', 'sum')

用法（CLI）：
  # 模式1：列出目标文件的所有实例化层次路径
  python hierarch_get.py ../test/with_instance/filelist.f ../test/with_instance/adder_8bit.sv

  # 模式2：列出目标变量在所有实例中的完整层次路径
  python hierarch_get.py ../test/with_instance/filelist.f ../test/with_instance/adder_8bit.sv sum
"""

import sys
import os
import json

from hierarchy import parse_filelist, extract_hierarchy


# ==============================================================================
# 第一层：公开 API
# ==============================================================================

def find_instance_paths_for_file(hierarchy, target_file):
    """
    在层次字典中查找目标 SV 文件对应模块的所有实例化路径。

    遍历 hierarchy dict，对每个 entry 的 file 字段与 target_file 做路径归一化
    比较，返回匹配的层次路径列表。

    Args:
        hierarchy:   extract_hierarchy() 返回的 dict[str, dict]，
                     key 为 hierarchicalPath，value 含 'file' 字段
        target_file: 目标 SV 源文件路径（相对或绝对）

    Returns:
        list[str]: 匹配的层次路径列表（如 ['alu_system.u_core.u_adder']）。
                   无匹配时返回空列表。
    """
    if not hierarchy:
        return []

    target_abs = _resolve_file_path(target_file)
    result = []

    for path, entry in hierarchy.items():
        entry_file = entry.get('file', '')
        if os.path.abspath(entry_file) == target_abs:
            result.append(path)

    return result


def find_variable_paths(hierarchy, target_file, var_name):
    """
    查找目标变量在所有实例化路径下的完整层次名称。

    先通过 find_instance_paths_for_file() 找到目标文件的所有实例路径，
    再对每条路径通过 AST body.find() 判断变量是否存在，若存在则拼接
    完整的层次变量路径。

    支持 struct 字段路径：var_name 可包含 '.' 分隔的字段路径
    （如 "cfg_reg.baud.div"），首段通过 body.find() 查找基变量，
    后续段通过 struct type scope 逐级查找字段。

    Args:
        hierarchy:   extract_hierarchy() 返回的 dict[str, dict]
        target_file: 目标 SV 源文件路径（相对或绝对）
        var_name:    要查找的变量名，可含 struct 字段路径（如 "cfg_reg.baud.div"）

    Returns:
        list[str]: 形如 ['alu_system.u_core.u_adder.sum'] 的变量层次路径列表。
                   无匹配时返回空列表。
    """
    inst_paths = find_instance_paths_for_file(hierarchy, target_file)
    if not inst_paths:
        return []

    # 拆分 var_name: 首段为基变量名，后续段为 struct 字段路径
    segments = var_name.split('.')
    base_name = segments[0]
    field_path = segments[1:]

    result = []
    for inst_path in inst_paths:
        entry = hierarchy.get(inst_path)
        if entry is None:
            continue

        body = entry.get('ast')
        if body is None:
            continue

        # 通过 AST 查找基变量
        symbol = body.find(base_name)
        if symbol is None:
            continue

        # 遍历 struct 字段路径
        found = True
        for field_name in field_path:
            struct_scope = symbol.type
            if hasattr(struct_scope, 'canonicalType') and struct_scope.canonicalType is not None:
                struct_scope = struct_scope.canonicalType
            if struct_scope is None or not hasattr(struct_scope, 'find'):
                found = False
                break
            symbol = struct_scope.find(field_name)
            if symbol is None:
                found = False
                break

        if found:
            var_path = f"{inst_path}.{var_name}"
            result.append(var_path)

    return result


# ==============================================================================
# 第二层：内部辅助
# ==============================================================================

def _resolve_file_path(file_path):
    """
    将用户输入的文件路径规整为绝对路径，用于与层次字典中的路径比较。

    与 parse_filelist() 保持一致的路径解析方式。

    Args:
        file_path: 文件路径（相对或绝对）

    Returns:
        str: 绝对路径
    """
    return os.path.abspath(file_path)


# ==============================================================================
# CLI
# ==============================================================================

def main():
    """CLI 入口：解析参数、构建层次、执行查询、输出 JSON。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if len(sys.argv) >= 3:
        filelist_path = sys.argv[1]
        target_file = sys.argv[2]
        var_name = sys.argv[3] if len(sys.argv) >= 4 else None
    else:
        # 默认使用测试数据
        filelist_path = os.path.join(
            script_dir, '..', 'test', 'with_instance', 'filelist.f'
        )
        target_file = os.path.join(
            script_dir, '..', 'test', 'with_instance', 'adder_8bit.sv'
        )
        var_name = None

    # 解析 filelist 并构建层次
    sv_files = parse_filelist(filelist_path)
    if not sv_files:
        print("[]")
        return

    hierarchy = extract_hierarchy(sv_files)
    if not hierarchy:
        print("[]")
        return

    # 执行查询
    if var_name:
        result = find_variable_paths(hierarchy, target_file, var_name)
    else:
        result = find_instance_paths_for_file(hierarchy, target_file)

    # JSON 输出
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
