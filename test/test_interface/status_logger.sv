//==============================================================================
// Module: status_logger
// Level:  3 (leaf module, instantiated inside data_sink)
// Description: Logs processing status and generates ack/final_status.
//              Accumulates received packet count, generates ack after each
//              valid packet, and latches final status when last is received.
//              Synthesis-safe: always_ff + always_comb.
//==============================================================================

module status_logger (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        valid,
    input  logic        last,
    input  logic [3:0]  chk_status,
    input  logic        chk_error,
    output logic        ack,
    output logic [3:0]  final_status,
    output logic        error_flag
);

    //---- FSM states ---------------------------------------------------------
    typedef enum logic [1:0] {
        S_IDLE      = 2'b00,
        S_PROCESS   = 2'b01,
        S_COMPLETE  = 2'b10
    } state_t;

    state_t state_next, state_reg;

    //---- Status registers ---------------------------------------------------
    logic [3:0] final_status_next, final_status_reg;
    logic       error_flag_next,   error_flag_reg;
    logic [3:0] pkt_count_next,    pkt_count_reg;

    //---- Registers ----------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_reg        <= S_IDLE;
            final_status_reg <= 4'h0;
            error_flag_reg   <= 1'b0;
            pkt_count_reg    <= 4'd0;
        end else begin
            state_reg        <= state_next;
            final_status_reg <= final_status_next;
            error_flag_reg   <= error_flag_next;
            pkt_count_reg    <= pkt_count_next;
        end
    end

    //---- Next-state logic & output -------------------------------------------
    always_comb begin
        state_next         = state_reg;
        final_status_next  = final_status_reg;
        error_flag_next    = error_flag_reg;
        pkt_count_next     = pkt_count_reg;
        ack                = 1'b0;

        case (state_reg)
            S_IDLE: begin
                if (valid) begin
                    state_next      = S_PROCESS;
                    pkt_count_next  = pkt_count_reg + 4'd1;
                end
            end

            S_PROCESS: begin
                ack = 1'b1;  // acknowledge the received packet

                // Accumulate error
                if (chk_error) begin
                    error_flag_next = 1'b1;
                end

                if (last) begin
                    state_next        = S_COMPLETE;
                    final_status_next = chk_status;
                end else begin
                    state_next = S_IDLE;
                end
            end

            S_COMPLETE: begin
                // Hold final state until reset
                state_next = S_COMPLETE;
            end

            default: state_next = S_IDLE;
        endcase
    end

    //---- Output assignments -------------------------------------------------
    assign final_status = final_status_reg;
    assign error_flag   = error_flag_reg;

endmodule
