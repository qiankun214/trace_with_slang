// dup_top.sv — 流程② 边界场景:同一模块实例化两次
// 供 tests/test_flow2.py 验证每处实例化各产一条 InstanceInfo / 信号前缀
// (doc/flow2_design_spec.md §1.4 / §8)。

module dup_top (
    input  logic a1,
    input  logic a2,
    output logic y1,
    output logic y2
);

    dup_leaf u1 (
        .a(a1),
        .y(y1)
    );

    dup_leaf u2 (
        .a(a2),
        .y(y2)
    );

endmodule
