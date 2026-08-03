# Module Templates

> 更新于 v1.1.0：新增 Package、Struct 模块、Verilator C++ 测试台、Makefile 模板。

## Package Template (共享结构体类型)

```systemverilog
//==============================================================================
// Package: <pkg_name>
// Type:    package (shared type definitions)
// 场景4: 结构体定义在集中的 SV 文件
//
// 定义所有模块共享的结构体类型。各模块通过 `import <pkg_name>::*;` 引入。
// 所有 struct 必须为 packed 以确保 Verilator 端口兼容性。
//==============================================================================

package <pkg_name>;

    // ── 基础子结构体 ────────────────────────────────────────────
    typedef struct packed {
        logic [15:0] field_a;
        logic [2:0]  field_b;
        logic        field_c;         // 避免使用 priority 等关键字作字段名
    } <sub_struct_a_t>;

    typedef struct packed {
        logic       enable;
        logic [3:0] level;            // 不是 priority!
    } <sub_struct_b_t>;

    // ── 嵌套结构体（场景5核心类型）──────────────────────────────
    typedef struct packed {
        <sub_struct_a_t> sub_a;       // 嵌套另一个 struct
        <sub_struct_b_t> sub_b;       // 嵌套另一个 struct
    } <main_struct_t>;

    // ── 状态结构体 ──────────────────────────────────────────────
    typedef struct packed {
        logic       flag_a;
        logic       flag_b;
        logic [1:0] status;
    } <status_struct_t>;

endpackage
```

> **注意**: package 文件在 filelist.f 中必须置于最前（在使用它的模块之前编译）。

## Struct Module — struct 端口（场景2）

```systemverilog
//==============================================================================
// Module: <module_name>
// Level:  <N>
// Parent: <parent_module>
// 场景2: 结构体例化在端口上 — 输入/输出端口使用 struct 类型
//==============================================================================

import <pkg_name>::*;    // ★ 文件作用域 import，端口声明可见

module <module_name> (
    input  logic           clk,
    input  logic           rst_n,
    input  <sub_struct_t>  cfg_i,      // ★ struct 输入端口
    output logic           tick_o
);

    // ── 使用端口 struct 字段 ────────────────────────────────────
    logic [15:0] counter;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            counter <= '0;
            tick_o  <= '0;
        end else begin
            if (counter >= cfg_i.field_a) begin   // 读取端口struct字段
                counter <= '0;
                tick_o  <= 1'b1;
            end else begin
                counter <= counter + 1;
                tick_o  <= 1'b0;
            end
        end
    end

endmodule
```

## Struct Module — 内部 struct 信号（场景1）

```systemverilog
//==============================================================================
// Module: <module_name>
// Level:  <N>
// Parent: <parent_module>
// 场景1: 结构体例化在模块内部 — 内部信号声明为 struct 类型
//==============================================================================

import <pkg_name>::*;    // ★ 文件作用域 import

module <module_name> (
    input  logic            clk,
    input  logic            rst_n,
    input  logic            wr_en,
    input  logic [31:0]     wr_data,
    output logic [31:0]     rd_data,
    output logic [<W-1>:0]  debug_o     // struct→向量 位流，C++ 校验用
);

    // ★ 场景1核心: 内部信号使用 struct 类型
    <main_struct_t>  cfg_reg;
    <status_struct_t> status_sync;

    // ── 字段级写入 ──────────────────────────────────────────────
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cfg_reg <= '0;
        end else if (wr_en) begin
            cfg_reg.sub_a.field_a <= wr_data[19:4];
            cfg_reg.sub_a.field_b <= wr_data[3:1];
            cfg_reg.sub_a.field_c <= wr_data[0];
        end
    end

    // ── 整结构体赋值输出 ────────────────────────────────────────
    assign debug_o = cfg_reg;    // 结构体→向量位流

endmodule
```

## Struct Module — 模块内 typedef struct（场景3）

