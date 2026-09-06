# 流程③ sqlite 落库 — Design Spec

> 定位:4 流程流水线第 3 级,把流程②输出的纯数据 `ParseResult` 一次性持久化到
> sqlite 数据库;此后流程④只读该库查询,无需重新解析。
> 与 `doc/structure.md` §流程③ 对应,本规格更细,可作为重建实现的行为契约。
> 表结构以本规格 §4 定稿为准;`doc/ref.md` §7.1 为设计初稿,差异汇总见 §4.6。
> 输入数据模型与顺序契约见 `doc/flow2_design_spec.md` §1(ParseResult 及
> InstanceInfo / PortInfo / SignalInfo / BlockInfo / DepEdge,定义于
> `src/datatypes.py`);查询示例(流程④备查)见 `doc/ref.md` §7.2。
> 日志统一经 loguru 打印(统计 `logger.info` / 告警 `logger.warning`)。
> 2026-09-06 初稿:基于 flow2 定稿后的数据模型编写;表结构在 ref.md §7.1 基础上
> 定稿(signals 补 definition 两列、新增 instance_ports 表、唯一约束改表达式索引)。
> 二次修订:实现改用 **SQLAlchemy Core**(Table 元数据 + insert + `engine.begin()`
> 事务),不手写 sqlite3 连接与 DDL;表元数据定义于 `src/schema.py`,流程④复用。
> 关键用法已在 sqlalchemy 2.0.52 + sqlite 实测(表达式唯一索引、connect 事件
> PRAGMA、显式 id 批量插入、事务自动回滚,见 §4.5/§5)。

## 1. 输入 / 输出

### 1.1 总览

```
流程②输出 ParseResult(纯数据,顺序确定可复现)
   │  instances / signals / blocks / dep_edges
   ▼
build_db(parse_result, db_path)  ── 全量重建 + 依序落库 ──▶  sqlite 数据库文件
   │                                                           6 表 + 5 索引
   ▼                                                           (§4)
流程④(db 路径 + var_path)输入
```

- **输入**:流程②的输出 — `ParseResult`(flow2 §1.3),四列表纯数据、
  顺序确定可复现;`dep_edges` 显式持有 `ParseResult.blocks` 中的
  BlockInfo 对象
- **输出**:sqlite 数据库文件(`db_path` 指向的物理文件),含 6 张表
  (§1.3);函数返回 `None`,调用方持有路径
- 流程③**功能**:把内存中的解析事实一次性持久化 —— 实例树、信号行、
  赋值块、依赖边,全部按 flow2 的产出顺序落库;边表同时服务 driver 与
  load 两个查询方向(flow2 §6.4)

### 1.2 公开函数清单(1 个)

| 函数(签名) | 输入 | 输出 | 功能 |
|---|---|---|---|
| `build_db(parse_result: ParseResult, db_path: str) -> None` | ParseResult(flow2 输出,空四列表合法) + db 文件路径(任意路径,相对路径基于当前工作目录) | 无(副作用:db 文件落盘) | **一级函数**:删旧库→建 schema→单事务依序插入四组信息→统计日志(§2) |

- 实现基于 SQLAlchemy Core(§2/§3),依赖 `sqlalchemy>=2.0`(已列入 requirements.txt);
  表元数据与流程④共享(`src/schema.py`),不手写 sqlite3/DDL

### 1.3 输出:数据库文件(6 表总览)

| 表 | 来源(ParseResult) | 粒度 | 关键约束 |
|---|---|---|---|
| `instances` | `instances` | 每处实例化一行 | `path` UNIQUE;`parent_id` 自引用(顶层 NULL) |
| `instance_ports` | `instances[].ports` | 每端口一行 | `(instance_id, position)` 主键 |
| `signals` | `signals` | 每信号行一行 | `full_path` UNIQUE;`instance_id` 外键 |
| `blocks` | `blocks` | 每块一行 | `id = index + 1`(§4.3) |
| `dep_edges` | `dep_edges` | 每边一行 | 两端信号外键;`block_id` 可 NULL;唯一表达式索引(§4.5) |

- 表行 id 由插入顺序决定,同输入 → 同库(id 序列可复现,§5 规则 11)
- flow2 不产出的数据本流程也不臆造;所有列均由 ParseResult 字段直接填充

### 1.4 完整示例

续 flow2 §1.8 的 mini.sv:`build_db(该 ParseResult, '/tmp/mini.db')` 后的库
(实现后以 pytest 固化):

