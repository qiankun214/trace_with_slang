//==============================================================================
// Module:    addr_compare
// Level:     3 (leaf module, instantiated inside data_parser)
// Description: 嵌套 struct 地址比较器
//              使用 pkt_ext_header_t 端口，其内部 src/dst 成员为 addr_t 类型。
//              通过嵌套字段访问语法 (ext_header.src.region) 比较地址区域。
//              纯组合逻辑。
//
// struct 场景：嵌套 struct — pkt_ext_header_t 内含 addr_t 成员
//==============================================================================

`include "pipeline_types.svh"

module addr_compare (
    input  pkt_ext_header_t ext_header,
    output logic            same_region,
    output logic [15:0]     src_full_addr,
    output logic [15:0]     dst_full_addr
);

    //---- 组合逻辑：访问嵌套 struct 子字段 ----------------------------------
    // ext_header.src 是 addr_t 类型，通过 .region / .offset 访问其子字段
    // ext_header.dst 同理
    always_comb begin
        // 比较源/目的地址的 region 字段
        if (ext_header.src.region == ext_header.dst.region) begin
            same_region = 1'b1;
        end else begin
            same_region = 1'b0;
        end

        // 将嵌套 addr_t 转换为 16-bit 全地址：{region, offset}
        src_full_addr = {ext_header.src.region, ext_header.src.offset};
        dst_full_addr = {ext_header.dst.region, ext_header.dst.offset};
    end

endmodule
