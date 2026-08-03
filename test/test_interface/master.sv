//==============================================================================
// Module: master
// Level:  2 (instantiated inside top, connected via bus_if.master modport)
// Description: Bus master module that performs a write-then-read transaction
//              over the bus_if interface. Internally instantiates two level-3
//              submodules: addr_generator and data_buffer.
//
// Hierarchy:
//   master (Level 2)
//   ├── u_addr_gen (addr_generator, Level 3)
//   └── u_data_buf (data_buffer,   Level 3)
//
// Transaction flow:
//   1. On start, load write data into buffer and generate target address
//   2. Write phase: drive bus.write=1 with addr + wdata, wait for ready
//   3. Read phase:  drive bus.read=1 with same addr, wait for ready, capture rdata
//   4. Assert done, output the read-back data as result
//==============================================================================

module master (
    bus_if.master bus,
    input  logic       start,
    output logic       done,
    output logic [7:0] result
);

    //---- FSM states ---------------------------------------------------------
    typedef enum logic [2:0] {
        S_IDLE    = 3'b000,
        S_SETUP   = 3'b001,
        S_WRITE   = 3'b010,
        S_READ    = 3'b011,
        S_DONE    = 3'b100
    } state_t;

    state_t state_next, state_reg;

    //---- Internal interconnect signals --------------------------------------
    logic       addr_gen_start;
    logic       addr_gen_next;
    logic [7:0] addr_gen_addr;
    logic       addr_gen_done;

    logic       buf_load;
    logic [7:0] buf_data_in;
    logic [7:0] buf_data_out;

    //---- State register -----------------------------------------------------
    always_ff @(posedge bus.clk or negedge bus.rst_n) begin
        if (!bus.rst_n) begin
            state_reg <= S_IDLE;
        end else begin
            state_reg <= state_next;
        end
    end

    //---- Next-state logic & bus output --------------------------------------
    always_comb begin
        state_next     = state_reg;
        bus.addr       = 8'h00;
        bus.wdata      = 8'h00;
        bus.write      = 1'b0;
        bus.read       = 1'b0;
        done           = 1'b0;
        addr_gen_start = 1'b0;
        addr_gen_next  = 1'b0;
        buf_load       = 1'b0;
        buf_data_in    = 8'h00;

        case (state_reg)
            S_IDLE: begin
                if (start) begin
                    state_next     = S_SETUP;
                    addr_gen_start = 1'b1;
                    buf_load       = 1'b1;
                    buf_data_in    = 8'h5A;  // test write pattern
                end
            end

            S_SETUP: begin
                // Wait one cycle for addr_gen and data_buf registers to update
                state_next = S_WRITE;
            end

            S_WRITE: begin
                bus.addr  = addr_gen_addr;
                bus.wdata = buf_data_out;
                bus.write = 1'b1;
                if (bus.ready) begin
                    state_next = S_READ;
                    // Note: do NOT advance addr_gen here — read from same addr
                end
            end

            S_READ: begin
                bus.addr = addr_gen_addr;
                bus.read = 1'b1;
                if (bus.ready) begin
                    state_next = S_DONE;
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

    //---- Output assignment: capture rdata on read completion ----------------
    logic [7:0] result_reg;

    always_ff @(posedge bus.clk or negedge bus.rst_n) begin
        if (!bus.rst_n) begin
            result_reg <= 8'h00;
        end else if (state_reg == S_READ && bus.ready) begin
            result_reg <= bus.rdata;
        end
    end

    assign result = result_reg;

    //---- Submodule: addr_generator (Level 3) --------------------------------
    addr_generator u_addr_gen (
        .clk       (bus.clk),
        .rst_n     (bus.rst_n),
        .start     (addr_gen_start),
        .next_addr (addr_gen_next),
        .addr      (addr_gen_addr),
        .done      (addr_gen_done)
    );

    //---- Submodule: data_buffer (Level 3) -----------------------------------
    data_buffer u_data_buf (
        .clk      (bus.clk),
        .rst_n    (bus.rst_n),
        .load     (buf_load),
        .data_in  (buf_data_in),
        .data_out (buf_data_out)
    );

endmodule
