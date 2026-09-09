// func_call_rhs.sv — 流程② 边界场景:赋值 RHS 为函数调用,实参按读取收集
// (doc/flow2_design_spec.md §6.3)。

function automatic logic [7:0] addf(
    input logic [7:0] x,
    input logic [7:0] y
);
    return x + y;
endfunction

module func_call_top (
    input  logic [7:0] a,
    input  logic [7:0] b,
    output logic [7:0] y
);
    assign y = addf(a, b);
endmodule
