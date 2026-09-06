// inout_ref.sv — 流程② 边界场景:inout / ref 端口连接
// 连接表达式不在本次依赖提取范围,应告警跳过且不产 is_port_conn 边
// (doc/flow2_design_spec.md §6.2 / §7)。

module child_io (
    inout wire io
);
endmodule

module child_ref (
    ref logic x
);
endmodule

module inout_ref_top (
    inout wire io,
    input  logic a,
    output logic y
);

    logic x;

    child_io u_io (
        .io(io)
    );

    child_ref u_ref (
        .x(x)
    );

    assign y = x;

endmodule