```sql
instances:
  id=1  path='mini'  name='mini'  module_name='mini'  parent_id=NULL  depth=1  file='/abs/path/mini.sv'

instance_ports:
  instance_id=1  position=0  name='clk'  direction='input'   bit_width=1
  instance_id=1  position=1  name='a'    direction='input'   bit_width=4
  instance_id=1  position=2  name='y'    direction='output'  bit_width=4

signals:
  id=1  instance_id=1  name='clk'  full_path='mini.clk'  type_name='logic'      bit_width=1  kind='port'     is_port=1  direction='input'   definition_file='/abs/path/mini.sv'  definition_line=3
  id=2  instance_id=1  name='a'    full_path='mini.a'    type_name='logic'      bit_width=4  kind='port'     is_port=1  direction='input'   definition_file='/abs/path/mini.sv'  definition_line=4
  id=3  instance_id=1  name='y'    full_path='mini.y'    type_name='logic'      bit_width=4  kind='port'     is_port=1  direction='output'  definition_file='/abs/path/mini.sv'  definition_line=5
  id=4  instance_id=1  name='b'    full_path='mini.b'    type_name='logic[3:0]' bit_width=4  kind='variable' is_port=0  direction=''        definition_file='/abs/path/mini.sv'  definition_line=7

blocks:
  id=1  instance_id=1  block_type='assign'     source_file='/abs/path/mini.sv'  start_line=9   end_line=9   source_text='    assign y = a & b;'
  id=2  instance_id=1  block_type='always_ff'  source_file='/abs/path/mini.sv'  start_line=10  end_line=10  source_text='    always_ff @(posedge clk) b <= a;'

dep_edges:
  id=1  driven_signal_id=3  read_signal_id=2  block_id=1  is_condition=0  is_port_conn=0   -- y ← a(assign)
  id=2  driven_signal_id=3  read_signal_id=4  block_id=1  is_condition=0  is_port_conn=0   -- y ← b(assign)
  id=3  driven_signal_id=4  read_signal_id=2  block_id=2  is_condition=0  is_port_conn=0   -- b ← a(RHS)
  id=4  driven_signal_id=4  read_signal_id=1  block_id=2  is_condition=1  is_port_conn=0   -- b ← clk(门控)
```

要点:

- blocks 显式以 `id = index + 1` 插入(flow2 的 index 0/1 → id 1/2)
- 边的 block_id 经块对象身份映射解析,同一块的两条边 block_id 相同
- 信号 id 即 flow2 信号列表序(clk/a/y/b → 1/2/3/4);§6 的查询推演以此库为准

## 2. 整体处理流程

```
ParseResult(流程②输出)
   │
   ▼
build_db(parse_result, db_path)
   ├─ db_path 已存在 ──▶ 删除文件(全量重建语义,§5 规则 1)
   ├─ _create_engine:create_engine('sqlite:///<db_path>')
   │     + connect 事件监听:逐连接 PRAGMA foreign_keys=ON(§5 规则 2)
   ├─ _create_schema:metadata.create_all(engine) ── 6 表 + 5 索引
   │     (§4,元数据定义于 src/schema.py,流程④复用)
   ├─ with engine.begin() as conn:(单事务,§5 规则 4)
   │    ├─ _insert_instances ──▶ path→id 映射(parent_id 按 path 前缀反查)
   │    ├─ _insert_ports     ──▶ instance_ports 行(声明序 position)
   │    ├─ _insert_signals   ──▶ full_path→id 映射(instance_path 解析)
   │    ├─ _insert_blocks    ──▶ id(BlockInfo)→行 id 映射(id=index+1)
   │    └─ _insert_dep_edges ──▶ 信号 id + block_id 解析;解析失败告警丢弃(§7)
   │   (begin 上下文结束自动 commit;异常自动回滚)
   ├─ _log_summary:各表行数 logger.info
   └─ engine.dispose()
        │
        ▼
db_path 数据库文件 → 流程④输入
```

## 3. 子函数规划

