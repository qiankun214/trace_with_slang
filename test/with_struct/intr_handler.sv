//==============================================================================
// intr_handler.sv — 中断处理器（模块内部 typedef struct）
// Level: 2  (L2 child, parent=csr_system, child=irq_arbiter)
// Parent: csr_system
// 场景3: 结构体定义在模块内部 — typedef struct packed {...} intr_status_local_t
//        在模块作用域内私有定义，不依赖外部 package
//
// 功能: 接收外部标量状态信号 + irq_cfg_t 使能配置，使用模块内部定义的
//       intr_status_local_t 结构体同步状态，组合产生中断输出。
//       同时实例化 irq_arbiter (L3) 形成 2 层子模块调用。
//==============================================================================

import csr_pkg::*;

module intr_handler (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        tx_done_i,       // 发送完成（标量）
    input  logic        rx_ready_i,      // 接收就绪（标量）
    input  logic        err_i,           // 错误信号（标量）
    input  logic [1:0]  fifo_level_i,    // FIFO 水位（标量）
    input  irq_cfg_t    irq_cfg_i,       // 中断使能配置 (来自 csr_regfile)
    input  csr_cfg_t    full_cfg_i,      // 完整配置 (→ irq_arbiter，场景5)
    output logic        intr_o,          // 中断输出
    output logic        irq_grant_o      // 中断授权（来自 irq_arbiter）
);

    // ── ★ 场景3核心: 模块内部私有 typedef struct ──────────────
    // 不依赖外部 package 的类型定义，完全在模块作用域内
    typedef struct packed {
        logic       tx_done_s;           // 同步后的发送完成
        logic       rx_ready_s;          // 同步后的接收就绪
        logic       err_s;               // 同步后的错误
        logic [1:0] fifo_level_s;        // 同步后的 FIFO 水位
    } intr_status_local_t;

    // 使用模块内部自定义的 struct 类型声明信号
    intr_status_local_t status_synced;

    // ── 状态同步: 标量 → 局部结构体 ─────────────────────────────
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            status_synced <= '0;
        else
            status_synced.tx_done_s    <= tx_done_i;
            status_synced.rx_ready_s   <= rx_ready_i;
            status_synced.err_s        <= err_i;
            status_synced.fifo_level_s <= fifo_level_i;
    end

    // ── 中断生成逻辑 ────────────────────────────────────────────
    always_comb begin
        intr_o = 1'b0;
        // irq_cfg_i 使能位 & 局部 struct 状态字段
        if (irq_cfg_i.en_tx_done && status_synced.tx_done_s)
            intr_o = 1'b1;
        else if (irq_cfg_i.en_rx_done && status_synced.rx_ready_s)
            intr_o = 1'b1;
        else if (irq_cfg_i.en_err && status_synced.err_s)
            intr_o = 1'b1;
    end

    // ── L3 子模块: 中断仲裁器（嵌套 struct 字段访问，场景5）───
    irq_arbiter u_arbiter (
        .clk        (clk),
        .rst_n      (rst_n),
        .full_cfg_i (full_cfg_i),
        .irq_req    (intr_o),
        .irq_grant  (irq_grant_o)
    );

endmodule
