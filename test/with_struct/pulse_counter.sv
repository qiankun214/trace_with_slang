//==============================================================================
// pulse_counter.sv — 脉冲计数器（纯标量叶子模块，无 struct 对照基线）
// Level: 4  (L4 leaf)
// Parent: baud_gen
//
// 对输入的 baud_tick 脉冲进行 8-bit 计数并输出。完全使用标量端口，
// 不使用任何结构体类型，作为测试套件中的对照基线。
//==============================================================================

module pulse_counter (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        tick_i,        // 脉冲输入（来自 baud_gen）
    output logic [7:0]  count_o        // 8-bit 脉冲计数
);

    // ── 脉冲计数寄存器 ──────────────────────────────────────────
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count_o <= 8'd0;
        end else if (tick_i) begin
            count_o <= count_o + 8'd1;
        end
    end

endmodule
