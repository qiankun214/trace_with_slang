"""流程③④共享的 sqlite schema 元数据(SQLAlchemy Core)。

6 张表 + 5 个索引,表结构定稿见 doc/flow3_design_spec.md §4(本节 DDL 为
`metadata.create_all` 的落地结果)。流程③(build_db)用它建库,流程④查询
复用同一份 Table 对象,避免两处手写表名/列名。

标志列(is_port / is_condition / is_port_conn)定义为 Integer:sqlite 无独立
布尔类型,Python bool 绑定为 1/0(spec §4 实测)。
"""

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    func,
)

metadata = MetaData()

# ── ① 实例层次树(§4.1):每处实例化一行,顶层 depth=1、parent_id NULL ──

instances = Table(
    "instances",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("path", Text, nullable=False, unique=True),  # 'alu_system.u_core'
    Column("name", Text, nullable=False),  # 实例名(顶层即模块名)
    Column("module_name", Text, nullable=False),  # 模块类型名
    Column("parent_id", Integer, ForeignKey("instances.id")),
    Column("depth", Integer, nullable=False),
    Column("file", Text, nullable=False),  # 模块定义文件绝对路径
)

# ── ② 实例端口(§4.1):每端口一行,按声明序(position 0 起) ──

instance_ports = Table(
    "instance_ports",
    metadata,
    Column("instance_id", Integer, ForeignKey("instances.id"), primary_key=True),
    Column("position", Integer, primary_key=True),
    Column("name", Text, nullable=False),
    Column("direction", Text, nullable=False),  # 'input'/'output'/'inout'/'ref'
    Column("bit_width", Integer, nullable=False),
)

# ── ③ 信号(§4.2):每个变量/端口/struct 字段一行,full_path 唯一 ──

signals = Table(
    "signals",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("instance_id", Integer, ForeignKey("instances.id"), nullable=False),
    Column("name", Text, nullable=False),  # 末段名
    Column("full_path", Text, nullable=False, unique=True),
    Column("type_name", Text),
    Column("bit_width", Integer),
    Column("kind", Text),  # variable/net/parameter/port/field
    Column("is_port", Integer, nullable=False, default=0),
    Column("direction", Text),  # 端口方向;非端口为 ''
    Column("definition_file", Text),  # 定义位置文件绝对路径
    Column("definition_line", Integer),  # 定义位置行号(1 起)
)

# ── ④ 赋值语句块(§4.3):含 port_connection 块,id = BlockInfo.index + 1 ──

blocks = Table(
    "blocks",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("instance_id", Integer, ForeignKey("instances.id"), nullable=False),
    Column("block_type", Text, nullable=False),
    Column("source_file", Text),
    Column("start_line", Integer),  # 1 起,含
    Column("end_line", Integer),  # 1 起,含
    Column("source_text", Text),  # 该行范围的原始源文本
)

# ── ⑤ 依赖边(§4.4):driver/load 的共同数据源,block_id 可 NULL ──

dep_edges = Table(
    "dep_edges",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("driven_signal_id", Integer, ForeignKey("signals.id"), nullable=False),
    Column("read_signal_id", Integer, ForeignKey("signals.id"), nullable=False),
    Column("block_id", Integer, ForeignKey("blocks.id")),
    Column("is_condition", Integer, nullable=False, default=0),
    Column("is_port_conn", Integer, nullable=False, default=0),
)

# ── ⑥ 索引(§4.5) ──
# 唯一性用表达式索引而非表级 UNIQUE:SQLite 的 UNIQUE 中 NULL 互不相等,
# 表级约束挡不住 block_id 为 NULL 的重复边;COALESCE(block_id, 0) 兜住
# (block_id 从 1 起,0 作 NULL 哨兵安全)。
Index(
    "idx_edges_unique",
    dep_edges.c.driven_signal_id,
    dep_edges.c.read_signal_id,
    func.coalesce(dep_edges.c.block_id, 0),
    dep_edges.c.is_condition,
    dep_edges.c.is_port_conn,
    unique=True,
)
Index("idx_signals_name", signals.c.name)
Index("idx_signals_inst", signals.c.instance_id)
Index("idx_edges_driven", dep_edges.c.driven_signal_id)
Index("idx_edges_read", dep_edges.c.read_signal_id)