| 函数 | 输入 | 输出 | 功能 |
|---|---|---|---|
| `build_db`(一级,公开) | `parse_result: ParseResult, db_path: str` | `None` | 总流程编排(§2);插入全部在一个事务内 |
| `_create_engine`(私有) | `db_path: str` | `sqlalchemy.Engine` | `create_engine('sqlite:///<db_path>')` 并挂 connect 事件监听注册 `PRAGMA foreign_keys=ON` |
| `_create_schema`(私有) | `engine` | `None` | `metadata.create_all(engine)` 建 6 表 + 全部索引(§4) |
| `_insert_instances`(私有) | `conn, instances: list[InstanceInfo]` | `dict[str, int]` | 按列表序批量插入实例行(显式 id),parent_id 按 path 前缀反查已建映射;返回 path→id 映射 |
| `_insert_ports`(私有) | `conn, instances, instance_ids` | `None` | 插入 instance_ports 行(position 自 0 按声明序递增) |
| `_insert_signals`(私有) | `conn, signals: list[SignalInfo], instance_ids` | `dict[str, int]` | 按列表序批量插入信号行(instance_id 解析,定义位置落列);返回 full_path→id 映射 |
| `_insert_blocks`(私有) | `conn, blocks: list[BlockInfo], instance_ids` | `dict[int, int]` | 按列表序插入块行,显式 `id = index + 1`;返回 `id(BlockInfo)`→行 id 映射(供边解析) |
| `_insert_dep_edges`(私有) | `conn, dep_edges: list[DepEdge], signal_ids, block_ids` | `None` | 解析两端信号 id 与 block_id 后插入;信号解析失败告警丢弃该边(§7) |
| `_log_summary`(私有) | `engine` | `None` | 统计各表行数并 `logger.info` 汇总(含丢弃边计数) |

**设计依据**:每个子函数单一职责、输入/输出类型明确;主函数只做编排(删旧库、
建引擎、建 schema、编排五个插入、统计、dispose)。**采用 SQLAlchemy Core
(Table 元数据 + `insert()` + `engine.begin()`),不用 ORM** —— 落库是纯批量
装载,无对象往返与会话状态需求,ORM 的 session/identity map 纯属负担;且表
元数据与查询语句可被流程④直接复用(`src/schema.py`)。`conn` 参数为
`sqlalchemy.Connection`,插入用 `conn.execute(表.insert(), [dict, ...])`
批量 list-of-dicts。插入顺序即 flow2 的产出顺序(flow2 §4),不需要任何排序;
映射字典在插入过程中逐步构建,不预先全量扫描。

## 4. 表结构定义(定稿)

> `doc/ref.md` §7.1 为初稿,本节为其定稿版本;差异汇总见 §4.6。
> DDL 由 `src/schema.py` 的 SQLAlchemy Table 元数据经 `create_all` 生成,
> 本节 SQL 即落地结果(sqlite_master 实测一致);标志列定义为 Integer,
> Python bool 绑定为 1/0(sqlite 无独立布尔类型)。

### 4.1 instances / instance_ports

```sql
CREATE TABLE instances (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,      -- 'alu_system.u_core'
    name        TEXT NOT NULL,             -- 'u_core'(顶层即模块名)
    module_name TEXT NOT NULL,             -- 'alu_core'
    parent_id   INTEGER REFERENCES instances(id),   -- 父实例行 id;顶层 NULL
    depth       INTEGER NOT NULL,          -- 顶层为 1
    file        TEXT NOT NULL              -- 模块定义文件绝对路径
);

CREATE TABLE instance_ports (
    instance_id INTEGER NOT NULL REFERENCES instances(id),
    position    INTEGER NOT NULL,          -- 端口声明序(0 起)
    name        TEXT NOT NULL,
    direction   TEXT NOT NULL,             -- 'input'/'output'/'inout'/'ref'
    bit_width   INTEGER NOT NULL,
    PRIMARY KEY (instance_id, position)
);
```

- `instances` 行与 `InstanceInfo` 一一对应;`parent_id` 由
  `path.rsplit('.', 1)` 反查 path→id 映射获得(无 '.' → NULL,§5 规则 6)
- `instance_ports` 持久化 `InstanceInfo.ports`(flow2 契约输出的端口清单;
  与 signals 的 port 行语义不同:本表是**实例端口列表**,按声明序,
  signals 是全局信号行)

### 4.2 signals

```sql
CREATE TABLE signals (
    id              INTEGER PRIMARY KEY,
    instance_id     INTEGER NOT NULL REFERENCES instances(id),
    name            TEXT NOT NULL,         -- 末段名,如 'div'
    full_path       TEXT NOT NULL UNIQUE,  -- 'csr_system.u_regfile.cfg_reg.baud.div'
    type_name       TEXT,                  -- str(type),无类型时 '<unknown>'
    bit_width       INTEGER,
    kind            TEXT,                  -- variable/net/parameter/port/field
    is_port         INTEGER NOT NULL DEFAULT 0,
    direction       TEXT,                  -- 端口方向;非端口为 ''
    definition_file TEXT,                  -- 定义位置文件绝对路径
    definition_line INTEGER                -- 定义位置行号(1 起)
);
```

