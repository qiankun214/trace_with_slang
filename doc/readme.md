# readme — trace_with_slang 使用说明

SystemVerilog trace 分析工具：pyslang 解析 filelist → 信息提取落 sqlite 库 →
四大查询（变量信息 / 赋值语句块 / trace load / trace driver）。

```text
filelist 路径 ──▶ ① parse_filelist ─▶ .sv 列表 ─▶ ② extract_design ─▶
ParseResult ─▶ ③ build_db ─▶ sqlite 库 ─▶ ④ 四大查询函数 ─▶ 结果
```

使用方式二选一：**CLI**（本文件 §2/§3，`src/cli.py`，架构外的调用方，仅串联
四个流程的一级函数，不触碰流程内部契约，见 doc/flow4_design_spec.md §9）
或 **Python API**（§4）。查询只读 sqlite，无需重新解析 SV。

## 1. 环境

- python 虚拟环境 `.venv`；依赖见 requirements.txt（pyslang / sqlalchemy / loguru）
- CLI 无打包安装，运行 `python src/cli.py <子命令> ...`（src 为平铺模块，
  脚本目录自动入 sys.path）

## 2. CLI 快速开始（用仓库自带演示素材）

```bash
# ① 解析 filelist 并落库:默认生成与 filelist 同目录同名的 .sqlite
python src/cli.py build test/with_instance/filelist.f
#   → test/with_instance/filelist.sqlite(build 日志走 stderr)

# ② 四大查询(结果走 stdout,可直接管道消费)
python src/cli.py info   test/with_instance/filelist.sqlite alu_system.u_core.add_sum
python src/cli.py blocks test/with_instance/filelist.sqlite alu_system.u_core.add_sum
python src/cli.py load   test/with_instance/filelist.sqlite alu_system.u_core.add_sum
python src/cli.py driver test/with_instance/filelist.sqlite alu_system.u_core.add_sum --json
```

各命令输出形态：

- **info**：中文标签键值对文本（类型 / 位宽 / 定义文件:行 等 10 项）
- **blocks**：块元信息 + 源文本原样打印，多条以分隔线隔开
- **load / driver**：每行一个信号 full_path（升序去重），无标题便于管道
- 任意查询子命令加 `--json` 改输出 JSON（字段名为 dataclass 字段名，
  `ensure_ascii=False` 缩进 2）；管道用法例：`cli.py driver db var | sort`

## 3. CLI 参考

### 子命令与参数

| 子命令 | 参数 | 功能 |
|---|---|---|
| `build` | `FILELIST` `[-o DB]` | 串联 ①+②+③ 落库；`-o` 缺省 = filelist 同目录同 stem + `.sqlite`；父目录须已存在；无 stdout，落库汇总走 loguru INFO |
| `info` | `DB` `VAR_PATH` `[--json]` | 变量信息（精确匹配，无 base↔field 合并） |
| `blocks` | `DB` `VAR_PATH` `[--json]` | 完整赋值该变量的语句块（含源文本） |
| `load` | `DB` `VAR_PATH` `[--json]` | trace load：读取该变量的赋值块所驱动的信号 |
| `driver` | `DB` `VAR_PATH` `[--json]` | trace driver：驱动该变量的赋值块内被读的信号 |

VAR_PATH 为完整层次路径，如 `alu_system.u_core.add_sum`（点号无需转义）。

### 输出通道与退出码

- 结果 → **stdout**；loguru 日志（含错误）→ **stderr**
- 退出码：`0` 成功（含无匹配块/边的空结果）；`1` 已知用户错误（filelist /
  db / 变量不存在）；`2` 参数用法错误；未预期异常直接 traceback 爆出
- 错误消息与 Python API 层一致：`filelist 不存在: …` / `数据库文件不存在: …` /
  `变量不存在: …`

## 4. Python API 一览

```python
from filelist import parse_filelist          # 流程①
from extract import extract_design           # 流程②
from build_db import build_db                # 流程③
from query import (                          # 流程④
    get_variable_info, get_assignment_blocks, trace_load, trace_driver,
)

sv_files = parse_filelist("test/with_instance/filelist.f")   # -> list[str]
result = extract_design(sv_files)                            # -> ParseResult
build_db(result, "alu.sqlite")                               # 全量重建落库

info = get_variable_info("alu.sqlite", "alu_system.u_core.add_sum")  # SignalInfo
blocks = get_assignment_blocks("alu.sqlite", "alu_system.u_core.add_sum")  # list[BlockInfo]
loads = trace_load("alu.sqlite", "alu_system.u_core.add_sum")      # list[str] 升序
drivers = trace_driver("alu.sqlite", "alu_system.u_core.add_sum")  # list[str] 升序
```

- 一级函数签名与行为契约：见 doc/structure.md 及各 flow*_design_spec.md
- 返回类型字段：见 doc/types.md（SignalInfo / BlockInfo / ParseResult 等）
- 错误契约：filelist 缺失 → 退出码 1 终止；db 路径非文件 → `FileNotFoundError`；
  var_path 无匹配信号 → `ValueError`；无匹配块/边 → 空列表（非错误）
- 运行测试：`python -m pytest`

## 5. 演示素材与已知限制

- `test/with_instance/filelist.f`：ALU 三层层次（经典查询
  `alu_system.u_core.add_sum`）
- `test/with_struct/filelist.f`：四层 + struct 字段展开场景（base↔field 合并）
- 已知限制 / 非目标：各 flow spec 对应章节（如纯常量赋值不产依赖边、
  CLI 不做编译告警之外的诊断等），查询语义细则以 doc/flow4_design_spec.md 为准
