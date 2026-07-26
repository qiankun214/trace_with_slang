#!/usr/bin/env python3
"""
scan_ports.py - 使用 pyslang AST 扫描 SystemVerilog 文件，打印 IO 端口信息

用法：
    python scan_ports.py [sv_file_path]

默认扫描当前目录下的 simple_alu.sv

使用 elaborated AST（Compilation + PortSymbol），而非 CST（SyntaxTree）。
所有信息均从语义解析后的符号节点直接提取：
  - 方向：ArgumentDirection 枚举
  - 类型：经过类型推导的完整类型名（如 logic[7:0]）
  - 位宽：位流宽度（bitWidth）
"""

import sys
import os
from pyslang import ast, syntax


# 方向：ArgumentDirection 枚举 → 字符串
DIRECTION_MAP = {
    ast.ArgumentDirection.In:    'input',
    ast.ArgumentDirection.Out:   'output',
    ast.ArgumentDirection.InOut: 'inout',
    ast.ArgumentDirection.Ref:   'ref',
}


def scan_ports_ast(filepath):
    """
    使用 elaborated AST 扫描 SV 文件，提取所有 IO 端口信息。

    流程：
      1. 用 SyntaxTree 解析源文件（CST）
      2. 创建 Compilation 并加入语法树进行 elaboration
      3. 从 Root → topInstances → body.portList 遍历端口符号
    """
    # 1. 解析为 CST
    tree = syntax.SyntaxTree.fromFile(filepath)

    # 2. Elaboration：编译为 AST
    comp = ast.Compilation()
    comp.addSyntaxTree(tree)

    # 检查编译诊断
    diagnostics = comp.getAllDiagnostics()
    if diagnostics:
        print(f"警告: 发现 {len(diagnostics)} 条编译诊断信息:")
        for d in diagnostics[:5]:  # 只打印前 5 条
            print(f"  - {d}")
        if len(diagnostics) > 5:
            print(f"  ... 共 {len(diagnostics)} 条")
        print()

    # 3. 获取根符号
    root = comp.getRoot()

    all_ports = []

    # 4. 遍历顶层实例（模块、接口等）
    for top_inst in root.topInstances:
        module_name = top_inst.name
        print(f"模块名称: {module_name}")

        body = top_inst.body
        ports_info = []
        print(body)

        for port in body.portList:
            # ── 方向：从 ArgumentDirection 枚举提取 ──
            direction = DIRECTION_MAP.get(
                port.direction,
                str(port.direction)  # 回退
            )

            # ── 类型：已推导的完整类型字符串 ──
            port_type = str(port.type)
            print(port.type.bitWidth)

            # ── 端口名 ──
            port_name = port.name

            # ── 位宽：直接从类型对象获取 bitWidth ──
            width = port.type.bitWidth

            ports_info.append({
                'name': port_name,
                'direction': direction,
                'type': port_type,
                'width': width,
            })

        all_ports.extend(ports_info)

    return all_ports


def main():
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(script_dir, 'simple_alu.sv')

    if not os.path.exists(filepath):
        print(f"错误: 文件不存在 - {filepath}")
        sys.exit(1)

    print(f"扫描文件: {filepath}")
    print()

    ports = scan_ports_ast(filepath)

    if not ports:
        print("未找到 IO 端口信息。")
        return

    # 打印表头
    print(f"{'端口名称':<12} {'方向':<10} {'类型':<12} {'位宽':<8}")
    print("-" * 44)

    for p in ports:
        print(f"{p['name']:<12} {p['direction']:<10} {p['type']:<12} {p['width']:<8}")

    print()
    print(f"共扫描到 {len(ports)} 个 IO 端口。")


if __name__ == "__main__":
    main()
