//==============================================================================
// csr_regfile.sv — CSR 配置寄存器文件
// Level: 2  (L2 child, parent=csr_system, child=baud_gen)
// Parent: csr_system
// 场景1: 结构体例化在模块内部 — 内部信号使用 struct 类型 (cfg_reg, status_sync)
// 场景2: 结构体端口 — baud_cfg_o / irq_cfg_o / csr_cfg_o 输出端口使用 struct 类型
//
// 功能: 接收 CPU 侧标量写数据，按地址译码写入内部 struct 寄存器字段；
//       输出 baud_cfg_t / irq_cfg_t / csr_cfg_t 给下游子模块；
//       整结构体 cfg_debug 输出供 C++ 测试台直接校验位流。
//==============================================================================

import csr_pkg::*;

module csr_regfile (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         wr_en,
    input  logic [3:0]   addr,
    input  logic [31:0]  wr_data,
    input  csr_status_t  status_i,       // struct 输入: 外部状态（→ internal sync）
    output baud_cfg_t    baud_cfg_o,     // struct 输出 → baud_gen (场景2)
    output irq_cfg_t     irq_cfg_o,      // struct 输出 → intr_handler
    output csr_cfg_t     csr_cfg_o,      // struct 输出: 完整配置 (→ irq_arbiter)
    output logic [31:0]  rd_data,
    output logic         rd_valid,
    output logic [26:0]  cfg_debug       // 结构体→向量位流 (C++ 校验用)
);

    // ── ★ 场景1核心: 内部信号使用 struct 类型 ──────────────────
    csr_cfg_t    cfg_reg;      // 嵌套struct寄存器 (baud_cfg_t + irq_cfg_t)
    csr_status_t status_sync;  // 同步后的状态（unpacked→packed已在上层处理）

    // ── 寄存器写逻辑: 按地址字段级写入 struct ───────────────────
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cfg_reg <= '0;
        end else if (wr_en && addr == 4'h0) begin
            // 地址 0x0: 写入波特率配置 (baud_cfg_t)
            cfg_reg.baud.div        <= wr_data[19:4];
            cfg_reg.baud.oversample <= wr_data[3:1];
            cfg_reg.baud.mode       <= wr_data[0];
        end else if (wr_en && addr == 4'h1) begin
            // 地址 0x1: 写入中断配置 (irq_cfg_t)
            cfg_reg.irq.en_tx_done <= wr_data[6];
            cfg_reg.irq.en_rx_done <= wr_data[5];
            cfg_reg.irq.en_err     <= wr_data[4];
            cfg_reg.irq.prio_level <= wr_data[3:0];
        end
    end

    // ── 状态同步 ────────────────────────────────────────────────
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            status_sync <= '0;
        else
            status_sync <= status_i;
    end

    // ── 寄存器读逻辑 ────────────────────────────────────────────
    always_comb begin
        rd_data  = 32'd0;
        rd_valid = 1'b0;
        if (!wr_en) begin
            rd_valid = 1'b1;
            case (addr)
                4'h0: rd_data = {5'd0, cfg_reg};                    // 27-bit struct → 32
                4'h1: rd_data = {25'd0, cfg_reg.irq};               // 7-bit struct → 32
                4'h2: rd_data = {27'd0, status_sync};               // 5-bit struct → 32
                default: rd_valid = 1'b0;
            endcase
        end
    end

    // ── struct 输出端口驱动 ─────────────────────────────────────
    assign baud_cfg_o = cfg_reg.baud;    // 提取子结构体 (场景2: struct端口)
    assign irq_cfg_o  = cfg_reg.irq;     // 提取子结构体
    assign csr_cfg_o  = cfg_reg;         // 完整嵌套结构体 (场景5用)

    // ── 调试输出: 结构体→向量位流，C++ 直接校验 ───────────────
    assign cfg_debug = cfg_reg;

endmodule
