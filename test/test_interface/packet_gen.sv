//==============================================================================
// Module: packet_gen
// Level:  3 (leaf module, instantiated inside data_source)
// Description: Generates packet field values based on a packet ID.
//              Combinational mapping from pkt_id to data/valid/last fields.
//              Pure combinational logic, synthesis-safe.
//
// Packet sequence:
//   id=0: data=8'h10, valid=1, last=0
//   id=1: data=8'h20, valid=1, last=0
//   id=2: data=8'h30, valid=1, last=0
//   id=3: data=8'h40, valid=1, last=1  (final packet)
//   other: valid=0 (invalid)
//==============================================================================

module packet_gen (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        gen_next,
    input  logic [3:0]  pkt_id,
    output logic [7:0]  pkt_data,
    output logic        pkt_valid,
    output logic        pkt_last
);

    //---- Combinational packet generation ------------------------------------
    always_comb begin
        pkt_valid = 1'b0;
        pkt_data  = 8'h00;
        pkt_last  = 1'b0;

        case (pkt_id)
            4'd0: begin
                pkt_valid = 1'b1;
                pkt_data  = 8'h10;
                pkt_last  = 1'b0;
            end
            4'd1: begin
                pkt_valid = 1'b1;
                pkt_data  = 8'h20;
                pkt_last  = 1'b0;
            end
            4'd2: begin
                pkt_valid = 1'b1;
                pkt_data  = 8'h30;
                pkt_last  = 1'b0;
            end
            4'd3: begin
                pkt_valid = 1'b1;
                pkt_data  = 8'h40;
                pkt_last  = 1'b1;
            end
            default: begin
                pkt_valid = 1'b0;
                pkt_data  = 8'h00;
                pkt_last  = 1'b0;
            end
        endcase
    end

endmodule
