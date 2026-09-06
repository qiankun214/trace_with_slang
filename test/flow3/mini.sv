// mini.sv — 流程③ 端到端基准素材
// 与 doc/flow2_design_spec.md §1.8 示例逐行一致;经 extract_design 的产物
// 即 doc/flow3_design_spec.md §1.4 全表推演所依据的 ParseResult。
// 供 tests/test_flow3.py 固化表行/id/block_id/标志位等精确断言。

module mini (
    input  logic        clk,
    input  logic [3:0]  a,
    output logic [3:0]  y
);
    logic [3:0] b;

    assign y = a & b;                       // 块 0
    always_ff @(posedge clk) b <= a;        // 块 1
endmodule
