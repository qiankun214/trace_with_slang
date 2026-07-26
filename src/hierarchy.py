#!/usr/bin/env python3
"""
hierarchy.py - 使用 pyslang 提取 SystemVerilog 实例化层次并打印

功能：
  1. 输入一个 filelist 的路径（.f 文件）
  2. 提取所有模块的实例化层次关系
  3. 输出为 JSON 格式的字典，key 为层次路径，value 包含模块名、文件路径、AST、端口列表

层次路径格式：
  <top的module名>.<模块的实例化名>.<模块的实例化名>
  除了 top 是 module 名，其他层次都是实例化名（如 alu_system.u_core.u_adder）

用法：
  python hierarchy.py [filelist_path]

测试：
  python hierarchy.py ../test/with_instance/filelist.f
"""

import sys
import os
import json
from pyslang import ast, syntax


# 方向：ArgumentDirection 枚举 → 字符串
DIRECTION_MAP = {
    ast.ArgumentDirection.In:    'input',
    ast.ArgumentDirection.Out:   'output',
    ast.ArgumentDirection.InOut: 'inout',
    ast.ArgumentDirection.Ref:   'ref',
}


# ==============================================================================
# 第一层：公开 API
# ==============================================================================

def parse_filelist(filelist_path):
    """
    解析 filelist 文件，返回 SV 文件的绝对路径列表。

    支持以 # 开头的注释行和空行。相对路径会基于 filelist 所在目录解析为绝对路径。

    Args:
        filelist_path: filelist 文件路径

    Returns:
        list[str]: SV 文件的绝对路径列表
    """
    if not os.path.exists(filelist_path):
        print(f"错误: filelist 文件不存在 - {filelist_path}", file=sys.stderr)
        sys.exit(1)

    base_dir = os.path.dirname(os.path.abspath(filelist_path))
    sv_files = []

    with open(filelist_path, 'r') as f:
        for line in f:
            stripped = line.strip()
            # 跳过空行和以 # 开头的注释行
            if not stripped or stripped.startswith('#'):
                continue
            abs_path = os.path.abspath(os.path.join(base_dir, stripped))
            if os.path.exists(abs_path):
                sv_files.append(abs_path)
            else:
                print(f"警告: 文件不存在，已跳过 - {abs_path}", file=sys.stderr)

    return sv_files


def extract_hierarchy(sv_files):
    """
    提取所有 SV 文件的实例化层次。

    串联编译、遍历收集、组装结果三个步骤，返回完整的层次字典。

    Args:
        sv_files: SV 文件绝对路径列表

    Returns:
        dict[str, dict]: key 为层次路径，value 为 {module, file, ast, ports}
    """
    if not sv_files:
        return {}

    # 步骤 1: 编译所有 SV 文件
    comp, root = _build_compilation(sv_files)

    # 步骤 2: 遍历 AST 收集所有实例节点
    instances = _collect_all_instances(root)

    # 步骤 3: 为每个实例构建输出条目，组装 dict
    sm = comp.sourceManager
    result = _build_hierarchy_result(instances, sm)

    return result


# ==============================================================================
# 第二层：extract_hierarchy 内部子函数（步骤 1/2/3）
# ==============================================================================

def _build_compilation(sv_files):
    """
    步骤 1：创建 Compilation，逐一添加 SyntaxTree，elaborate。

    Args:
        sv_files: SV 文件绝对路径列表

    Returns:
        tuple: (comp, root)
    """
    comp = ast.Compilation()

    for f in sv_files:
        tree = syntax.SyntaxTree.fromFile(f)
        comp.addSyntaxTree(tree)

    # 报告编译诊断
    diagnostics = comp.getAllDiagnostics()
    if diagnostics:
        warning_count = sum(1 for d in diagnostics if not d.isError())
        error_count = sum(1 for d in diagnostics if d.isError())
        if warning_count or error_count:
            parts = []
            if error_count:
                parts.append(f"{error_count} 条错误")
            if warning_count:
                parts.append(f"{warning_count} 条警告")
            print(f"编译诊断: {', '.join(parts)}", file=sys.stderr)

    root = comp.getRoot()
    return comp, root


