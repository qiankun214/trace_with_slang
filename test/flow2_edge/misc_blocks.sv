// misc_blocks.sv — 流程② 边界场景:always_latch / initial / final 块类型
// 供 tests/test_flow2.py 验证 block_type 映射(doc/flow2_design_spec.md §1.6)。

module misc_blocks (
    input  logic       clk,
    input  logic       a,
    output logic [3:0] x,
    output logic [3:0] y,
    output logic [3:0] z
);

    logic [3:0] t;

    always_latch begin
        if (a) begin
            x <= t;
        end
    end

    initial begin
        y <= 4'd0;
    end

    final begin
        z = x;
    end

endmodule
