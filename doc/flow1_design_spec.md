# 流程① filelist 解析 — Design Spec

> 定位:4 流程流水线源头,为流程②(pyslang 解析)提供 `.sv` 文件清单。
> 与 `doc/structure.md` §流程① 对应,本规格更细,可作为重建实现的行为契约。
> 本规格对齐 VCS/Questa 等专业工具对 filelist 的约定:filelist 是命令行参数文本文件,
> 支持 `-f`(嵌套 filelist)、`-v`(库文件)、`-y`(库目录)与 `#` 注释
> (来源:VCS User Guide 通用知识;编写时环境网络受限未能在线核对,仅实现本规格列出的子集)。
> 日志统一经 loguru 打印(错误 `logger.error` / 告警 `logger.warning`)。

## 1. 输入 / 输出

- **输入**:filelist 文件路径(字符串)
- **输出**:`list[str]`,`.sv` 文件**绝对路径**列表;包含普通文件与 `-v`/`-y` 引入的库文件,按展开顺序合并,**去重**(保持首次出现顺序);路径中的环境变量(`$VAR`/`${VAR}`)在解析前展开
- **一级函数**:`parse_filelist(filelist_path: str) -> list[str]`

## 2. 整体处理流程

```
filelist.f 路径
   │
   ▼
┌─ 校验 filelist 存在 ──不存在──▶ logger.error + exit(1)
│        │ 存在
│        ▼
│  逐行读取(UTF-8)
│        │
│        ▼
│  行过滤:空行 / # 或 // 注释行 ──跳过──▶ (下一行)
│        │ 有效行
│        ▼
│  按空白拆分 token,按序处理:
│        ├─ 普通路径 ──▶ 展开环境变量 → 相对→绝对(基于本 filelist 目录)──缺失──▶ logger.warning,跳过
│        │                                 │ 存在
│        │                                 ▼ 加入结果
│        ├─ -f <子filelist> ──▶ 参数为相对路径──▶ logger.warning(可移植性提示)
│        │        │ 展开环境变量 → 解析为绝对(基于本 filelist 目录)
│        │        ├─ 递归层数 > 32 或已展开过(循环)──▶ logger.warning,跳过
│        │        └─ 未展开 ──▶ 递归展开(子 filelist 内路径基于其自身目录)
│        ├─ -v <文件> ──▶ 同普通路径处理(展开环境变量→相对→绝对→存在检查→加入/告警)
│        ├─ -y <目录> ──▶ 展开环境变量 → 存在则扫描目录下 .sv/.v 文件(非递归,文件名排序)加入;不存在──▶ logger.warning,跳过
│        └─ 其他选项 ──▶ logger.warning 并跳过(规则见 §4)
└────────┼─────────────
         ▼
  去重(保持首次出现顺序) → .sv 绝对路径列表 → 流程②
```

## 3. 子函数规划

| 函数 | 输入 | 输出 | 功能 |
|---|---|---|---|
| `parse_filelist`(一级,公开) | `filelist_path: str` | `list[str]` | 总流程编排 |
| `_assert_filelist_exists`(私有) | `filelist_path: str` | `None` | 校验路径存在;不存在时 `logger.error` 报错并以退出码 1 终止 |
| `_read_lines`(私有) | `filelist_path: str` | `list[str]` | 按 UTF-8 读取文件全部原始行 |
| `_is_skip_line`(私有) | `line: str` | `bool` | 去除首尾空白后为空(空行)或以 `#` 开头(注释行)→ `True`,否则 `False` |
| `_classify_token`(私有) | `token: str` | 类别标识 | 分类:`path`(普通路径)/ `flag_f` / `flag_v` / `flag_y` / `other_option`(`-`/`+` 开头的未知选项) |
| `_expand_env`(私有) | `entry: str` | `str` | 展开路径中的环境变量(`$VAR`/`${VAR}`,未定义展开为空串,语义同 `os.path.expandvars`) |
| `_expand_filelist`(私有) | `filelist_path: str, seen: set[str] \| None` | `list[str]` | 递归展开单个 filelist(§2 流程主体);`seen` 为已展开 filelist 集合,用于循环引用检测;递归层数限制 32 |
| `_resolve_abs_path`(私有) | `base_dir: str, entry: str` | `str` | 展开环境变量后,将相对路径基于 `base_dir` 解析为规范化绝对路径 |
| `_scan_library_dir`(私有) | `dir_path: str` | `list[str]` | 扫描目录下所有 `.sv`/`.v` 文件,按文件名排序,返回绝对路径列表 |
| `_dedup`(私有) | `paths: list[str]` | `list[str]` | 去除重复路径,保持首次出现顺序 |

