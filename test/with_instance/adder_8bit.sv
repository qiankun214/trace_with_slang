//==============================================================================
// Module: adder_8bit
// Level:  3 (leaf module, instantiated inside alu_core)
// Description: 8-bit full adder with carry-in and carry-out.
//              Pure combinational logic, synthesis-safe.
//==============================================================================

module adder_8bit (
    input  logic [7:0] a,
    input  logic [7:0] b,
    input  logic       cin,
    output logic [7:0] sum,
    output logic       cout
);

    // Internal carry chain: 9 bits to hold {cout, sum} concatenated
    logic [8:0] result;

    always_comb begin
        result = {1'b0, a} + {1'b0, b} + {7'b0, cin};
    end

    assign sum  = result[7:0];
    assign cout = result[8];

endmodule
