//==============================================================================
// Module:    data_arbiter
// Level:     2 (instantiated inside data_pipeline)
// Description: 数据仲裁器——两路输入优先级仲裁，产生状态标志输出。
//
// struct 场景：外部端口使用头文件 struct — output status_flags_t flags
//
// 功能：根据两路输入数据的比较结果和仲裁逻辑，
//       使用头文件定义的 status_flags_t 结构体输出状态标志。
//==============================================================================

`include "pipeline_types.svh"

module data_arbiter (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [31:0]  data_a,    // 高优先级通道
    input  logic [31:0]  data_b,    // 低优先级通道
    input  logic         a_valid,
    input  logic         b_valid,
    output logic [31:0]  sel_data,
    output logic         channel_sel,   // 0=A 1=B
    output status_flags_t flags
);

    //---- 内部信号 -----------------------------------------------------------
    status_flags_t flags_next;  // 组合逻辑下一状态

    //---- 仲裁逻辑 -----------------------------------------------------------
    always_comb begin
        // 优先级仲裁：A > B
        if (a_valid) begin
            sel_data    = data_a;
            channel_sel = 1'b0;
        end else if (b_valid) begin
            sel_data    = data_b;
            channel_sel = 1'b1;
        end else begin
            sel_data    = 32'd0;
            channel_sel = 1'b0;
        end
    end

    //---- 组合逻辑：状态标志生成 ---------------------------------------------
    always_comb begin
        flags_next = status_flags_t'('0);

        // 溢出检测：两路同时有效时设置溢出
        if (a_valid && b_valid) begin
            flags_next.overflow = 1'b1;
        end

        // 奇偶校验：对选中数据做奇偶校验（简化为 bit[0] 检测）
        flags_next.parity_err = sel_data[0];

        // CRC 错误：模拟 CRC 校验（如果数据全零则标记 CRC 错误）
        if (data_a == 32'd0 && data_b == 32'd0) begin
            flags_next.crc_err = 1'b1;
        end

        // 优先级：根据两通道有效状态编码
        flags_next.prio_level = {2'b0, a_valid, b_valid, 1'b0};
    end

    //---- 时序逻辑：状态标志输出寄存器 ---------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            flags <= '0;
        end else begin
            flags <= flags_next;
        end
    end

endmodule
