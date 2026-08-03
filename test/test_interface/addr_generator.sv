//==============================================================================
// Module: addr_generator
// Level:  3 (leaf module, instantiated inside master)
// Description: Generates sequential addresses for bus transactions.
//              On start, begins at 8'h10 and increments by 4 on each next_addr
//              pulse. Asserts done after 4 addresses have been generated.
//              Pure sequential + combinational logic, synthesis-safe.
//==============================================================================

module addr_generator (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        start,
    input  logic        next_addr,
    output logic [7:0]  addr,
    output logic        done
);

    //---- Internal state -----------------------------------------------------
    typedef enum logic [1:0] {
        S_IDLE   = 2'b00,
        S_ACTIVE = 2'b01,
        S_DONE   = 2'b10
    } state_t;

    state_t state_next, state_reg;

    // Address counter
    logic [7:0] addr_next, addr_reg;
    logic [2:0] cnt_next, cnt_reg;  // counts 0..3 (4 addresses)

    //---- State register -----------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_reg <= S_IDLE;
            addr_reg  <= 8'h00;
            cnt_reg   <= 3'b000;
        end else begin
            state_reg <= state_next;
            addr_reg  <= addr_next;
            cnt_reg   <= cnt_next;
        end
    end

    //---- Next-state logic ---------------------------------------------------
    always_comb begin
        state_next = state_reg;
        addr_next  = addr_reg;
        cnt_next   = cnt_reg;
        done       = 1'b0;

        case (state_reg)
            S_IDLE: begin
                if (start) begin
                    state_next = S_ACTIVE;
                    addr_next  = 8'h10;
                    cnt_next   = 3'b000;
                end
            end

            S_ACTIVE: begin
                if (next_addr) begin
                    if (cnt_reg == 3'd3) begin
                        state_next = S_DONE;
                        cnt_next   = 3'b000;
                    end else begin
                        addr_next  = addr_reg + 8'h04;
                        cnt_next   = cnt_reg + 3'd1;
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

    //---- Output assignment --------------------------------------------------
    assign addr = addr_reg;

endmodule
