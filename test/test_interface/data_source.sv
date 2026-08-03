//==============================================================================
// Module: data_source
// Level:  2 (instantiated inside top, connected via data_if.source modport)
// Description: Data source module that generates packet sequences and sends
//              them through the data_if interface. Internally instantiates
//              two level-3 submodules: packet_gen and sequence_ctrl.
//
// Hierarchy:
//   data_source (Level 2)
//   ├── u_pkt_gen  (packet_gen,    Level 3)
//   └── u_seq_ctrl (sequence_ctrl, Level 3)
//
// Key design: this module bridges between the interface's structured types
// (packet_t, status_t) and the traditional-port Level 3 submodules.
// Submodule output signals are assembled into the packet_t struct fields;
// the status_t struct field (ack) feeds back into the sequence controller.
//==============================================================================

module data_source (
    data_if.source  bus,
    input  logic        start,
    output logic        done,
    output logic [7:0]  last_data,
    output logic [3:0]  status_code,
    output logic        error_out
);

    //---- Internal interconnect signals --------------------------------------
    logic        seq_gen_next;
    logic [3:0]  seq_pkt_id;
    logic        seq_done;

    logic [7:0]  gen_data;
    logic        gen_valid;
    logic        gen_last;

    logic        sink_ack;

    //---- FSM to coordinate submodule operation ------------------------------
    typedef enum logic [1:0] {
        S_IDLE  = 2'b00,
        S_RUN   = 2'b01,
        S_DONE  = 2'b10
    } state_t;

    state_t state_next, state_reg;

    //---- State register -----------------------------------------------------
    always_ff @(posedge bus.clk or negedge bus.rst_n) begin
        if (!bus.rst_n) begin
            state_reg <= S_IDLE;
        end else begin
            state_reg <= state_next;
        end
    end

    //---- State control ------------------------------------------------------
    always_comb begin
        state_next = state_reg;
        done       = 1'b0;

        case (state_reg)
            S_IDLE: begin
                if (start) begin
                    state_next = S_RUN;
                end
            end

            S_RUN: begin
                if (seq_done) begin
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

    //---- Extract ack from interface status struct ---------------------------
    assign sink_ack = bus.status.ack;

    //---- Assemble interface packet struct from submodule outputs -------------
    assign bus.packet.data  = gen_data;
    assign bus.packet.id    = seq_pkt_id;
    assign bus.packet.valid = gen_valid;
    assign bus.packet.last  = gen_last;

    //---- Output assignments (captured values from last packet) --------------
    assign last_data   = gen_data;
    assign status_code = bus.status.status;
    assign error_out   = bus.status.error;

    //---- Submodule: sequence_ctrl (Level 3) ---------------------------------
    sequence_ctrl u_seq_ctrl (
        .clk      (bus.clk),
        .rst_n    (bus.rst_n),
        .start    (start),
        .ack      (sink_ack),
        .pkt_id   (seq_pkt_id),
        .gen_next (seq_gen_next),
        .done     (seq_done)
    );

    //---- Submodule: packet_gen (Level 3) ------------------------------------
    packet_gen u_pkt_gen (
        .clk       (bus.clk),
        .rst_n     (bus.rst_n),
        .gen_next  (seq_gen_next),
        .pkt_id    (seq_pkt_id),
        .pkt_data  (gen_data),
        .pkt_valid (gen_valid),
        .pkt_last  (gen_last)
    );

endmodule
