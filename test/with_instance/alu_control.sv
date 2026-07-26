//==============================================================================
// Module: alu_control
// Level:  2 (instantiated inside alu_system)
// Description: Simple FSM controller for the ALU system.
//              Manages IDLE → COMPUTE → DONE state transitions.
//              Synthesis-safe: uses enum for state, always_ff + always_comb.
//==============================================================================

module alu_control (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic compute_en,
    output logic done
);

    //---- FSM state encoding ----------------------------------------------
    typedef enum logic [1:0] {
        S_IDLE    = 2'b00,
        S_COMPUTE = 2'b01,
        S_DONE    = 2'b10
    } state_t;

    state_t state_next, state_reg;

    //---- State register --------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_reg <= S_IDLE;
        end else begin
            state_reg <= state_next;
        end
    end

    //---- Next-state logic ------------------------------------------------
    always_comb begin
        state_next = state_reg;
        case (state_reg)
            S_IDLE: begin
                if (start) begin
                    state_next = S_COMPUTE;
                end
            end
            S_COMPUTE: begin
                state_next = S_DONE;
            end
            S_DONE: begin
                if (!start) begin
                    state_next = S_IDLE;
                end
            end
            default: begin
                state_next = S_IDLE;
            end
        endcase
    end

    //---- Output logic ----------------------------------------------------
    always_comb begin
        compute_en = 1'b0;
        done       = 1'b0;
        case (state_reg)
            S_COMPUTE: begin
                compute_en = 1'b1;
            end
            S_DONE: begin
                done = 1'b1;
            end
            default: begin
                compute_en = 1'b0;
                done       = 1'b0;
            end
        endcase
    end

endmodule
