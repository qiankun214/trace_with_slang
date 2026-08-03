//==============================================================================
// sim_main.cpp — Verilator C++ 仿真测试台
//
// 测试 CSR System 的 5 种结构体场景:
//   S1: 结构体实例化在模块内部 (csr_regfile 的 cfg_reg 内部信号)
//   S2: 结构体例化在端口上 (baud_gen 的 cfg_i 端口)
//   S3: 结构体定义在模块内部 (intr_handler 的 intr_status_local_t)
//   S4: 结构体定义在集中SV文件 (csr_pkg package 共享类型)
//   S5: 结构体嵌套 (irq_arbiter 访问 cfg.baud.mode / cfg.irq.prio_level)
//==============================================================================

#include "Vcsr_system.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>

static int errors = 0;

#define CHECK(cond, name) do { \
    if (!(cond)) { errors++; printf("  FAIL: %s\n", name); } \
    else printf("  PASS: %s\n", name); \
} while(0)

// 时钟半周期 (单位: ps)
static const uint64_t HALF_CYCLE = 5000; // 5ns -> 100MHz

static void toggle_clock(Vcsr_system* dut, VerilatedContext* ctx) {
    ctx->timeInc(HALF_CYCLE);
    dut->clk = 0;
    dut->eval();
    ctx->timeInc(HALF_CYCLE);
    dut->clk = 1;
    dut->eval();
}

static void reset(Vcsr_system* dut, VerilatedContext* ctx) {
    dut->rst_n = 0;
    dut->addr = 0;
    dut->wr_data = 0;
    dut->wr_en = 0;
    dut->tx_busy_i = 0;
    dut->rx_ready_i = 0;
    dut->err_i = 0;
    dut->fifo_level_i = 0;
    for (int i = 0; i < 5; i++) toggle_clock(dut, ctx);
    dut->rst_n = 1;
    toggle_clock(dut, ctx);
}

static void write_reg(Vcsr_system* dut, VerilatedContext* ctx,
                      uint8_t addr, uint32_t data) {
    dut->addr = addr;
    dut->wr_data = data;
    dut->wr_en = 1;
    toggle_clock(dut, ctx);
    dut->wr_en = 0;
    dut->addr = 0;
    dut->wr_data = 0;
    toggle_clock(dut, ctx);
}

static uint32_t read_reg(Vcsr_system* dut, VerilatedContext* ctx, uint8_t addr) {
    dut->addr = addr;
    dut->wr_en = 0;
    toggle_clock(dut, ctx);
    return dut->rd_data;
}

