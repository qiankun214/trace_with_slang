//==============================================================================
// Module: sequence_ctrl
// Level:  3 (leaf module, instantiated inside data_source)
// Description: Controls the packet send sequence via FSM.
//              On start, sends pkt_id=0 through pkt_id=3 sequentially.
//              Waits for ack from sink before advancing to next packet.
//              Asserts done after all 4 packets have been acknowledged.
//              Synthesis-safe: always_ff + always_comb, no initial blocks.
//==============================================================================

module sequence_ctrl (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        start,
    input  logic        ack,
    output logic [3:0]  pkt_id,
    output logic        gen_next,
    output logic        done
);

    //---- FSM states ---------------------------------------------------------
    typedef enum logic [1:0] {
        S_IDLE    = 2'b00,
        S_SEND    = 2'b01,
        S_WAIT    = 2'b10,
        S_DONE    = 2'b11
    } state_t;

    state_t state_next, state_reg;

    //---- Packet ID counter --------------------------------------------------
    logic [3:0] id_next, id_reg;

    //---- Registers ----------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_reg <= S_IDLE;
            id_reg    <= 4'd0;
        end else begin
            state_reg <= state_next;
            id_reg    <= id_next;
        end
    end

    //---- Next-state logic ---------------------------------------------------
    always_comb begin
        state_next = state_reg;
        id_next    = id_reg;
        gen_next   = 1'b0;
        done       = 1'b0;

        case (state_reg)
            S_IDLE: begin
                if (start) begin
                    state_next = S_SEND;
                    id_next    = 4'd0;
                end
            end

            S_SEND: begin
                gen_next = 1'b1;
                state_next = S_WAIT;
            end

            S_WAIT: begin
                if (ack) begin
                    if (id_reg == 4'd3) begin
                        state_next = S_DONE;
                    end else begin
                        state_next = S_SEND;
                        id_next    = id_reg + 4'd1;
                    end
                end
            end

            S_DONE: begin
                done = 1'b1;
                if (!start) begin
                    state_next = S_IDLE;
                end
            end

            default: state_next = S_IDLE;
        endcase
    end

    //---- Output assignments -------------------------------------------------
    assign pkt_id = id_reg;

endmodule
