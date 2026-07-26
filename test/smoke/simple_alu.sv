// simple_alu.sv - 简单可综合的 ALU 模块
// 用于测试 pyslang 端口扫描功能

module simple_alu (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  a,
    input  logic [7:0]  b,
    input  logic [1:0]  op,
    output logic [7:0]  result,
    output logic        zero,
    output logic        carry
);

    // 操作码定义
    localparam ADD = 2'b00;
    localparam SUB = 2'b01;
    localparam AND = 2'b10;
    localparam OR  = 2'b11;

    // 内部寄存器
    logic [8:0] add_sub_result;  // 9-bit to capture carry

    always_comb begin
        case (op)
            ADD: add_sub_result = a + b;
            SUB: add_sub_result = a - b;
            AND: result = a & b;
            OR:  result = a | b;
            default: begin
                add_sub_result = '0;
                result = '0;
            end
        endcase
    end

    assign carry = (op == ADD || op == SUB) ? add_sub_result[8] : '0;

    always_comb begin
        if (op == ADD || op == SUB)
            result = add_sub_result[7:0];
        else if (op != AND && op != OR)
            result = '0;
    end

    assign zero = (result == '0);

endmodule