int main(int argc, char** argv) {
    VerilatedContext* ctx = new VerilatedContext;
    ctx->commandArgs(argc, argv);

    Vcsr_system* dut = new Vcsr_system{ctx};

    printf("=== CSR System Struct Test Suite ===\n\n");

    // ── 初始化 ──────────────────────────────────────────────────
    reset(dut, ctx);
    printf("--- Reset complete ---\n\n");

    // ═══════════════════════════════════════════════════════════════
    // 测试1: S4+S1 — package struct 类型 + 内部 struct 信号写/读
    // ═══════════════════════════════════════════════════════════════
    printf("Test 1: S4+S1 — Package struct write/read via internal cfg_reg\n");

    // 写入 baud 配置 (addr 0x0):
    //   div=100 (16'h0064), oversample=3 (3'b011), mode=1
    //   wr_data[19:4]=div, [3:1]=oversample, [0]=mode
    uint32_t baud_val = (0x0064 << 4) | (3 << 1) | 1;  // = 0x0647
    write_reg(dut, ctx, 0x0, baud_val);

    // 写入 irq 配置 (addr 0x1):
    //   en_tx_done=1, en_rx_done=0, en_err=0, prio_level=5
    //   wr_data[6]=1, [3:0]=5
    uint32_t irq_val = (1 << 6) | 5;  // = 0x45
    write_reg(dut, ctx, 0x1, irq_val);

    // 回读 addr 0x0: rd_data = {5'd0, csr_cfg_t[26:0]}
    uint32_t rd0 = read_reg(dut, ctx, 0x0);
    // csr_cfg_t = {baud_cfg_t[19:0], irq_cfg_t[6:0]} = {0x0647, 0x45}
    uint32_t expected_csr = ((baud_val & 0xFFFFF) << 7) | (irq_val & 0x7F);
    CHECK((rd0 & 0x07FFFFFF) == expected_csr,
          "S4+S1: rd_data matches csr_cfg_t = {baud, irq}");

    // cfg_debug 直接输出 csr_cfg_t 位流
    CHECK(dut->cfg_debug_o == expected_csr,
          "S4+S1: cfg_debug matches expected csr_cfg_t bitstream");

    printf("\n");

    // ═══════════════════════════════════════════════════════════════
    // 测试2: S2 — struct 端口传递，baud_gen 分频
    // ═══════════════════════════════════════════════════════════════
    printf("Test 2: S2 — baud_cfg_t struct port, baud_tick generation\n");

    // 写入 div=4 到 baud 配置，重新写字
    baud_val = (4 << 4) | (3 << 1) | 1;  // div=4, oversample=3, mode=1
    write_reg(dut, ctx, 0x0, baud_val);

    // 运行 100 个周期，统计 baud_tick 上升沿
    int tick_count = 0;
    int prev_tick = dut->baud_tick_o;
    for (int i = 0; i < 100; i++) {
        toggle_clock(dut, ctx);
        if (dut->baud_tick_o && !prev_tick) tick_count++;
        prev_tick = dut->baud_tick_o;
    }
    // div=4 → 每 5 个周期一个 tick (counter 0..4), 100 周期 ≈ 20 ticks
    CHECK(tick_count >= 15 && tick_count <= 25,
          "S2: baud_tick rate ~1/(div+1) = 1/5 (expected ~20 per 100 cycles)");

    printf("\n");

    // ═══════════════════════════════════════════════════════════════
    // 测试3: S3 — 模块内 typedef struct, 中断生成
    // ═══════════════════════════════════════════════════════════════
    printf("Test 3: S3 — Module-local typedef struct, interrupt generation\n");

    // 配置 irq: en_rx_done=1, prio_level=5
    irq_val = (0 << 6) | (1 << 5) | (0 << 4) | 5;  // en_rx_done=1
    write_reg(dut, ctx, 0x1, irq_val);

    // 驱动 rx_ready_i=1 → intr_handler 应该产生 intr_o
    dut->rx_ready_i = 1;
    toggle_clock(dut, ctx);
    toggle_clock(dut, ctx);

    CHECK(dut->intr_o == 1,
          "S3: intr_o asserted when rx_ready_i=1 and en_rx_done=1");

    // 清除 rx_ready_i，中断应该消失
    dut->rx_ready_i = 0;
    toggle_clock(dut, ctx);
    toggle_clock(dut, ctx);
    CHECK(dut->intr_o == 0,
          "S3: intr_o de-asserted when rx_ready_i=0");

    printf("\n");

    // ═══════════════════════════════════════════════════════════════
    // 测试4: S5 — 嵌套 struct 字段访问
    // ═══════════════════════════════════════════════════════════════
    printf("Test 4: S5 — Nested struct field access (cfg.baud.mode / cfg.irq.prio_level)\n");

    // 配置: mode=1 (高速), prio_level=5 (>0)
    baud_val = (4 << 4) | (3 << 1) | 1;  // div=4, mode=1
    irq_val  = (1 << 6) | 5;             // en_tx_done=1, prio_level=5
    write_reg(dut, ctx, 0x0, baud_val);
    write_reg(dut, ctx, 0x1, irq_val);

    // 触发 tx_busy_i=1 → intr_o=1 → irq_arbiter 检查 full_cfg_i.baud.mode && full_cfg_i.irq.prio_level>0
    // irq_arbiter 使用嵌套 struct: full_cfg_i.baud.mode / full_cfg_i.irq.prio_level
    dut->tx_busy_i = 1;
    toggle_clock(dut, ctx);
    toggle_clock(dut, ctx);

    // intr_o 应该被置位（tx_busy_i=1 + en_tx_done=1）
    CHECK(dut->intr_o == 1,
          "S5: intr_o via nested struct chain (baud.mode=1, irq.prio_level=5)");

    // 清除: mode=0, irq_arbiter should block irq_grant
    baud_val = (4 << 4) | (3 << 1) | 0;  // mode=0
    write_reg(dut, ctx, 0x0, baud_val);
    dut->tx_busy_i = 0;
    toggle_clock(dut, ctx);
    toggle_clock(dut, ctx);

    // intr_o 应该清零
    CHECK(dut->intr_o == 0,
          "S5: intr_o de-asserted after clearing mode and tx_busy_i");

    printf("\n");

    // ═══════════════════════════════════════════════════════════════
    // 测试5: Baseline — L4 pulse_counter + 纯标量模块
    // ═══════════════════════════════════════════════════════════════
    printf("Test 5: Baseline — L4 pulse_counter and scalar-only bus_decoder\n");

    // 恢复 baud 配置使 baud_tick 产生
    baud_val = (4 << 4) | (3 << 1) | 1;  // div=4
    write_reg(dut, ctx, 0x0, baud_val);

    // 记录 pulse_count 初始值
    uint8_t count_start = dut->pulse_count_o;
    // 运行足够的周期让 pulse_counter 计数变化
    for (int i = 0; i < 200; i++) toggle_clock(dut, ctx);
    uint8_t count_end = dut->pulse_count_o;

    CHECK(count_end > count_start,
          "Baseline: L4 pulse_counter advances with baud_tick");

    printf("\n");

    // ═══════════════════════════════════════════════════════════════
    // 结果汇总
    // ═══════════════════════════════════════════════════════════════
    dut->final();
    delete dut;
    delete ctx;

    if (errors) {
        printf("*** %d TESTS FAILED ***\n", errors);
        return 1;
    } else {
        printf("*** ALL TESTS PASSED ***\n");
        return 0;
    }
}
