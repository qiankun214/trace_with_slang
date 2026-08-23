//==============================================================================
// Module:    data_transform
// Level:     2 (instantiated inside data_pipeline)
// Description: 数据变换模块——根据配置控制字对载荷数据进行字节序变换和掩码处理。
//
// struct 场景：内部变量使用头文件 struct — config_word_t 用于内部寄存器
//
// 子模块：
//   byte_swapper (Level 3) — 4 字节大小端交换
//
// 功能：内部使用 config_word_t 结构体寄存器存储配置，
//       根据 mode 字段选择直通/交换/掩码操作。
//==============================================================================

`include "pipeline_types.svh"

module data_transform (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [31:0]  raw_data,
    input  logic [15:0]  config_in,  // 外部输入，内部转为 config_word_t
    output logic [31:0]  trans_data
);

    //---- 内部变量：使用头文件 struct 类型 -----------------------------------
    // 场景 1：内部变量使用 structure（来自头文件的 config_word_t）
    config_word_t cfg_reg;      // 配置寄存器
    config_word_t cfg_next;     // 配置下一状态

    //---- 字节交换相关信号 ---------------------------------------------------
    logic [31:0] swapped_data;

    //---- 例化 byte_swapper (Level 3) ----------------------------------------
    // byte_swapper 内部自行定义了 swap_word_t 局部 struct
    byte_swapper u_swapper (
        .word_in  (raw_data),
        .word_out (swapped_data)
    );

    //---- 组合逻辑：配置字解析 -----------------------------------------------
    // 将外部 config_in 转为内部 config_word_t struct
    always_comb begin
        cfg_next = config_word_t'(config_in);
    end

    //---- 时序逻辑：配置寄存器 -----------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cfg_reg <= '0;
        end else begin
            cfg_reg <= cfg_next;
        end
    end

    //---- 组合逻辑：数据处理 ------------------------------------------------
    // 根据 config_word_t 的各字段（mode, bypass, mask）决定输出
    always_comb begin
        if (cfg_reg.bypass) begin
            // 旁路模式：直接输出原始数据
            trans_data = raw_data;
        end else begin
            unique case (cfg_reg.mode)
                2'b00: begin
                    // 直通模式：原始数据直接输出
                    trans_data = raw_data;
                end
                2'b01: begin
                    // 字节交换模式：使用 byte_swapper 输出
                    trans_data = swapped_data;
                end
                2'b10: begin
                    // 掩码模式：用 mask 字段对数据做位掩码
                    trans_data = raw_data & {4{cfg_reg.mask}};
                end
                default: begin
                    // 保留模式：直通
                    trans_data = raw_data;
                end
            endcase
        end
    end

endmodule
