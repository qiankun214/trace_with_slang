// local_loop.sv — 流程② 边界场景:循环变量为过程块局部声明
// 循环变量 k 不在信号表中,依赖边应被 debug 丢弃
// (doc/flow2_design_spec.md §5 规则 9)。

module local_loop_edge (
    input  logic        clk,
    input  logic [1:0]  n,
    input  logic        d,
    output logic [3:0]  q
);

    always_ff @(posedge clk) begin
        for (int k = 0; k < n; k++) begin
            q[k] <= d;
        end
    end

endmodule
