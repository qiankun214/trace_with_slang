//==============================================================================
// Module: reg_file
// Level:  3 (leaf module, instantiated inside slave)
// Description: 8-bit x 256-entry register file.
//              Write: stores wdata at addr on write=1 (sequential).
//              Read:  combinational read of addr to rdata.
//              Write-priority: if write=1, rdata reflects the newly written value.
//              Synthesis-safe.
//==============================================================================

module reg_file (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        write,
    input  logic [7:0]  addr,
    input  logic [7:0]  wdata,
    output logic [7:0]  rdata
);

    //---- Register file storage ----------------------------------------------
    logic [7:0] mem [0:255];

    //---- Write operation (sequential) ---------------------------------------
    always_ff @(posedge clk) begin
        if (write) begin
            mem[addr] <= wdata;
        end
    end

    //---- Read operation (combinational) -------------------------------------
    always_comb begin
        if (write) begin
            rdata = wdata;  // write-through
        end else begin
            rdata = mem[addr];
        end
    end

endmodule