- 行与 `SignalInfo` 一一对应,`full_path` 唯一性由 flow2 保证(flow2 §1.5),
  UNIQUE 约束兜底(冲突即程序错误,§7)
- `definition_file`/`definition_line` 为 flow3 定稿新增列(功能①"定义位置"
  查询必需;ref.md §7.1 初稿缺失,见 §4.6)

### 4.3 blocks

```sql
CREATE TABLE blocks (
    id          INTEGER PRIMARY KEY,       -- 显式插入 = BlockInfo.index + 1
    instance_id INTEGER NOT NULL REFERENCES instances(id),
    block_type  TEXT NOT NULL,             -- always_comb/always_ff/always_latch/always/
                                           -- initial/final/assign/port_connection
    source_file TEXT,
    start_line  INTEGER,                   -- 1 起,含
    end_line    INTEGER,                   -- 1 起,含
    source_text TEXT                       -- 该行范围的原始源文本
);
```

- 行与 `BlockInfo` 一一对应;`id = index + 1` 为**显式插入**的契约值
  (flow2 §9 允许"index 即自增 id"或"自行维护映射",本流程选择显式 id
  使对应关系不依赖 rowid 巧合;index 0 → id 1)
- 各列按 flow2 值原样落列(flow2 保证均有值;port_connection 块因无源语法
  被跳过时不产出 BlockInfo,故不存在"有块行无源文本"的情形)

### 4.4 dep_edges

```sql
CREATE TABLE dep_edges (
    id               INTEGER PRIMARY KEY,
    driven_signal_id INTEGER NOT NULL REFERENCES signals(id),   -- LHS
    read_signal_id   INTEGER NOT NULL REFERENCES signals(id),   -- RHS/条件/端口
    block_id         INTEGER REFERENCES blocks(id),             -- 边绑定的块;
                                                                -- NULL 仅为无对应块兜底
    is_condition     INTEGER NOT NULL DEFAULT 0,                -- 1=门控条件读(通道2)
    is_port_conn     INTEGER NOT NULL DEFAULT 0                 -- 1=跨模块端口连接边
);
```

- 行与 `DepEdge` 一一对应;两端 full_path → signal id 解析(§5 规则 10),
  block_id 经块对象身份映射解析,`block is None → NULL`(flow2 §9)
- 自依赖边(driven == read)两列同 id,正常插入
- 去重依赖 flow2 §5 规则 10(已按元组去重),库内唯一索引仅兜底(§4.5)

### 4.5 索引

```sql
CREATE UNIQUE INDEX idx_edges_unique ON dep_edges
    (driven_signal_id, read_signal_id, COALESCE(block_id, 0),
     is_condition, is_port_conn);
CREATE INDEX idx_signals_name ON signals(name);
CREATE INDEX idx_signals_inst ON signals(instance_id);
CREATE INDEX idx_edges_driven ON dep_edges(driven_signal_id);
CREATE INDEX idx_edges_read   ON dep_edges(read_signal_id);
```

- `full_path`/`path` 的 UNIQUE 约束自带隐式索引,无需重复建
- **`idx_edges_unique` 用表达式索引而非表级 UNIQUE 约束**:SQLite 的
  UNIQUE 中 NULL 互不相等,表级约束挡不住 block_id 为 NULL 的重复边;
  `COALESCE(block_id, 0)` 兜住该情形(block_id 从 1 起,0 作 NULL 哨兵安全)。
  元数据写法:`Index('idx_edges_unique', edges.c.driven_signal_id,
  edges.c.read_signal_id, func.coalesce(edges.c.block_id, 0),
  edges.c.is_condition, edges.c.is_port_conn, unique=True)`
  (实测生成的 DDL 与本节约简一致,NULL block 重复边可被拦截)
- `idx_edges_driven`/`idx_edges_read` 分别服务 driver(按 driven 查 read)
  与 load(按 read 查 driven)两个方向;`idx_signals_name` 服务按名全局搜索

### 4.6 与 ref.md §7.1 初稿的差异

