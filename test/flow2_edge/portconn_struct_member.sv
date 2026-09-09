// portconn_struct_member.sv — 流程② 边界场景:父侧端口连接表达式为 struct
// 字段成员(a.lo),按 §6.3 拼接规则解析(doc/flow2_design_spec.md §6.2)。

module pf_leaf (
    input  logic lo_i,
    output logic lo_o
);
endmodule

module portconn_member_top (
    input  logic d,
    output logic y
);
    typedef struct packed {
        logic lo;
        logic hi;
    } pair_t;

    pair_t cfg;

    pf_leaf u_leaf (
        .lo_i(cfg.lo),
        .lo_o(cfg.lo)
    );

    assign y = d;
endmodule