```systemverilog
//==============================================================================
// Module: <module_name>
// Level:  <N>
// Parent: <parent_module>
// 场景3: 结构体定义在模块内部 — typedef struct packed {...} local_t
//        不依赖外部 package，完全在模块作用域内私有
//==============================================================================

import <pkg_name>::*;    // 仅 import 端口需要的类型（如有）

module <module_name> (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        sig_a,
    input  logic        sig_b,
    input  logic [1:0]  sig_c,
    output logic        result_o
);

    // ★ 场景3核心: 模块内部私有 typedef struct
    // 不依赖外部 package 的类型定义，完全在模块作用域内
    typedef struct packed {
        logic       sync_a;
        logic       sync_b;
        logic [1:0] sync_c;
    } local_status_t;

    local_status_t status_synced;  // 使用本模块自定义的 struct 类型

    // ── 逐字段赋值（避免 '{} 模式）────────
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            status_synced <= '0;
        end else begin
            status_synced.sync_a <= sig_a;
            status_synced.sync_b <= sig_b;
            status_synced.sync_c <= sig_c;
        end
    end

    // ── 使用局部 struct 字段 ────────────────────────────────────
    always_comb begin
        result_o = status_synced.sync_a && status_synced.sync_b;
    end

endmodule
```

## Struct Module — 嵌套 struct 字段访问（场景5）

```systemverilog
//==============================================================================
// Module: <module_name>
// Level:  <N>
// Parent: <parent_module>
// 场景5: 结构体嵌套 — 使用嵌套 struct，通过 a.b.c 二级字段访问
//==============================================================================

import <pkg_name>::*;

module <module_name> (
    input  logic           clk,
    input  logic           rst_n,
    input  <main_struct_t> full_cfg_i,   // 嵌套 struct 输入
    input  logic           req,
    output logic           grant
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            grant <= 1'b0;
        end else begin
            // ★ 场景5核心: 嵌套 struct 二级字段访问
            // full_cfg_i.sub_a.field_c  — 通过子结构体访问
            // full_cfg_i.sub_b.level    — 通过子结构体访问
            if (req && full_cfg_i.sub_a.field_c && (full_cfg_i.sub_b.level > 4'd0))
                grant <= 1'b1;
            else
                grant <= 1'b0;
        end
    end

endmodule
```

## Verilator C++ Testbench Template

```cpp
//==============================================================================
// sim_main.cpp — Verilator C++ 仿真测试台
//==============================================================================

#include "V<top_module>.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>

static int errors = 0;

#define CHECK(cond, name) do { \
    if (!(cond)) { errors++; printf("  FAIL: %s\n", name); } \
    else printf("  PASS: %s\n", name); \
} while(0)

static void toggle_clock(V<top_module>* dut, VerilatedContext* ctx) {
    static const uint64_t HALF_CYCLE = 5000;  // 5ns → 100MHz
    ctx->timeInc(HALF_CYCLE);
    dut->clk = 0; dut->eval();
    ctx->timeInc(HALF_CYCLE);
    dut->clk = 1; dut->eval();
}

static void reset(V<top_module>* dut, VerilatedContext* ctx) {
    dut->rst_n = 0;
    // 清零所有输入
    dut->wr_en = 0;
    dut->addr = 0;
    dut->wr_data = 0;
    // ... 其他输入 ...
    for (int i = 0; i < 5; i++) toggle_clock(dut, ctx);
    dut->rst_n = 1;
    toggle_clock(dut, ctx);
}

int main(int argc, char** argv) {
    VerilatedContext* ctx = new VerilatedContext;
    ctx->commandArgs(argc, argv);
    V<top_module>* dut = new V<top_module>{ctx};

    reset(dut, ctx);

    // ── Test 1: struct write/read ────────────────────────────
    // 写入 struct 字段值（按位布局拼装 wr_data）
    uint32_t write_val = (<field_a_val> << <shift_a>) |
                         (<field_b_val> << <shift_b>) |
                         (<field_c_val> << <shift_c>);
    dut->addr = 0x0;
    dut->wr_data = write_val;
    dut->wr_en = 1;
    toggle_clock(dut, ctx);
    dut->wr_en = 0;

    // 读取回校验
    toggle_clock(dut, ctx);
    CHECK(dut->debug_o == expected_bitstream,
          "S1: struct field write/read matches");

    // ── Test 2-5: 按场景依次验证 ────────────────────────────

    dut->final();
    delete dut; delete ctx;
    printf(errors ? "*** %d TESTS FAILED ***\n" : "*** ALL TESTS PASSED ***\n", errors);
    return errors ? 1 : 0;
}
```

