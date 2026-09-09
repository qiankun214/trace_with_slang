// portconn_edge_drop.sv — 流程② 边界场景:端口连接边引用的信号不在信号表中
// (输出连父侧部分选择 / 输入连未声明隐式网),应丢弃并 debug 记录
// (doc/flow2_design_spec.md §6.2 / §5 规则 9)。

module ps_leaf (
    input  logic [3:0] i_i,
    output logic [3:0] o_o
);
endmodule

module portconn_drop_ps_top (
    input  logic [3:0] d,
    output logic [3:0] y
);
    ps_leaf u_ps (
        .i_i(d),
        .o_o(y[3:0])
    );

    assign y = d;
endmodule

module in_leaf (
    input  logic a_i,
    output logic a_o
);
endmodule

module portconn_drop_in_top (
    input  logic d,
    output logic y
);
    in_leaf u_in (
        .a_i(undeclared_wire),
        .a_o(y)
    );

    assign y = d;
endmodule
