//==============================================================================
// Module:    field_extractor
// Level:     3 (leaf module, instantiated inside data_parser)
// Description: 从 pkt_header_t 结构体中提取各字段输出
//              纯组合逻辑，使用头文件中定义的 struct 类型作为输入端口。
//
// struct 场景：外部端口使用头文件 struct（pkt_header_t）
//==============================================================================

`include "pipeline_types.svh"

module field_extractor (
    input  pkt_header_t header,
    output logic [15:0] src_addr,
    output logic [15:0] dst_addr,
    output logic [7:0]  pkt_type,
    output logic [7:0]  length,
    output logic [31:0] timestamp
);

    //---- 组合逻辑：结构体字段拆解 -------------------------------------------
    always_comb begin
        src_addr  = header.src_addr;
        dst_addr  = header.dst_addr;
        pkt_type  = header.pkt_type;
        length    = header.length;
        timestamp = header.timestamp;
    end

endmodule