| 项 | ref.md §7.1 初稿 | flow3 定稿 | 原因 |
|---|---|---|---|
| signals 表 | 无 definition 列 | 补 `definition_file`/`definition_line` | flow2 契约输出定义位置,功能①(变量信息)必需 |
| 表数量 | 5 张 | 6 张(新增 `instance_ports`) | 持久化 flow2 契约输出的 `InstanceInfo.ports`,避免实例端口清单在流程③丢失 |
| dep_edges 唯一性 | 表级 UNIQUE 约束 | 表达式唯一索引 `COALESCE(block_id, 0)` | 表级 UNIQUE 对 NULL 不生效,挡不住 block_id=NULL 的重复边(§4.5) |
| blocks.id | 未约定 | 显式 `id = index + 1` | flow2 §9 二选一的定稿选择(§4.3) |
| dep_edges.block_id 注释 | NULL=端口连接边 | NULL=无对应块兜底(端口连接边有 block 时非 NULL) | 与 flow2 §1.7 的显式对象绑定定稿一致 |

## 5. 处理规则

1. **全量重建**:db_path 已存在 → 先删除文件再建库;不提供增量/追加模式
   (设计变更重建是本项目的既定模型,ref.md §7.4)
2. `_create_engine`:`create_engine('sqlite:///<db_path>')` 后**必须**挂
   connect 事件监听执行 `PRAGMA foreign_keys=ON`(SQLAlchemy 按需创建
   连接,PRAGMA 只对单个连接生效,仅对 engine 执行一次无效;漏开则
   `REFERENCES` 约束静默失效)
3. `_create_schema`:`metadata.create_all(engine)`,表与索引的元数据定义于
   `src/schema.py`(与流程④共享,避免两处手写表名/列名;文件已删,无需 DROP)
4. **单事务**:全部插入包在 `with engine.begin() as conn:` 内 —— 成功自动
   commit、异常自动回滚(实测);插入用 `conn.execute(表.insert(),
   [dict, ...])` 批量 list-of-dicts;**行列表为空必须跳过执行** —— 空参数
   列表会被 SQLAlchemy 按单次无参执行(`INSERT ... DEFAULT VALUES`)
   而非 no-op(实测触发 NOT NULL 错误)
5. 插入顺序固定:instances → instance_ports → signals → blocks →
   dep_edges(外键依赖决定:边最后插入,需引用已建信号与块 id)
6. **全部表 id 由 Python 侧显式指定**(Core 批量插入不提供逐行 lastrowid,
   显式 id 与确定性规则一致):instances 行 id = 列表位置 + 1,严格按
   `ParseResult.instances` 列表序插入;`parent_id = path→id 映射
   [path.rsplit('.', 1)[0]]`(无 '.' → NULL);flow2 按 DFS 前序产出
   (父先于子),映射边插边建即可,无需两遍
7. instance_ports 按每实例的 `ports` 声明序插入,`position` 自 0 递增
8. signals 行 id = 列表位置 + 1,严格按 `ParseResult.signals` 列表序插入;
   `instance_id = instance_ids[instance_path]`(不在映射中 → KeyError
   直接爆出,flow2 契约保证一致);`direction` 原样落列(非端口为空串)
9. blocks 严格按 `ParseResult.blocks` 列表序插入,显式 `id = index + 1`
   (与规则 6 的显式 id 约定自然一致);边插边建 `id(BlockInfo) → id` 映射
   (对象身份,flow2 §9 契约)
10. dep_edges 行 id = 列表位置 + 1,严格按 `ParseResult.dep_edges` 列表序
    插入:两端信号 full_path → signal id 经映射解析,**解析失败 →
    logger.warning 并丢弃该边**(flow2 §9 契约的兜底防御,flow2 本身已
    先行过滤);block_id 经块对象身份映射解析,`block is None → NULL`
    (块对象不在映射中 → KeyError 直接爆出,flow2 §9 保证
    "不存在块键解析失败的情形")
11. **确定性**:显式 id + 严格按 ParseResult 列表序插入,无集合遍历、无排序;
    同输入 → 同库(全部 id 序列可复现)
12. 结束 `logger.info` 汇总各表行数与丢弃边计数,`engine.dispose()`;
    所有日志经 loguru,sink/格式/级别配置属调用方职责,本流程不初始化

## 6. 与流程④的接口契约

- 输出为 db 文件路径;流程④输入 = db 路径 + 变量层次路径(var_path),
  **只读连接**查询,无需重新解析
- 四大功能对应的 SQL 模式(以 §1.4 的库推演):

