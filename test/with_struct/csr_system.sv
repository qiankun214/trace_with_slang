//==============================================================================
// csr_system.sv — CSR 配置寄存器系统顶层
// Level: 1  (L1 top module)
//
// 顶层模块，集成所有子模块形成完整的 CSR 配置与中断控制系统。
// 端口全部为标量类型，方便 C++ 测试台直接驱动。内部将标量输入打包为
// struct 后连接各子模块。
//
// 子模块调用层次:
//   csr_system (L1)
//   ├── csr_regfile u_regfile (L2)     [场景1: 内部struct信号]
//   │   └── baud_gen u_baud (L3)       [场景2: struct端口]
//   │       └── pulse_counter u_counter (L4)  [对照基线]
//   ├── bus_decoder u_decode (L2)      [纯标量对照]
//   └── intr_handler u_intr (L2)       [场景3: 模块内typedef struct]
//       └── irq_arbiter u_arbiter (L3) [场景5: 嵌套struct]
//
// 3层子模块调用路径: csr_system.u_regfile.u_baud.u_counter
//==============================================================================

import csr_pkg::*;

module csr_system (
    input  logic        clk,
    input  logic        rst_n,

    // ── CPU 总线接口 (标量) ─────────────────────────────────────
    input  logic [3:0]  addr,
    input  logic [31:0] wr_data,
    input  logic        wr_en,

    // ── 外部状态输入 (标量) ─────────────────────────────────────
    input  logic        tx_busy_i,
    input  logic        rx_ready_i,
    input  logic        err_i,
    input  logic [1:0]  fifo_level_i,

    // ── 系统输出 (标量) ─────────────────────────────────────────
    output logic        baud_tick_o,
    output logic        intr_o,
    output logic [31:0] rd_data,
    output logic        rd_valid,
    output logic [26:0] cfg_debug_o,     // struct→向量 位流（C++ 校验）
    output logic [7:0]  pulse_count_o     // L4 pulse_counter 输出
);

    // ── 内部 struct 信号 ────────────────────────────────────────
    csr_status_t status_pack;      // 标量→struct 打包
    baud_cfg_t   baud_cfg_wire;    // csr_regfile → baud_gen
    irq_cfg_t    irq_cfg_wire;     // csr_regfile → intr_handler
    csr_cfg_t    csr_cfg_wire;     // csr_regfile → intr_handler → irq_arbiter (嵌套struct)

    // ── 标量 → struct 打包 ─────────────────────────────────────
    assign status_pack.tx_busy    = tx_busy_i;
    assign status_pack.rx_ready   = rx_ready_i;
    assign status_pack.fifo_level = fifo_level_i;
    assign status_pack.parity_err = err_i;

    // ── L2: CSR 寄存器文件 ─────────────────────────────────────
    csr_regfile u_regfile (
        .clk        (clk),
        .rst_n      (rst_n),
        .wr_en      (wr_en),
        .addr       (addr),
        .wr_data    (wr_data),
        .status_i   (status_pack),
        .baud_cfg_o (baud_cfg_wire),
        .irq_cfg_o  (irq_cfg_wire),
        .csr_cfg_o  (csr_cfg_wire),
        .rd_data    (rd_data),
        .rd_valid   (rd_valid),
        .cfg_debug  (cfg_debug_o)
    );

    // ── L3: 波特率发生器 (struct 端口, 场景2) ─────────────────
    //      内含 L4 pulse_counter，形成 3 层子模块调用
    baud_gen u_baud (
        .clk           (clk),
        .rst_n         (rst_n),
        .cfg_i         (baud_cfg_wire),
        .baud_tick_o   (baud_tick_o),
        .pulse_count_o (pulse_count_o)
    );

    // ── L2: 总线译码器 (纯标量对照) ────────────────────────────
    bus_decoder u_decode (
        .addr    (addr),
        .wr_en   (wr_en),
        .reg_sel (),
        .reg_we  ()
    );

    // ── L2: 中断处理器 (模块内 typedef struct, 场景3) ─────────
    //      内含 L3 irq_arbiter (嵌套 struct, 场景5)
    intr_handler u_intr (
        .clk         (clk),
        .rst_n       (rst_n),
        .tx_done_i   (tx_busy_i),       // 映射: tx_busy_i → 发送状态
        .rx_ready_i  (rx_ready_i),
        .err_i       (err_i),
        .fifo_level_i(fifo_level_i),
        .irq_cfg_i   (irq_cfg_wire),
        .full_cfg_i  (csr_cfg_wire),    // 嵌套struct 传递到 irq_arbiter
        .intr_o      (intr_o),
        .irq_grant_o ()                  // 未连接到此顶层端口
    );

endmodule