## Makefile Template（Icarus + Verilator）

```makefile
VERILATOR ?= verilator
IVERILOG  ?= iverilog
TOP        = <top_module>
TRACE      ?= 0

.PHONY: all iv-check verilate sim trace clean

all: iv-check verilate sim

iv-check:
	@echo "=== Icarus Verilog compilation check ==="
	$(IVERILOG) -g2012 -c filelist.f -o $(TOP).vvp
	@echo "  Icarus compilation: OK"

verilate:
	@echo "=== Verilator C++ model build ==="
	$(VERILATOR) --cc --exe --build -f filelist.f sim_main.cpp \
	  --top-module $(TOP) \
	  -Wall -Wno-fatal \
	  -Wno-UNUSEDSIGNAL \
	  -Wno-UNUSEDPARAM \
	  -Wno-WIDTHEXPAND \
	  -Wno-WIDTHTRUNC \
	  $(if $(filter 1,$(TRACE)),--trace)

sim: verilate
	@echo "=== Simulation run ==="
	./obj_dir/V$(TOP)

trace: TRACE=1
trace: verilate
	@echo "=== Simulation with VCD trace ==="
	./obj_dir/V$(TOP)
	@echo "  VCD file: $(TOP).vcd (use GTKWave to view)"

clean:
	rm -rf obj_dir *.vvp *.vcd *.lxt
```

## Filelist Template（含 Package）

```
#==============================================================================
# Filelist for <design_name> — iverilog / Verilator compilation
# Module hierarchy (4 levels):
#   Level 1: <top_module>
#   Level 2: <child_a>, <child_b>, <child_c>
#   Level 3: <grandchild_a>, <grandchild_b>
#   Level 4: <great_grandchild>
#
# Struct scenarios:
#   S1: <child_a>  — 内部struct信号
#   S2: <grandchild_a> — struct端口
#   S3: <child_b>  — 模块内typedef struct
#   S4: <pkg>      — package集中定义
#   S5: <grandchild_b> — 嵌套struct字段访问
#==============================================================================

# Package (must be compiled first!)
<pkg_name>.sv

# Level 4 — Leaf leaf
<great_grandchild>.sv

# Level 3 — Grandchild
<grandchild_a>.sv
<grandchild_b>.sv

# Level 2 — Child
<child_a>.sv
<child_b>.sv
<child_c>.sv

# Level 1 — Top
<top_module>.sv
```

## Leaf Module (Level 3) — Pure Combinational

```systemverilog
//==============================================================================
// Module: <module_name>
// Level:  3 (leaf module, instantiated inside <parent_module>)
// Description: <one-line purpose>
//              Pure combinational logic, synthesis-safe.
//==============================================================================

module <module_name> (
    input  logic [7:0] a,
    input  logic [7:0] b,
    input  logic       sel,
    output logic [7:0] result,
    output logic       flag
);

    always_comb begin
        // Combinational logic here
        result = <expression>;
        flag   = <expression>;
    end

endmodule
```

## Leaf Module (Level 3) — Sequential (single register)

```systemverilog
//==============================================================================
// Module: <module_name>
// Level:  3 (leaf module, instantiated inside <parent_module>)
// Description: <one-line purpose>
//              Sequential logic with async reset, synthesis-safe.
//==============================================================================

module <module_name> (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        en,
    input  logic [7:0]  data_in,
    output logic [7:0]  data_out
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out <= 8'b0;
        end else if (en) begin
            data_out <= data_in;
        end
    end

endmodule
```

## Intermediate Module (Level 2) — Instantiates Children

