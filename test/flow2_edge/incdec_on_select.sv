// incdec_on_select.sv — 流程② 边界场景:自增/自减作用于下标选择(cntr[i]++),
// 除自依赖边外再产出下标读边(doc/flow2_design_spec.md §6.1 / §6.3)。

module incdec_sel_top (
    input  logic       clk,
    input  logic [1:0] i,
    output logic [3:0] cntr
);
    always_ff @(posedge clk) cntr[i]++;
endmodule
