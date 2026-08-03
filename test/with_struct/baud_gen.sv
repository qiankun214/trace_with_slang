//==============================================================================
// baud_gen.sv — 波特率发生器（struct 端口）
// Level: 3  (L3 grandchild, parent=csr_regfile, child=pulse_counter)
// Parent: csr_regfile
// 场景2: 结构体例化在端口上 — 输入端口使用 baud_cfg_t packed struct
//
// 根据输入结构体 cfg_i 的 div/oversample/mode 字段生成波特率脉冲。
// 同时实例化 L4 pulse_counter 形成 3 层子模块调用链。
//==============================================================================

import csr_pkg::*;

module baud_gen (
    input  logic        clk,
    input  logic        rst_n,
    input  baud_cfg_t   cfg_i,         // ★ 场景2核心: struct 输入端口
    output logic        baud_tick_o,
    output logic [7:0]  pulse_count_o   // 来自子模块 pulse_counter
);

    // ── 内部分频计数器 ──────────────────────────────────────────
    logic [15:0] counter;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            counter     <= 16'd0;
            baud_tick_o <= 1'b0;
        end else begin
            // cfg_i.div / cfg_i.oversample / cfg_i.mode — 端口 struct 字段读取
            if (counter >= cfg_i.div) begin
                counter     <= 16'd0;
                baud_tick_o <= 1'b1;     // 产生一个周期的脉冲
            end else begin
                counter     <= counter + 16'd1;
                baud_tick_o <= 1'b0;
            end
        end
    end

    // ── L4 子模块: 脉冲计数器（形成 3 层子模块调用）───────────
    pulse_counter u_counter (
        .clk    (clk),
        .rst_n  (rst_n),
        .tick_i (baud_tick_o),
        .count_o(pulse_count_o)
    );

endmodule
