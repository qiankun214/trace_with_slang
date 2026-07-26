//==============================================================================
// Module: result_stage
// Level:  2 (instantiated inside alu_system)
// Description: Pipeline register stage for latching ALU computation results.
//              Latches result and carry on compute_en assertion.
//              Synthesis-safe: pure always_ff register with async reset.
//==============================================================================

module result_stage (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        en,
    input  logic [7:0]  data_in,
    input  logic        carry_in,
    output logic [7:0]  data_out,
    output logic        carry_out
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out  <= 8'b0;
            carry_out <= 1'b0;
        end else if (en) begin
            data_out  <= data_in;
            carry_out <= carry_in;
        end
    end

endmodule
