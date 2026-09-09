// struct_array_elem.sv — 流程② 边界场景:struct 数组元素字段写(arr[idx].lo)
// 的 LHS 链底不是具名基变量,无法解析为信号行,应丢弃并 debug 记录
// (doc/flow2_design_spec.md §6.3 / §5 规则 9)。

module struct_arr_top (
    input  logic       clk,
    input  logic       d,
    input  logic [1:0] idx,
    output logic       q
);
    typedef struct packed {
        logic lo;
        logic hi;
    } pair_t;

    pair_t arr [4];

    always_ff @(posedge clk) begin
        arr[idx].lo <= d;
        q <= d;
    end
endmodule
