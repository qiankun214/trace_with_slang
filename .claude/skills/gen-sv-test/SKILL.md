---
name: gen-sv-test
description: This skill should be used when the user asks to generate SystemVerilog test data, create multi-level module hierarchies for testing, produce SV test fixtures with submodules, or batch-generate synthesizable SV modules for tool validation. Triggers on phrases like "生成测试数据", "generate test SystemVerilog", "create multi-level SV modules", "批量生成SV模块", "generate SV test fixtures", or similar requests for creating hierarchical SystemVerilog designs for testing purposes.
version: 1.1.0
---

# SystemVerilog Test Data Generator

Generate multi-level, hierarchical SystemVerilog module designs suitable for testing downstream tools (parsers, linters, synthesizers, waveform viewers). Every generated design must compile cleanly under Icarus Verilog and use only synthesis-safe constructs.

## Design Constraints (non-negotiable)

1. **Hierarchy depth ≥ 2 levels** — a top module must instantiate at least 2 child modules, at least one of which instantiates at least 1 grandchild module.
2. **Submodule count ≥ 2** — the top module must contain at least 2 direct child instances.
3. **Synthesizable syntax only** — `always_ff`, `always_comb`, `assign`, `logic` types, `enum` for FSM states. No `initial`, `$display`, `$monitor`, `class`, dynamic arrays, queues, or fork/join.
4. **Icarus Verilog 12.0** — compile with `iverilog -g2012 -c filelist.f` and confirm exit code 0.
5. **ANSI-style port lists** — `input logic` / `output logic` with packed vector ranges.

## Workflow

### Step 1: Determine Target Directory and Design Theme

Ask the user (or infer from context) the target directory. Default to `test/with_instance/` under the current project root.

