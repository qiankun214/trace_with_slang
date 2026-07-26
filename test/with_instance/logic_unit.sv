//==============================================================================
// Module: logic_unit
// Level:  3 (leaf module, instantiated inside alu_core)
// Description: Bitwise logic operations unit.
//              Supports AND, OR, XOR, and NOT (on operand a).
//              Pure combinational logic, synthesis-safe.
//==============================================================================

module logic_unit (
    input  logic [7:0] a,
    input  logic [7:0] b,
    input  logic [1:0] sel,     // 00: AND, 01: OR, 10: XOR, 11: NOT(a)
    output logic [7:0] result
);

    always_comb begin
        unique case (sel)
            2'b00:   result = a & b;
            2'b01:   result = a | b;
            2'b10:   result = a ^ b;
            default: result = ~a;    // sel == 2'b11
        endcase
    end

endmodule
