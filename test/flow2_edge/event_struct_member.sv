// event_struct_member.sv — 流程② 边界场景:时序事件列表中 struct 成员字段
// (posedge ctl.flag)作为门控条件读(doc/flow2_design_spec.md §6.1 / §5.2)。

module event_member_top (
    input  logic       clk,
    input  logic [3:0] d,
    output logic [3:0] q
);
    typedef struct packed {
        logic flag;
    } ctl_t;

    ctl_t ctl;

    always_ff @(posedge clk or posedge ctl.flag) q <= d;
endmodule
