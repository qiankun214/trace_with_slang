"""流程②输出数据模型(纯数据 dataclass)。

ParseResult 及 InstanceInfo / SignalInfo / BlockInfo / DepEdge / PortInfo
六个 dataclass,是流程②(pyslang 解析)→ 流程③(sqlite 落库)的纯数据接口,
不含任何 pyslang 对象(Compilation/Symbol 生命周期止于流程②内部)。
字段级定义与行为契约见 doc/flow2_design_spec.md §1.3–§1.7;类型清单见
doc/types.md。

命名说明:不采用 types.py —— src/ 位于 pythonpath 时与标准库 types 模块
冲突(进程内标准库 types 先被导入后,`from types import ParseResult` 实测
报 ImportError),故命名 datatypes.py。
"""

from dataclasses import dataclass


@dataclass
class PortInfo:
    """实例端口信息(§1.4)。"""

    name: str  # 端口名,如 'clk'
    direction: str  # 'input'/'output'/'inout'/'ref'
    bit_width: int  # port.type.bitWidth(无类型时 0)


@dataclass
class InstanceInfo:
    """实例层次树节点(§1.4),每处实例化一条。"""

    path: str  # 层次路径,如 'alu_system.u_core'(顶层为模块名)
    name: str  # 实例名(顶层即模块名)
    module_name: str  # 模块类型名(inst.definition.name)
    depth: int  # 层次深度(顶层为 1)
    file: str  # 模块定义文件绝对路径
    ports: list[PortInfo]  # 端口列表(body.portList,按声明序)


@dataclass
class SignalInfo:
    """信号行(§1.5);按 full_path 唯一,port 与同名内部变量合并为一行。"""

    instance_path: str  # 所在实例层次路径
    full_path: str  # 完整信号路径,如 'alu_system.u_core.add_sum'
    name: str  # 末段名
    type_name: str  # str(symbol.type) 或 str(field.type),无类型时 '<unknown>'
    bit_width: int  # type.bitWidth(无则 0)
    kind: str  # 'variable'/'net'/'parameter'/'port'/'field'
    is_port: bool  # 是否端口信号
    direction: str  # 端口方向,非端口为空串
    definition_file: str  # 定义位置文件绝对路径
    definition_line: int  # 定义位置行号(1 起)


@dataclass
class BlockInfo:
    """赋值语句块(§1.6),含 port_connection 块。"""

    instance_path: str  # 所属实例层次路径(port_connection 记父实例)
    index: int  # 全局块序号(全列表序 0 起,唯一)
    block_type: str  # 'always_comb'/'always_ff'/'always_latch'/'always'/
    #                  'initial'/'final'/'assign'/'port_connection'
    source_file: str  # 源文件绝对路径
    start_line: int  # 起始行号(1 起,含)
    end_line: int  # 结束行号(1 起,含)
    source_text: str  # 该行范围的原始源文本


@dataclass
class DepEdge:
    """依赖边(§1.7):driver/load 的共同数据源,两端为信号 full_path。"""

    driven_signal: str  # 被驱动信号 full_path(LHS)
    read_signal: str  # 被读取信号 full_path(RHS/条件/端口)
    block: BlockInfo | None  # 显式绑定产生这条边的块对象(纯数据,§9);
    #  该块因无源语法被跳过时为 None(§5 规则 8)
    is_condition: bool  # 门控条件读(通道2);RHS 读(通道1)为 False
    is_port_conn: bool  # 跨模块端口连接边;块内依赖边为 False


@dataclass
class ParseResult:
    """流程②总输出(§1.3),四列表均为纯数据、顺序确定可复现。"""

    instances: list[InstanceInfo]  # 实例层次树(§1.4)
    signals: list[SignalInfo]  # 信号行(§1.5),按 full_path 唯一
    blocks: list[BlockInfo]  # 赋值语句块(§1.6),含 port_connection 块
    dep_edges: list[DepEdge]  # 依赖边(§1.7),显式绑定块对象
