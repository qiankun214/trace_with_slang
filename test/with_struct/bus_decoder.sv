//==============================================================================
// bus_decoder.sv — 总线地址译码器（纯标量对照基线）
// Level: 2  (L2 child, parent=csr_system)
// Parent: csr_system
//
// 纯组合译码器，根据 addr[3:0] 和 wr_en 产生寄存器选择信号。
// 完全不使用任何 struct 类型，作为测试套件中的无 struct 对照模块。
//==============================================================================

module bus_decoder (
    input  logic [3:0]  addr,
    input  logic        wr_en,
    output logic [3:0]  reg_sel,       // 寄存器选择 (one-hot)
    output logic        reg_we         // 寄存器写使能
);

    // ── 组合地址译码 ────────────────────────────────────────────
    always_comb begin
        reg_we  = wr_en;
        case (addr)
            4'h0: reg_sel = 4'b0001;   // 波特率配置寄存器
            4'h1: reg_sel = 4'b0010;   // 中断配置寄存器
            4'h2: reg_sel = 4'b0100;   // 状态寄存器
            4'h3: reg_sel = 4'b1000;   // 保留
            default: begin
                reg_sel = 4'b0000;
                reg_we  = 1'b0;
            end
        endcase
    end

endmodule
