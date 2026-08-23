# 自定义类型清单

> 记录本项目所有自定义类型(dataclass),标注功能。字段级定义详见各流程 spec:
> 流程② dataclass 见 `doc/flow2_design_spec.md` §1;流程①/③/④ 的自定义类型
> 在各自 spec 定稿后补入本表。

## 流程②(pyslang 解析与信息提取)

定义于 `src/`(待实现),是流程② → 流程③ 的纯数据接口,不含任何 pyslang 对象。

| 类型 | 功能 | 关键字段 |
|---|---|---|
| `ParseResult` | 流程②总输出,流程③建库的直接输入 | `instances` / `signals` / `blocks` / `dep_edges` 四列表(确定顺序,可复现) |
| `InstanceInfo` | 实例层次树节点(instances 表行) | `path`(层次路径) / `name` / `module_name` / `depth` / `file` / `ports` |
| `PortInfo` | 实例端口信息 | `name` / `direction` / `bit_width` |
| `SignalInfo` | 信号行(变量/网络/参数/端口/struct 字段;按 `full_path` 唯一,port 与同名内部变量合并为一行) | `instance_path` / `full_path` / `name` / `type_name` / `bit_width` / `kind` / `is_port` / `direction` / `definition_file` / `definition_line` |
| `BlockInfo` | 完整赋值语句块(always/assign/port_connection,blocks 表行) | `instance_path` / `index`(全局块序号,作为 block 键) / `block_type` / `source_file` / `start_line` / `end_line` / `source_text` |
| `DepEdge` | 依赖边(dep_edges 表行;driver/load 的共同数据源) | `driven_signal` / `read_signal`(full_path) / `block`(**显式绑定** BlockInfo 对象,可为 None) / `is_condition` / `is_port_conn` |

## 流程①(filelist 解析)

定义于 `src/filelist.py`,为流程内部私有类型,不跨流程传递:

| 类型 | 功能 | 可见性 |
|---|---|---|
| `_ExpansionContext` | `-f` 递归展开上下文(seen 集合 + 深度) | 私有 |
| `_TokenCursor` | token 流游标(顺序消费) | 私有 |
