//==============================================================================
// Module:    data_pipeline
// Level:     1 (top-level parent module)
// Description: 数据处理流水线顶层模块
//              集成数据解析、变换、仲裁三级流水处理。
//
// Module hierarchy:
//   Level 1: data_pipeline
//   Level 2: ├── data_parser     (包头解析，struct 端口 + 内部局部 struct)
//            ├── data_transform  (数据变换，内部使用头文件 struct)
//            └── data_arbiter    (数据仲裁，struct 端口)
//   Level 3:     ├── field_extractor  (inside data_parser)
//                └── byte_swapper     (inside data_transform)
//
// struct 场景覆盖：
//   1. 内部变量使用 structure     — data_transform 中 config_word_t 寄存器
//   2. 外部端口使用 structure     — data_parser 中 pkt_header_t 端口
//   3. struct 定义在模块内部      — data_parser.parse_result_t
//                                   byte_swapper.swap_word_t
//   4. struct 统一定义在头文件    — pipeline_types.svh (pkt_header_t,
//                                   config_word_t, status_flags_t)
//
// All modules use synthesis-safe SystemVerilog constructs only.
//==============================================================================

`include "pipeline_types.svh"

module data_pipeline (
    input  logic         clk,
    input  logic         rst_n,

    //---- 数据包头部输入（struct 类型端口）------------------------------------
    input  pkt_header_t  pkt_header,

    //---- 扩展包头输入（嵌套 struct 类型端口）---------------------------------
    input  pkt_ext_header_t pkt_ext_hdr,

    //---- 原始载荷数据 -------------------------------------------------------
    input  logic [31:0]  raw_payload,

    //---- 配置输入（打包为逻辑向量，内部转为 config_word_t）-------------------
    input  logic [15:0]  config_word,

    //---- 仲裁通道 B 输入 ----------------------------------------------------
    input  logic [31:0]  alt_data,
    input  logic         alt_valid,

    //---- 输出 ---------------------------------------------------------------
    output logic [31:0]  output_data,
    output logic         addr_match,
    output status_flags_t status_out
);

    //---- 内部互联信号 -------------------------------------------------------
    // data_parser 输出
    logic [15:0] parser_src_addr;
    logic [15:0] parser_dst_addr;
    logic [7:0]  parser_pkt_type;
    logic [7:0]  parser_length;
    logic [31:0] parser_timestamp;
    logic [15:0] parser_data_len;

    // data_transform 输出
    logic [31:0] transform_data;

    // data_arbiter 内部信号
    logic        arb_channel_sel;

    //---- 子模块：data_parser (Level 2) --------------------------------------
    // 场景 2+3：pkt_header_t 端口 + 内部 parse_result_t 局部 struct
    data_parser u_parser (
        .clk        (clk),
        .rst_n      (rst_n),
        .header     (pkt_header),
        .payload    (raw_payload),
        .src_addr   (parser_src_addr),
        .dst_addr   (parser_dst_addr),
        .pkt_type   (parser_pkt_type),
        .length     (parser_length),
        .timestamp  (parser_timestamp),
        .data_len   (parser_data_len),
        .ext_header (pkt_ext_hdr),
        .addr_match (addr_match)
    );

    //---- 子模块：data_transform (Level 2) -----------------------------------
    // 场景 1：内部使用 config_word_t struct 寄存器
    data_transform u_transform (
        .clk        (clk),
        .rst_n      (rst_n),
        .raw_data   (raw_payload),
        .config_in  (config_word),
        .trans_data (transform_data)
    );

    //---- 子模块：data_arbiter (Level 2) -------------------------------------
    // 场景 2+4：output status_flags_t 端口（头文件定义）
    data_arbiter u_arbiter (
        .clk         (clk),
        .rst_n       (rst_n),
        .data_a      (transform_data),
        .data_b      (alt_data),
        .a_valid     (1'b1),             // 变换数据始终有效
        .b_valid     (alt_valid),
        .sel_data    (output_data),
        .channel_sel (arb_channel_sel),
        .flags       (status_out)
    );

endmodule
