//==============================================================================
// main.cpp — Verilator C++ testbench for top module
//
// Drives both Subsystem A (bus_if — modport pattern) and Subsystem B
// (data_if — struct typedef pattern) and checks correctness via assertions.
//
// Build:
//   verilator --cc --build --exe --top-module top -I. <all .sv files> \
//             main.cpp -o Vtop
// Run:
//   ./Vtop
//==============================================================================

#include "Vtop.h"
#include "verilated.h"
#include "verilated_vcd_c.h"
#include <cstdio>
#include <cstdlib>

static vluint64_t sim_time = 0;

int main(int argc, char** argv) {
    //---- Verilator context & top module -------------------------------------
    VerilatedContext* ctx = new VerilatedContext;
    ctx->commandArgs(argc, argv);
    Vtop* top = new Vtop{ctx};

    //---- Waveform tracing ---------------------------------------------------
    Verilated::traceEverOn(true);
    VerilatedVcdC* tfp = new VerilatedVcdC;
    top->trace(tfp, 99);
    tfp->open("trace.vcd");

    //---- Initialize inputs --------------------------------------------------
    top->clk        = 0;
    top->rst_n      = 0;
    top->bus_start  = 0;
    top->data_start = 0;

    //---- Reset sequence (10 half-cycles with rst_n=0) -----------------------
    printf("[TB] Starting reset sequence...\n");
    for (int i = 0; i < 10; i++) {
        top->clk = !top->clk;
        top->eval();
        tfp->dump(sim_time++);
    }
    top->rst_n = 1;
    printf("[TB] Reset released at time %lu\n", sim_time);

    bool bus_pass  = false;
    bool data_pass = false;
    int  cycle     = 0;
    const int MAX_CYCLES = 500;

    //=========================================================================
    // Test Subsystem A: Bus Interface (modport pattern)
    //   - Trigger a write-then-read transaction
    //   - Expect bus_result == 8'h5A (the written value read back)
    //=========================================================================
    printf("[TB] === Test A: Bus Interface (modport) ===\n");

    // Set bus_start BEFORE clock edge so FSM samples it on posedge
    top->bus_start = 1;
    for (int tick = 0; tick < 2; tick++) {
        top->clk = !top->clk;  // tick=0: 0->1 (posedge captures start=1)
        top->eval();
        tfp->dump(sim_time++);
    }
    top->bus_start = 0;  // clear after posedge captured

    // Wait for bus_done (with timeout)
    while (!top->bus_done && cycle < MAX_CYCLES) {
        top->clk = !top->clk;
        top->eval();
        tfp->dump(sim_time++);
        cycle++;
        top->bus_start = 0;
    }

    if (top->bus_done) {
        printf("[TB] Subsystem A: bus_done asserted at cycle %d\n", cycle);
        printf("[TB] Subsystem A: bus_result = 0x%02X (expected 0x5A)\n", top->bus_result);
        if (top->bus_result == 0x5A) {
            bus_pass = true;
            printf("[TB] Subsystem A: PASS\n");
        } else {
            printf("[TB] Subsystem A: FAIL — result mismatch\n");
        }
    } else {
        printf("[TB] Subsystem A: FAIL — bus_done not asserted within %d cycles\n", MAX_CYCLES);
    }

    //=========================================================================
    // Test Subsystem B: Data Interface (struct typedef pattern)
    //   - Trigger packet sequence (4 packets: id=0..3)
    //   - Expect data_last_value == 8'h40 (last packet data)
    //   - Expect data_status_out reflects completion
    //=========================================================================
    printf("[TB] === Test B: Data Interface (struct) ===\n");

    // Set data_start BEFORE clock edge so FSM samples it on posedge
    int cycle_b = 0;
    top->data_start = 1;
    for (int tick = 0; tick < 2; tick++) {
        top->clk = !top->clk;  // tick=0: 0->1 (posedge captures start=1)
        top->eval();
        tfp->dump(sim_time++);
        cycle_b++;
    }
    top->data_start = 0;  // clear after posedge captured

    // Wait for data_done (with timeout)
    while (!top->data_done && cycle_b < MAX_CYCLES) {
        top->clk = !top->clk;
        top->eval();
        tfp->dump(sim_time++);
        cycle_b++;
        top->data_start = 0;
    }

    if (top->data_done) {
        printf("[TB] Subsystem B: data_done asserted at cycle %d\n", cycle_b);
        printf("[TB] Subsystem B: data_last_value = 0x%02X (expected 0x40)\n", top->data_last_value);
        printf("[TB] Subsystem B: data_status_out = 0x%X\n", top->data_status_out);
        if (top->data_last_value == 0x40) {
            data_pass = true;
            printf("[TB] Subsystem B: PASS\n");
        } else {
            printf("[TB] Subsystem B: FAIL — last_value mismatch\n");
        }
    } else {
        printf("[TB] Subsystem B: FAIL — data_done not asserted within %d cycles\n", MAX_CYCLES);
    }

    //=========================================================================
    // Final result
    //=========================================================================
    bool all_pass = bus_pass && data_pass;
    printf("\n[TB] ========================================\n");
    printf("[TB] Subsystem A (bus_if modport):  %s\n", bus_pass  ? "PASS" : "FAIL");
    printf("[TB] Subsystem B (data_if struct):  %s\n", data_pass ? "PASS" : "FAIL");
    printf("[TB] ========================================\n");
    printf("[TB] %s\n", all_pass ? "ALL TESTS PASSED" : "TEST FAILED");

    //---- Cleanup ------------------------------------------------------------
    top->final();
    tfp->close();
    delete top;
    delete tfp;
    delete ctx;

    return all_pass ? 0 : 1;
}
