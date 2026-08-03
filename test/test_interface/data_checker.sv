//==============================================================================
// Module: data_checker
// Level:  3 (leaf module, instantiated inside data_sink)
// Description: Validates incoming packet data fields.
//              Checks: valid must be asserted, data must be within valid range,
//              last must only be asserted when id=3.
//              Combinational logic, synthesis-safe.
//==============================================================================

module data_checker (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  data,
    input  logic [3:0]  id,
    input  logic        valid,
    input  logic        last,
    output logic [3:0]  chk_status,
    output logic        chk_error
);

    //---- Combinational check logic ------------------------------------------
    always_comb begin
        chk_status = 4'h0;
        chk_error  = 1'b0;

        if (valid) begin
            // Data range check: expected values are 8'h10, 8'h20, 8'h30, 8'h40
            if (data != 8'h10 && data != 8'h20 && data != 8'h30 && data != 8'h40) begin
                chk_error  = 1'b1;
                chk_status = 4'h1;  // data out of range
            end

            // Last-bit check: last should only be 1 when id=3
            if (last && id != 4'd3) begin
                chk_error  = 1'b1;
                chk_status = 4'h2;  // unexpected last
            end

            // Last must be 1 when id=3 (final packet)
            if (!last && id == 4'd3) begin
                chk_error  = 1'b1;
                chk_status = 4'h3;  // missing last on final packet
            end
        end else begin
            // No packet to check
            chk_status = 4'h0;
            chk_error  = 1'b0;
        end
    end

endmodule
