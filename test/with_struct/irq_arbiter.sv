//==============================================================================
// irq_arbiter.sv — 中断仲裁器（嵌套结构体字段访问）
// Level: 3  (L3 grandchild, parent=intr_handler)
// Parent: intr_handler
// 场景5: 结构体嵌套 — 使用 csr_cfg_t (内含 baud_cfg_t + irq_cfg_t)，
//         通过 full_cfg_i.baud.mode / full_cfg_i.irq.prio_level 二级字段访问
//
// 当 irq_req 有效且 full_cfg_i.baud.mode=1 (高速模式) 且中断优先级 > 0
// 时，授予中断请求 (irq_grant=1)。
//==============================================================================

import csr_pkg::*;

module irq_arbiter (
    input  logic      clk,
    input  logic      rst_n,
    input  csr_cfg_t  full_cfg_i,     // ★ 场景5核心: 嵌套 struct 输入 (含 baud + irq)
    input  logic      irq_req,        // 中断请求
    output logic      irq_grant       // 中断授权
);

    // ── 仲裁逻辑 ────────────────────────────────────────────────
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            irq_grant <= 1'b0;
        end else begin
            // ★ 场景5核心: 嵌套 struct 字段访问
            // full_cfg_i.baud.mode      — 二级字段: 通过 baud 子结构体访问 mode
            // full_cfg_i.irq.prio_level — 二级字段: 通过 irq 子结构体访问 prio_level
            if (irq_req && full_cfg_i.baud.mode && (full_cfg_i.irq.prio_level > 4'd0))
                irq_grant <= 1'b1;
            else
                irq_grant <= 1'b0;
        end
    end

endmodule
