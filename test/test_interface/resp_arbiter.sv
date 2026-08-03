//==============================================================================
// Module: resp_arbiter
// Level:  3 (leaf module, instantiated inside slave)
// Description: Simplified response arbiter for bus transactions.
//              Ready is asserted one cycle after write or read request.
//              rdata_out passes through rdata_raw directly.
//              Synthesis-safe.
//==============================================================================

module resp_arbiter (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        write,
    input  logic        read,
    input  logic [7:0]  rdata_raw,
    output logic [7:0]  rdata_out,
    output logic        ready
);

    //---- Ready pipeline: assert ready one cycle after request ----------------
    logic req_d1;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            req_d1 <= 1'b0;
        end else begin
            req_d1 <= write || read;
        end
    end

    assign ready = req_d1;

    //---- Pass rdata through directly ----------------------------------------
    assign rdata_out = rdata_raw;

endmodule