| 功能 | SQL 模式 | §1.4 推演 |
|---|---|---|
| 变量信息 | `SELECT * FROM signals WHERE full_path = ?` | 'mini.b' → id 4 行(类型 logic[3:0]、位宽 4、定义 mini.sv:7) |
| 赋值语句块 | 以该信号为 driven 的边的 block_id → blocks:`SELECT DISTINCT b.* FROM dep_edges e JOIN blocks b ON b.id = e.block_id WHERE e.driven_signal_id = ?` | 'mini.b' → block_id 2 → always_ff 块(第 10 行) |
| trace load | `SELECT s.full_path FROM dep_edges e JOIN signals s ON s.id = e.driven_signal_id WHERE e.read_signal_id = ?` | 'mini.a' → {mini.y, mini.b} |
| trace driver | `SELECT s.full_path FROM dep_edges e JOIN signals s ON s.id = e.read_signal_id WHERE e.driven_signal_id = ?` | 'mini.b' → {mini.a, mini.clk}(含条件读) |

- driver/load 是同一张边表的两个方向(§4.4),落库一次、双向复用
- `is_condition`/`is_port_conn` 已落库:流程④可按需过滤(如 driver 结果
  是否含门控条件读、是否混入端口连接边,由 flow4 spec 定夺)
- 多级 fan-out 可直接用 SQLite 的 `WITH RECURSIVE`(≥3.8.3,示例见
  ref.md §7.2);是否提供多级查询属流程④职责
- base↔field 合并规则属流程④职责(flow2 §6.4 已预留提示:整 struct 赋值
  驱动基行、字段写驱动叶子行,SQL 侧层级合并规则在 flow4 spec 明确)
- 所有查询所需索引已由本流程建好(§4.5),流程④无需再建
- 流程④同样基于 `src/schema.py` 的 Table 元数据构建查询(flow4 spec 定);
  上述 SQL 模式是查询语义,不受实现方式影响

## 7. 错误处理

| 情形 | 规格行为 |
|---|---|
| 空 ParseResult(四列表空) | 正常建库(6 空表),不报错 |
| db_path 已存在(文件) | 删除重建,非错误(§5 规则 1) |
| db_path 指向已存在目录 / 父目录不存在 | sqlalchemy OperationalError 直接爆出;不自动创建目录(禁止过度 try) |
| instance_path 不在实例映射 | KeyError 直接爆出(flow2 契约破坏,程序错误) |
| 边端信号 full_path 不在信号映射 | `logger.warning` 并丢弃该边(flow2 §9 契约的兜底) |
| 边 block 对象不在块映射 | KeyError 直接爆出(flow2 §9 保证不存在此情形) |
| 重复边触发 UNIQUE 索引(含 NULL block 重复边) | sqlalchemy IntegrityError 直接爆出(flow2 §5 规则 10 已去重,冲突即程序错误;表达式索引拦截已实测) |
| 外键约束违反 | sqlalchemy IntegrityError 直接爆出(程序错误;FK 由 connect 事件 PRAGMA 保证生效,§5 规则 2,已实测) |
| 插入中途异常 | `engine.begin()` 自动回滚(已实测),异常爆出;半成品 db 文件不承诺清理(调用方可传临时路径成功后自行改名) |

> 所有日志统一经 loguru 输出;sink/格式/级别配置属调用方职责,本流程不初始化。

## 8. 边界情况

- 空 ParseResult → 库内含 6 张空表,流程④查询返回空结果
- `block=None` 的边(端口连接块因无源语法被跳过)→ `block_id` 落 NULL
- 自依赖边(driven == read)→ 两列同一 signal id
- 同一块产生多条边 → 多条 dep_edges 行共享同一 block_id
- 无端口模块 / 无实例化语句的设计 → instance_ports 空、无 port_connection 块
- 同名信号不同实例 → full_path 不同,各自成行
- 同一模块多处实例化 → 多 instances 行,parent_id 各自反查正确
- 路径含多级 '.'(如 'alu_system.u_core.add_sum')→ `rsplit('.', 1)`
  只切父级,不影响信号解析

## 9. 非目标(明确不做)

- 不做增量/追加建库(每次全量重建,§5 规则 1)
- 不用 ORM(session/identity map,批量装载不需要,§3 设计依据)
- 不做 schema 版本化 / meta 表 / 迁移工具
- 不做 sqlite 之外的存储格式(JSON/Postgres 等,ref.md §7.4 已否)
- 不做查询 API(流程④职责)
- 不做 ParseResult 一致性预校验(依赖 flow2 契约;仅边解析做告警丢弃兜底)
- 不做性能调优(WAL/缓存/连接池等,属调用方)
- 不做并发写支持(单写者,一次 build 一个连接)