def _collect_all_instances(root):
    """
    步骤 2：遍历所有顶层实例，通过 visit() 递归收集所有 InstanceSymbol 节点。

    Args:
        root: RootSymbol

    Returns:
        list[InstanceSymbol]: 所有实例符号节点（DFS 前序）
    """
    all_instances = []

    def collect(sym):
        if sym.kind == ast.SymbolKind.Instance:
            all_instances.append(sym)

    for top_inst in root.topInstances:
        top_inst.visit(collect)

    return all_instances


def _build_hierarchy_result(instances, sm):
    """
    步骤 3：遍历实例列表，为每个构建输出条目，组装最终 dict。

    Args:
        instances: InstanceSymbol 列表
        sm: SourceManager

    Returns:
        dict[str, dict]: key=层次路径, value={module, file, ast, ports}
    """
    result = {}
    for inst in instances:
        key, entry = _build_instance_entry(inst, sm)
        result[key] = entry
    return result


# ==============================================================================
# 第三层：叶子辅助函数
# ==============================================================================

def _build_instance_entry(inst, sm):
    """
    为单个 InstanceSymbol 构建输出条目。

    Args:
        inst: InstanceSymbol
        sm: SourceManager

    Returns:
        tuple[str, dict]: (层次路径, {module, file, ast, ports})
    """
    # 层次路径：inst.hierarchicalPath 格式符合要求
    #   顶层为 module 名，后续为实例名
    path = inst.hierarchicalPath

    # 模块类型名
    module_name = inst.definition.name

    # 文件路径：使用定义位置的绝对路径
    file_path = "<unknown>"
    if inst.definition.location:
        try:
            file_path = str(sm.getFullPath(inst.definition.location.buffer))
        except Exception:
            # 回退到相对路径
            fname = sm.getFileName(inst.definition.location)
            if fname:
                file_path = fname

    # AST：InstanceBodySymbol，供后续解析使用
    body = inst.body

    # 端口列表
    ports = _extract_ports(body)

    entry = {
        'module': module_name,
        'file': file_path,
        'ast': body,
        'ports': ports,
    }

    return path, entry


def _extract_ports(body):
    """
    从 InstanceBodySymbol.portList 提取端口信息。

    对每个端口提取名称、方向、位宽。处理 port.type 为 None 的边界情况。

    Args:
        body: InstanceBodySymbol

    Returns:
        list[dict]: 每个端口为 {name, direction, width}
    """
    ports = []
    for port in body.portList:
        # 方向
        direction = DIRECTION_MAP.get(
            port.direction,
            str(port.direction)
        )

        # 位宽：防御性检查
        width = 0
        if (hasattr(port, 'type') and port.type is not None
                and hasattr(port.type, 'bitWidth')):
            width = port.type.bitWidth

        ports.append({
            'name': port.name,
            'direction': direction,
            'width': width,
        })

    return ports


# ==============================================================================
# CLI
# ==============================================================================

def main():
    """CLI 入口：解析参数、调用提取、输出 JSON。"""
    if len(sys.argv) > 1:
        filelist_path = sys.argv[1]
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filelist_path = os.path.join(
            script_dir, '..', 'test', 'with_instance', 'filelist.f'
        )

    # 解析 filelist
    sv_files = parse_filelist(filelist_path)

    if not sv_files:
        print("{}")
        return

    # 提取层次
    result = extract_hierarchy(sv_files)

    # JSON 序列化：移除不可序列化的 "ast" 字段
    json_result = {}
    for key, entry in result.items():
        json_result[key] = {
            'module': entry['module'],
            'file': entry['file'],
            'ports': entry['ports'],
        }

    print(json.dumps(json_result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
