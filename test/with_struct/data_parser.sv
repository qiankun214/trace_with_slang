//==============================================================================
// Module:    data_parser
// Level:     2 (instantiated inside data_pipeline)
// Description: 数据包解析器——解析包头并提取字段，验证基本信息。
//
// struct 场景：
//   1. 外部端口使用头文件 struct — input pkt_header_t header
//   2. 模块内部定义局部 struct — parse_result_t 用于内部状态
//   3. 嵌套 struct — input pkt_ext_header_t ext_header（含 addr_t 子成员）
//
// 子模块：
//   field_extractor (Level 3) — 拆解包头字段
//   addr_compare   (Level 3) — 嵌套 struct 地址比较
//
// 功能：接收 pkt_header_t 结构体端口，例化 field_extractor 提取各字段，
//       组合逻辑检查包头有效性并生成内部 parse_result_t 结果。
//       通过 addr_compare 子模块演示嵌套 struct 字段访问。
//==============================================================================

`include "pipeline_types.svh"

module data_parser (
    input  logic        clk,
    input  logic        rst_n,
    input  pkt_header_t header,
    input  logic [31:0] payload,
    output logic [15:0] src_addr,
    output logic [15:0] dst_addr,
    output logic [7:0]  pkt_type,
    output logic [7:0]  length,
    output logic [31:0] timestamp,
    output logic [15:0] data_len,
    // 嵌套 struct 端口
    input  pkt_ext_header_t ext_header,
    output logic            addr_match
);

    //---- 模块内部定义局部 struct 类型 ---------------------------------------
    // parse_result_t 仅在 data_parser 模块内部使用，不作为端口类型
    typedef struct packed {
        logic        valid;      // 解析结果有效标志
        logic [7:0]  field_id;   // 提取字段编号
        logic [15:0] field_len;  // 字段实际长度
    } parse_result_t;

    //---- 内部信号（使用局部定义的 struct）------------------------------------
    parse_result_t parse_res_reg;   // 时序寄存器
    parse_result_t parse_res_next;  // 组合逻辑下一状态

    //---- 例化 field_extractor (Level 3) -------------------------------------
    field_extractor u_extractor (
        .header    (header),
        .src_addr  (src_addr),
        .dst_addr  (dst_addr),
        .pkt_type  (pkt_type),
        .length    (length),
        .timestamp (timestamp)
    );

    //---- 例化 addr_compare (Level 3) — 嵌套 struct 场景 --------------------
    // ext_header.src / ext_header.dst 为嵌套的 addr_t 类型
    addr_compare u_addr_compare (
        .ext_header    (ext_header),
        .same_region   (addr_match),
        .src_full_addr (),
        .dst_full_addr ()
    );

    //---- 组合逻辑：解析结果生成 ---------------------------------------------
    // 根据头文件 struct 输入的 length 字段和 payload 判断有效载荷长度
    always_comb begin
        parse_res_next = parse_res_reg;

        // 根据 packet length 和 payload 数据生成内部解析结果
        if (header.length > 8'd0 && |payload) begin
            parse_res_next.valid     = 1'b1;
            parse_res_next.field_id  = header.pkt_type;
            parse_res_next.field_len = {8'd0, header.length};
        end else begin
            parse_res_next.valid     = 1'b0;
            parse_res_next.field_id  = 8'd0;
            parse_res_next.field_len = 16'd0;
        end
    end

    //---- 时序逻辑：寄存解析结果 ---------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            parse_res_reg <= '0;
        end else begin
            parse_res_reg <= parse_res_next;
        end
    end

    //---- 输出数据长度（基于解析结果的 payload 长度）--------------------------
    assign data_len = parse_res_reg.field_len;

endmodule
