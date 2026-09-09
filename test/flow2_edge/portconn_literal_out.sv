// portconn_literal_out.sv — 流程② 边界场景:输出端口连接表达式为不可赋值的
// 常量(结构非 Assignment)。本素材故意含编译 ERROR(slang 错误恢复后继续),
// 提取按 doc/flow2_design_spec.md §5 规则 3 完成,该连接按 §7 告警跳过。
// 注意:这是 tests/ 下唯一允许携带编译 ERROR 的输入素材。

module lit_leaf (
    output logic o_o
);
endmodule

module portconn_lit_top (
    input  logic d,
    output logic y
);
    lit_leaf u_lit (
        .o_o(1'b0)
    );

    assign y = d;
endmodule
