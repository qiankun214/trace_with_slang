// loop_array.sv — 流程② 边界场景:for 循环 + 数组元素写 + 自增
// 供 tests/test_flow2.py 验证 stopExpr 门控、LHS 下标读、i++ 自依赖
// (doc/flow2_design_spec.md §5 规则 9 / §6.1 / §6.3)。

module loop_array_edge (
    input  logic        clk,
    input  logic [1:0]  n,
    input  logic        d,
    output logic [3:0]  q
);

    logic [1:0] i;

    always_ff @(posedge clk) begin
        for (i = 0; i < n; i++) begin
            q[i] <= d;
        end
    end

endmodule
