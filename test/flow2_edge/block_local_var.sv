// block_local_var.sv — 流程② 边界场景:门控分支内块局部变量(local 声明)的
// 赋值 LHS 不在信号表中,应跳过(doc/flow2_design_spec.md §5 规则 9)。

module block_local_top (
    input  logic       en,
    input  logic [3:0] a,
    output logic [3:0] y
);
    always_comb begin
        y = 4'd0;
        if (en) begin
            logic [3:0] tmp;
            tmp = a;
            y = tmp;
        end
    end
endmodule
