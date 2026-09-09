// part_sel_lhs.sv — 流程② 边界场景:LHS 部分选择写 q[3:0] <= d,选择边界
// 表达式作为读取收集(doc/flow2_design_spec.md §6.3)。

module part_sel_lhs_top (
    input  logic       clk,
    input  logic [3:0] d,
    output logic [7:0] q
);
    always_ff @(posedge clk) q[3:0] <= d;
endmodule