**设计依据**:每个子函数单一职责、输入/输出类型明确;主函数只做编排,不做行级细节。

## 4. 处理规则

1. 若 filelist 路径不存在,必须终止处理并报错(见 §5)
2. 路径 token 在解析前必须先展开环境变量(`$VAR`/`${VAR}`,未定义展开为空串);展开后的路径基于 filelist 所在目录解析为**规范化绝对路径**(abspath);递归展开 `-f` 子 filelist 时,基准随子 filelist 所在目录切换
3. 逐行读取:去除行首尾空白后为空(空行)→ 跳过;以 `#` 或 `//` 开头(注释行)→ 跳过
4. 有效行按空白拆分为 token 序列,按序流式处理;单 token 纯路径行的行为与既有约定一致(保序、注释、缺失告警)
5. token 按 §2 流程图分发;`-f`/`-v`/`-y` 的参数取**下一个 token**(可在同一行或下一行,允许跨行)
6. `-f` 参数为相对路径 → `logger.warning`("filelist 相对路径"),仍基于当前 filelist 目录解析并递归展开;递归层数限制为常数 32,超出 → `logger.warning` 并跳过该引用
7. 循环引用:`-f` 指向已展开过的 filelist → `logger.warning` 并跳过该引用
8. 未知选项:
   - `+` 开头(plusarg,如 `+incdir+`):自包含,`logger.warning` 后跳过该 token
   - 其他 `-` 选项(非 `-f`/`-v`/`-y`):`logger.warning` 后跳过该 token **及其后一个参数 token**(参数不参与路径处理,不报"文件缺失"误警)
9. `-y` 目录扫描:仅目录下直接文件,非递归;只收 `.sv`/`.v`,忽略其他;按文件名排序保证结果确定性
10. 返回结果列表:保持行顺序;**去重(保持首次出现顺序)**;所有路径均为规范化绝对路径

## 5. 错误处理

| 情形 | 规格行为 |
|---|---|
| filelist 不存在 | `logger.error` 输出错误信息,以退出码 1 终止 |
| 单个 .sv 文件缺失 | `logger.warning` 输出警告,跳过该行,继续解析其余行 |
| `-f` 参数为相对路径 | `logger.warning`,继续解析(仍基于本 filelist 目录) |
| `-f` 循环引用 | `logger.warning`,跳过该引用 |
| `-f` 递归层数超过 32 | `logger.warning`,跳过该引用 |
| 环境变量未定义(展开为空串) | 展开后路径为空或不存在 → `logger.warning`,跳过(同缺失文件处理) |
| `-y` 目录不存在 | `logger.warning`,跳过 |
| 未知选项 | `logger.warning`,按 §4 规则跳过 |

> 所有日志统一经 loguru 输出(错误 `logger.error` / 告警 `logger.warning`);sink/格式/级别配置属调用方职责,本流程不初始化。

## 6. 边界情况

- 仅含注释/空行的 filelist → 返回空列表 `[]`
- 所有行均指向不存在的文件 → 返回 `[]`,逐条告警
- 同一文件出现多行(含经普通行与 `-v` 重复)→ 去重,仅保留首次出现的路径
- 相对路径(含 `../`)基于 filelist 所在目录解析,输出为规范化绝对路径
- 嵌套 `-f` 深度最多 32 层(超出告警跳过,见 §5)
- `-y` 目录为空 → 不产生文件;目录含非 `.sv`/`.v` 文件 → 忽略
- 环境变量展开支持 `$VAR` 与 `${VAR}` 两种写法;未定义 → 展开为空 → 按缺失处理

## 7. 与流程②的接口契约

- 输出(.sv 绝对路径列表,含库文件)直接作为流程②的输入,传路径不传文件对象
- 空列表是合法输入,流程②必须能处理

## 8. 非目标(明确不做)

- 不实现 VCS 严格"按需编译"语义(库文件全部加入编译;同名模块冲突由流程②诊断)
- 不展开 include / 宏 / 通配符,不处理 `+incdir+`(属编译器职责)
- `-y` 不递归扫描子目录
- 不做编码容错(BOM 等,按 UTF-8 读取)
- 不校验 .sv 文件内容(语法检查属流程②)
