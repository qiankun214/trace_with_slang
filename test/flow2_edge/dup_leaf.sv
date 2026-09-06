// dup_leaf.sv — 流程② 边界场景:同一模块被多处实例化的叶子模块

module dup_leaf (
    input  logic a,
    output logic y
);

    assign y = a;

endmodule
