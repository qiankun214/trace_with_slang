//==============================================================================
// Module: alu_system
// Level:  1 (top-level parent module)
// Description: Top-level ALU system that instantiates three Level-2 submodules:
//              alu_core, alu_control, and result_stage.
//
// Module hierarchy (3 levels total):
//   Level 1: alu_system (this file)
//   Level 2: ├── alu_core
//            ├── alu_control
//            └── result_stage
//   Level 3:     ├── adder_8bit  (inside alu_core)
//                └── logic_unit  (inside alu_core)
//
// All modules use synthesis-safe SystemVerilog constructs only.
//==============================================================================

module alu_system (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  operand_a,
    input  logic [7:0]  operand_b,
    input  logic [2:0]  opcode,
    input  logic        start,
    output logic [7:0]  result,
    output logic        carry,
    output logic        done
);

    //---- Internal interconnect signals -----------------------------------
    logic        compute_en;
    logic        done_int;
    logic [7:0]  core_result;
    logic        core_carry;

    //---- Submodule: alu_control (Level 2) --------------------------------
    alu_control u_control (
        .clk        (clk),
        .rst_n      (rst_n),
        .start      (start),
        .compute_en (compute_en),
        .done       (done_int)
    );

    //---- Submodule: alu_core (Level 2) -----------------------------------
    // Internally instantiates adder_8bit and logic_unit (Level 3)
    alu_core u_core (
        .operand_a (operand_a),
        .operand_b (operand_b),
        .opcode    (opcode),
        .result    (core_result),
        .carry     (core_carry)
    );

    //---- Submodule: result_stage (Level 2) -------------------------------
    result_stage u_result (
        .clk       (clk),
        .rst_n     (rst_n),
        .en        (compute_en),
        .data_in   (core_result),
        .carry_in  (core_carry),
        .data_out  (result),
        .carry_out (carry)
    );

    //---- Output assignment -----------------------------------------------
    assign done = done_int;

endmodule