```systemverilog
//==============================================================================
// Module: <module_name>
// Level:  2 (instantiated inside <top_module>)
// Description: <one-line purpose>
//              Instantiates <child_a> and <child_b> (Level 3).
//==============================================================================

module <module_name> (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  operand_a,
    input  logic [7:0]  operand_b,
    input  logic [1:0]  op,
    output logic [7:0]  result
);

    //---- Internal signals ------------------------------------------------
    logic [7:0] child_a_result;
    logic [7:0] child_b_result;
    logic       sel_int;

    //---- Child instantiation: <child_a> (Level 3) ------------------------
    <child_a> u_child_a (
        .a      (operand_a),
        .b      (operand_b),
        .result (child_a_result)
    );

    //---- Child instantiation: <child_b> (Level 3) ------------------------
    <child_b> u_child_b (
        .a      (operand_a),
        .sel    (op[0]),
        .result (child_b_result)
    );

    //---- Output mux ------------------------------------------------------
    always_comb begin
        case (op[1])
            1'b0: result = child_a_result;
            1'b1: result = child_b_result;
        endcase
    end

endmodule
```

## Top Module (Level 1) — System Integration

```systemverilog
//==============================================================================
// Module: <top_module>
// Level:  1 (top-level parent module)
// Description: <one-line purpose>
//
// Module hierarchy:
//   Level 1: <top_module>
//   Level 2: ├── <child_a>
//            ├── <child_b>
//            └── <child_c>
//   Level 3:     ├── <grandchild_a1>  (inside child_a)
//                └── <grandchild_a2>  (inside child_a)
//
// All modules use synthesis-safe SystemVerilog constructs only.
//==============================================================================

module <top_module> (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  input_a,
    input  logic [7:0]  input_b,
    input  logic [1:0]  opcode,
    input  logic        start,
    output logic [7:0]  output_data,
    output logic        done
);

    //---- Internal interconnect signals -----------------------------------
    logic [7:0] child_a_result;
    logic [7:0] child_b_result;

    //---- Submodule: <child_a> (Level 2) ----------------------------------
    <child_a> u_child_a (
        .clk       (clk),
        .rst_n     (rst_n),
        .operand_a (input_a),
        .operand_b (input_b),
        .result    (child_a_result)
    );

    //---- Submodule: <child_b> (Level 2) ----------------------------------
    <child_b> u_child_b (
        .clk    (clk),
        .rst_n  (rst_n),
        .start  (start),
        .result (child_b_result)
    );

    //---- Submodule: <child_c> (Level 2) ----------------------------------
    <child_c> u_child_c (
        .clk       (clk),
        .rst_n     (rst_n),
        .data_in   (child_a_result),
        .ctrl_in   (child_b_result),
        .data_out  (output_data),
        .done      (done)
    );

endmodule
```

## Filelist Template

```
#==============================================================================
# Filelist for <design_name> — iverilog compilation
# Module hierarchy (3 levels):
#   Level 1: <top_module>
#   Level 2: <child_a>, <child_b>, <child_c>
#   Level 3: <grandchild_a1>, <grandchild_a2>
#==============================================================================

# Level 3 — Leaf modules (must be compiled first)
<grandchild_a1>.sv
<grandchild_a2>.sv

# Level 2 — Intermediate modules
<child_a>.sv
<child_b>.sv
<child_c>.sv

# Level 1 — Top module
<top_module>.sv
```

## FSM Control Module Template

```systemverilog
//==============================================================================
// Module: <fsm_name>
// Level:  2 (instantiated inside <top_module>)
// Description: Simple FSM controller, synthesis-safe.
//==============================================================================

module <fsm_name> (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic enable,
    output logic done
);

    typedef enum logic [1:0] {
        S_IDLE    = 2'b00,
        S_ACTIVE  = 2'b01,
        S_DONE    = 2'b10
    } state_t;

    state_t state_next, state_reg;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_reg <= S_IDLE;
        end else begin
            state_reg <= state_next;
        end
    end

    always_comb begin
        state_next = state_reg;
        case (state_reg)
            S_IDLE:   if (start)  state_next = S_ACTIVE;
            S_ACTIVE:             state_next = S_DONE;
            S_DONE:   if (!start) state_next = S_IDLE;
            default:              state_next = S_IDLE;
        endcase
    end

    always_comb begin
        enable = (state_reg == S_ACTIVE);
        done   = (state_reg == S_DONE);
    end

endmodule
```
