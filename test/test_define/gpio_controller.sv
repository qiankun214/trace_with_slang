//==============================================================================
// Module:    gpio_controller
// Description: 可综合 GPIO 控制器模块，通过宏定义配置位宽和功能特性。
//
// 宏定义（来自 gpio_config.svh）：
//   GPIO_WIDTH         — GPIO 数据位宽
//   CLK_DIV            — 时钟分频系数
//   ENABLE_INPUT_SYNC  — 使能输入同步寄存器
//   ENABLE_INTERRUPT   — 使能中断输出
//
// 端口说明：
//   gpio_in   — GPIO 输入引脚（来自外部 IO pad）
//   gpio_out  — GPIO 输出引脚（驱动到外部 IO pad）
//   gpio_oe   — GPIO 输出使能（1 = 输出模式，0 = 输入模式）
//==============================================================================

`include "gpio_config.svh"

module gpio_controller (
    input  logic                     clk,
    input  logic                     rst_n,

    //---- GPIO 物理接口 ------------------------------------------------------
    input  logic [`GPIO_WIDTH-1:0]   gpio_in,
    output logic [`GPIO_WIDTH-1:0]   gpio_out,
    output logic [`GPIO_WIDTH-1:0]   gpio_oe,

`ifdef ENABLE_INTERRUPT
    //---- 中断输出 -----------------------------------------------------------
    output logic                     interrupt
`endif
);

    //==========================================================================
    // 内部信号定义
    //==========================================================================

    // 同步后的输入信号
    logic [`GPIO_WIDTH-1:0] gpio_in_sync;

`ifdef ENABLE_INPUT_SYNC
    // 两级同步寄存器，防止亚稳态
    logic [`GPIO_WIDTH-1:0] sync_ff1;
    logic [`GPIO_WIDTH-1:0] sync_ff2;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sync_ff1 <= '0;
            sync_ff2 <= '0;
        end else begin
            sync_ff1 <= gpio_in;
            sync_ff2 <= sync_ff1;
        end
    end

    assign gpio_in_sync = sync_ff2;
`else
    // 未使能同步时，直接连接输入
    assign gpio_in_sync = gpio_in;
`endif

    //==========================================================================
    // 输出寄存器：在时钟沿锁存输出数据和方向
    //==========================================================================

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            gpio_out <= '0;
            gpio_oe  <= '0;
        end else begin
            // 仅当对应引脚配置为输出时，才驱动输出数据
            gpio_out <= gpio_in_sync;
            gpio_oe  <= '1;  // 演示用：所有引脚固定为输出模式
        end
    end

`ifdef ENABLE_INTERRUPT
    //==========================================================================
    // 中断生成逻辑：检测输入引脚任意位变化时产生一个周期脉冲
    //==========================================================================

    logic [`GPIO_WIDTH-1:0] gpio_in_prev;
    logic                   change_detected;

    // 保存上一周期的输入值
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            gpio_in_prev <= '0;
        end else begin
            gpio_in_prev <= gpio_in_sync;
        end
    end

    // 组合逻辑检测变化
    assign change_detected = |(gpio_in_sync ^ gpio_in_prev);

    // 中断输出寄存器
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            interrupt <= '0;
        end else begin
            interrupt <= change_detected;
        end
    end
`endif

endmodule
