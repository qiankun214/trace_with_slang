// legacy_ports.sv — 流程② 边界场景:非 ANSI 端口声明(方向声明 + 同名成员声明)
// 与模块体 parameter type 非信号符号(doc/flow2_design_spec.md §1.5)。

module legacy_top(a, y);
    input a;
    output y;
    reg y;
    parameter type T = int;

    assign y = a;
endmodule
