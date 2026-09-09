// const_cond.sv — 流程② 边界场景:门控条件为常量(无有效信号读)时不做条件
// 广播(doc/flow2_design_spec.md §6.1 通道 2)。

module const_cond_top (
    input  logic [3:0] d,
    output logic [3:0] q
);
    always_comb begin
        if (1'b0) begin
            q = d;
        end
    end
endmodule
