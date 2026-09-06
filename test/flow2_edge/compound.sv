// compound.sv — 流程② 边界场景:复合赋值(隐式读自身)
// 供 tests/test_flow2.py 验证 isCompound 自依赖边(doc/flow2_design_spec.md §6.1)。

module compound_edge (
    input  logic [7:0] b,
    output logic [7:0] q
);

    logic [7:0] acc;

    always_comb begin
        acc += b;
    end

    assign q = acc;

endmodule
