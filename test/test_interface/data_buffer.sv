//==============================================================================
// Module: data_buffer
// Level:  3 (leaf module, instantiated inside master)
// Description: Write-data buffer that latches input data on load pulse.
//              Holds and continuously drives the latched value.
//              Pure sequential logic, synthesis-safe.
//==============================================================================

module data_buffer (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        load,
    input  logic [7:0]  data_in,
    output logic [7:0]  data_out
);

    //---- Data register ------------------------------------------------------
    logic [7:0] data_reg;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_reg <= 8'h00;
        end else if (load) begin
            data_reg <= data_in;
        end
    end

    assign data_out = data_reg;

endmodule
