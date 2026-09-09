// concat_lhs.sv — 流程② 边界场景:拼接(Concatenation)作 LHS 时无法解析为
// 信号行,应丢弃并 debug 记录(doc/flow2_design_spec.md §6.3 / §5 规则 9)。

module concat_lhs_top (
    input  logic [7:0] d,
    output logic [7:0] q
);
    always_comb begin
        {q[3:0], q[7:4]} = {d[3:0], d[7:4]};
        q = d;
    end
endmodule