Choose a **realistic hardware theme** that naturally produces hierarchy. Preferred themes (pick one that fits the user's need):

| Theme | Top Module | Level-2 Children | Level-3 Grandchildren |
|---|---|---|---|
| ALU System | `alu_system` | `alu_core`, `alu_control`, `result_stage` | `adder_8bit`, `logic_unit` (inside alu_core) |
| GPIO Controller | `gpio_controller` | `gpio_regfile`, `gpio_pad_ctrl`, `intr_handler` | `reg_bank`, `sync_ff` (inside gpio_regfile) |
| FIFO Pipeline | `fifo_pipeline` | `sync_fifo`, `pipe_stage`, `flow_ctrl` | `fifo_mem`, `ptr_sync` (inside sync_fifo) |
| Counter System | `counter_system` | `cnt_8bit`, `cnt_16bit`, `cmp_unit` | `adder_8bit`, `mux_2to1` (inside cnt_8bit) |
| CSR Config System | `csr_system` | `csr_regfile`, `intr_handler`, `bus_decoder` | `baud_gen`, `irq_arbiter` (inside csr_regfile/intr_handler); `pulse_counter` (L4 inside baud_gen) |

> **CSR Config System** 是专门为测试 SystemVerilog `struct` 支持而设计的主题，包含 package 共享类型、struct 端口、模块内 typedef、嵌套 struct 等场景。详见下方 "Struct-Aware Test Data" 章节。

### Step 2: Design the Module Hierarchy

Before writing code, plan the full hierarchy on paper/plan file:

```
top_module (Level 1)
├── child_a (Level 2)
│   ├── grandchild_a1 (Level 3)
│   └── grandchild_a2 (Level 3)
├── child_b (Level 2)
└── child_c (Level 2)
```

Define port lists for every module. Each module must have a clearly defined function — no "dummy" or empty modules.

### Step 3: Create Source Files (Bottom-Up)

Write modules from **leaf to root** so iverilog compilation order matches filelist order:

1. **Level 3 modules first** — pure combinational or simple sequential logic. These are the building blocks. See `references/templates.md` for starter code.
2. **Level 2 modules** — instantiate Level 3 children, add muxing/control logic.
3. **Level 1 (top) module** — instantiate all Level 2 children, wire them together.

Coding rules per module:
- One module per file, filename = module name + `.sv`
- Header comment block identifying the module's level and its parent
- ANSI port declarations
- Separate `always_comb` for next-state logic and `always_ff` for registers
- Named port connections on all instantiations (`.port_name(signal_name)` style)
- Instance names use `u_` prefix

### Step 4: Create filelist.f

Write `filelist.f` with modules ordered bottom-up (Level 3 → Level 2 → Level 1). Each line is a relative filename. Add a header comment showing the hierarchy.

### Step 5: Compile and Verify

```bash
cd <target_directory>
iverilog -g2012 -c filelist.f -o <top_module>.vvp 2>&1
```

Checklist:
- [ ] Exit code = 0
- [ ] No errors (warnings about `unique case` from vvp are acceptable)
- [ ] The `.vvp` output file exists
- [ ] Verify file count matches the plan

If compilation fails, read the error, fix the file, and recompile. Do NOT leave broken code.

### Step 6: Report

Summarize the generated design:
- Module hierarchy diagram (ASCII tree)
- File listing with levels
- Compilation result

## Parameterization

When generating multiple test datasets, vary these dimensions across runs:

- **Hierarchy depth** (2, 3, or 4 levels)
- **Number of children per parent** (2, 3, or more)
- **Design theme** (ALU, GPIO, FIFO, Counter, custom)
- **Interface complexity** (number of ports, data width)
- **Control logic style** (FSM vs. pipelined vs. purely combinational)

Each variant goes into its own subdirectory under `test/`.

## Struct-Aware Test Data

当需要生成包含 SystemVerilog `struct` 的测试数据时，应覆盖以下 **5 种场景**：

| 场景 | 描述 | 实现方式 | 示例 |
|------|------|----------|------|
| S1 结构体在模块内部 | struct 类型信号在模块内声明和使用 | `import pkg::*;` 后在模块体内声明 struct 变量 | `csr_cfg_t cfg_reg;` |
| S2 结构体在端口上 | 模块端口使用 struct 类型 | `input/output <struct_type>` 在端口列表中 | `input baud_cfg_t cfg_i` |
| S3 模块内 typedef struct | struct 类型在模块作用域内私有定义 | `typedef struct packed {...} local_t;` 在模块内 | `intr_status_local_t` |
| S4 集中文件定义 | struct 类型在 package 中统一定义 | `package pkg; typedef struct packed {...} t; endpackage` | `csr_pkg.sv` |
| S5 结构体嵌套 | struct 字段本身是另一个 struct 类型 | 在 packed struct 内嵌入另一个 struct 类型 | `csr_cfg_t` 内含 `baud_cfg_t` + `irq_cfg_t` |

### Struct 设计约束

1. **端口 struct 必须为 `packed`** — Verilator 5.x 不支持 unpacked struct 端口；Icarus 12 对 unpacked struct 端口支持也有限
2. **嵌套 struct 必须全链 `packed`** — 嵌套链中所有 struct 都声明为 `packed`，确保 Verilator 正确展平
3. **顶层端口全标量** — 顶层模块端口使用标量类型，C++ 测试台只触碰标量引脚，规避 Verilator struct 端口扁平化 API 的不确定性
4. **提供回读向量** — 使用 `assign cfg_debug = cfg_reg;` 将 struct 转为位流向量输出，方便 C++ 测试台直接校验
5. **struct 字段名避免 SystemVerilog 关键字** — 已知 Icarus 12 中 `priority` 是保留字，不能用作 struct 字段名；其他如 `mode`、`type`、`begin` 等也应避免
6. **`typedef struct packed` 优于 `struct packed`** — 使用 typedef 定义命名类型，方便端口声明和复用

### 典型 struct 测试层次设计

struct 测试数据应同时满足 ≥3 层子模块调用深度。推荐 CSR 主题层次：

```
csr_system (L1 顶层，纯标量端口)
├── csr_regfile u_regfile (L2)              [S1: 内部struct信号]
│   └── baud_gen u_baud (L3)                [S2: struct端口]
│       └── pulse_counter u_counter (L4)    [标量对照基线]
├── bus_decoder u_decode (L2)               [纯标量对照基线]
└── intr_handler u_intr (L2)                [S3: 模块内typedef struct]
    └── irq_arbiter u_arbiter (L3)          [S5: 嵌套struct字段访问]
```

3 层子模块调用路径：`csr_system.u_regfile.u_baud.u_counter`

参考实现：`test/with_struct/`

## Package 使用指南

### Package 文件 (如 `csr_pkg.sv`)

```systemverilog
package csr_pkg;
    typedef struct packed {
        logic [15:0] div;
        logic [2:0]  oversample;
        logic        mode;          // 注意：避免使用 priority 等关键字作字段名
    } baud_cfg_t;

    // 嵌套结构体：struct 内包含另一个 struct
    typedef struct packed {
        baud_cfg_t  baud;
        irq_cfg_t   irq;
    } csr_cfg_t;
endpackage
```

### Package 编译顺序

- **filelist.f 中 package 文件必须置于最前** — 所有使用该 package 的模块之前编译
- 使用 `import csr_pkg::*;` 引入类型

### 端口类型可见性（关键！）

```systemverilog
// ★ 正确: import 放在模块声明之前（文件作用域），端口声明可见
import csr_pkg::*;

module my_mod (
    input  baud_cfg_t  cfg_i,    // 端口类型可解析
    output logic       tick_o
);
    // 模块体内不需要重复 import
endmodule
```

```systemverilog
// ★ 错误: import 只在模块体内，端口声明不可见
module my_mod (
    input  baud_cfg_t  cfg_i,    // Icarus/Verilator 报错: 未知类型
    output logic       tick_o
);
    import csr_pkg::*;           // 太晚了，端口已解析
endmodule
```

> **规则**: 若模块端口使用 package 类型，`import pkg::*;` 必须放在 `module ... ( ` 之前（文件作用域）。模块内部信号使用 package 类型时，模块内 import 也有效，但建议统一使用文件作用域 import 保持一致性。

### struct 赋值语法兼容性

```systemverilog
// ★ Icarus 12 不支持 '{} 赋值模式，使用逐字段赋值
// 不支持:  status_synced <= '{tx_done_s: tx_done_i, rx_ready_s: rx_ready_i, ...};
// 应使用:
always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        status_synced <= '0;             // 支持整结构体清零
    end else begin
        status_synced.tx_done_s  <= tx_done_i;    // 逐字段赋值
        status_synced.rx_ready_s <= rx_ready_i;
    end
end

// assign 逐字段赋值也支持
assign status_pack.tx_busy  = tx_busy_i;
assign status_pack.rx_ready = rx_ready_i;

// 整结构体赋值（同类型之间）支持
assign cfg_o = cfg_reg;    // csr_cfg_t → csr_cfg_t
assign baud_o = cfg_reg.baud;  // 提取子结构体
```

## Verilator 验证工作流

### 新增: Verilator C++ 仿真测试

对于 struct 测试数据，**必须使用 Verilator 进行编译+仿真验证**（Icarus 仅编译检查不够，struct 成员访问的行为需运行时验证）。

#### C++ 测试台模板

```cpp
#include "V<top_module>.h"
#include "verilated.h"
#include <cstdio>

static int errors = 0;
#define CHECK(cond, name) do { \
    if (!(cond)) { errors++; printf("  FAIL: %s\n", name); } \
    else printf("  PASS: %s\n", name); \
} while(0)

int main(int argc, char** argv) {
    VerilatedContext* ctx = new VerilatedContext;
    ctx->commandArgs(argc, argv);
    V<top_module>* dut = new V<top_module>{ctx};

    // 1. 复位序列
    dut->rst_n = 0;
    // ... toggle clock 5 cycles ...
    dut->rst_n = 1;

    // 2. 按场景分组测试
    // S1: 写 struct 字段 → 回读校验
    // S2: struct 端口传递 → 功能验证
    // S3: 模块内 typedef struct → 行为验证
    // S5: 嵌套 struct 字段访问 → 逻辑验证
    // Baseline: 标量对照模块 → 功能验证

    dut->final();
    delete dut; delete ctx;
    printf(errors ? "*** %d TESTS FAILED ***\n" : "*** ALL TESTS PASSED ***\n", errors);
    return errors ? 1 : 0;
}
```

#### Makefile 模板（兼容 Icarus + Verilator）

```makefile
VERILATOR ?= verilator
IVERILOG  ?= iverilog
TOP        = <top_module>
TRACE      ?= 0

.PHONY: iv-check verilate sim trace clean

iv-check:
	$(IVERILOG) -g2012 -c filelist.f -o $(TOP).vvp

verilate:
	$(VERILATOR) --cc --exe --build -f filelist.f sim_main.cpp \
	  --top-module $(TOP) \
	  -Wall -Wno-fatal \
	  -Wno-UNUSEDSIGNAL \
	  -Wno-UNUSEDPARAM \
	  -Wno-WIDTHEXPAND \
	  -Wno-WIDTHTRUNC \
	  $(if $(filter 1,$(TRACE)),--trace)

sim: verilate
	./obj_dir/V$(TOP)

trace: TRACE=1
trace: verilate
	./obj_dir/V$(TOP)

clean:
	rm -rf obj_dir *.vvp *.vcd *.lxt
```

#### 验证步骤

1. `make iv-check` — Icarus 编译检查（退出码 0）
2. `make verilate` — Verilator C++ 构建（退出码 0，无 fatal error）
3. `make sim` — C++ 仿真测试（`ALL TESTS PASSED`，退出码 0）
4. `make trace` — 可选波形生成
5. 工具冒烟 — 使用项目 pyslang 工具（`hierarchy.py`、`hierarchy_var.py`）验证层次和变量提取

#### .gitignore

将 Verilator 生成的 `obj_dir/` 加入 `.gitignore`。

## 已知陷阱 (Pitfalls)

### Icarus Verilog 12 限制

| 问题 | 表现 | 解决方案 |
|------|------|----------|
| `priority` 是保留字 | `syntax error: Error in struct/union member` | 重命名为 `prio_level` 等 |
| `import pkg::*` 在模块内 | 端口声明报 `Errors in port declarations` | 将 import 移到模块声明之前（文件作用域） |
| `'{field: value, ...}` 赋值 | `syntax error` / `Malformed statement` | 改用逐字段赋值 `s.field <= value;` |
| `'{default:0}` 模式 | 不支持 | 使用 `'0` 清零整结构体 |

### Verilator 5.x 限制

| 问题 | 表现 | 解决方案 |
|------|------|----------|
| unpacked struct 端口 | 编译报错 | 端口一律使用 `packed` struct |
| `import::*` 在 $unit 作用域 | `IMPORTSTAR` 警告 | 可安全忽略，或用 `-Wno-IMPORTSTAR` 抑制 |
| 空端口连接 `.port()` | `PINCONNECTEMPTY` 警告 | 可安全忽略，或用 `-Wno-PINCONNECTEMPTY` 抑制 |

### struct 字段名黑名单 (Icarus 12)

以下 SystemVerilog 关键字**不能**用作 struct 字段名（已验证）：

- `priority` — 语法错误

建议避免使用任何 SV 关键字作为字段名，优先使用带下划线前缀/后缀的描述性名称（如 `prio_level`、`mode_sel` 而非 `mode`）。

## Reference Files

- `references/templates.md` — Starter templates for leaf, intermediate, and top modules
- `references/synthesis_rules.md` — Detailed synthesis-safety checklist
