//==============================================================================
// Module: alu_core
// Level:  2 (instantiated inside alu_system)
// Description: ALU core — instantiates adder_8bit and logic_unit, then selects
//              output based on the opcode.
//              Demonstrates 2-level hierarchy (alu_core → adder_8bit / logic_unit).
//==============================================================================

module alu_core (
    input  logic [7:0] operand_a,
    input  logic [7:0] operand_b,
    input  logic [2:0] opcode,      // 000: ADD, 001: SUB, 010: AND, 011: OR, 100: XOR, 101: NOT
    output logic [7:0] result,
    output logic       carry
);

    //---- Internal signals ------------------------------------------------
    logic [7:0] add_sum;
    logic       add_cout;
    logic [7:0] add_b_mux;           // b or ~b for subtraction
    logic       add_cin;             // 0 for ADD, 1 for SUB (as +1 for 2's complement)

    logic [1:0] logic_sel;
    logic [7:0] logic_result;

    //---- Adder input mux (handle SUB via 2's complement) -----------------
    always_comb begin
        if (opcode == 3'b001) begin          // SUB: a + (~b) + 1
            add_b_mux = ~operand_b;
            add_cin   = 1'b1;
        end else begin                        // ADD or other
            add_b_mux = operand_b;
            add_cin   = 1'b0;
        end
    end

    //---- Logic unit opcode mapping ---------------------------------------
    // Map ALU opcode bits [1:0] directly to logic_unit sel
    assign logic_sel = opcode[1:0];

    //---- Submodule instantiation: adder_8bit (Level 3) -------------------
    adder_8bit u_adder (
        .a   (operand_a),
        .b   (add_b_mux),
        .cin (add_cin),
        .sum (add_sum),
        .cout(add_cout)
    );

    //---- Submodule instantiation: logic_unit (Level 3) -------------------
    logic_unit u_logic (
        .a      (operand_a),
        .b      (operand_b),
        .sel    (logic_sel),
        .result (logic_result)
    );

    //---- Output mux: select between adder and logic results --------------
    always_comb begin
        carry = 1'b0;
        case (opcode)
            3'b000, 3'b001: begin              // ADD, SUB
                result = add_sum;
                carry  = add_cout;
            end
            3'b010, 3'b011, 3'b100, 3'b101: begin  // AND, OR, XOR, NOT
                result = logic_result;
            end
            default: begin
                result = 8'b0;
            end
        endcase
    end

endmodule
