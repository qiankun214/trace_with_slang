//==============================================================================
// Module: top
// Level:  1 (top-level integration module)
// Description: Top-level module that demonstrates two SystemVerilog interface
//              usage patterns in a single design:
//
//   Subsystem A (bus_if):  Interface for port connections via modports.
//                          A master performs write-then-read transactions
//                          to a slave through the bus_if interface.
//
//   Subsystem B (data_if): Interface containing typedef struct packed types.
//                          A data source sends structured packets to a sink,
//                          which validates them and returns status responses.
//
// Module hierarchy (3 levels total):
//   Level 1: top (this file)
//   Level 2: ├── u_master  (master.sv)
//            ├── u_slave   (slave.sv)
//            ├── u_source  (data_source.sv)
//            └── u_sink    (data_sink.sv)
//   Level 3:     ├── u_addr_gen  (addr_generator.sv)  — inside master
//                ├── u_data_buf  (data_buffer.sv)      — inside master
//                ├── u_regfile   (reg_file.sv)          — inside slave
//                ├── u_arbiter   (resp_arbiter.sv)      — inside slave
//                ├── u_pkt_gen   (packet_gen.sv)        — inside data_source
//                ├── u_seq_ctrl  (sequence_ctrl.sv)     — inside data_source
//                ├── u_checker   (data_checker.sv)      — inside data_sink
//                └── u_logger    (status_logger.sv)     — inside data_sink
//
// All modules use synthesis-safe SystemVerilog constructs only.
//==============================================================================

module top (
    input  logic        clk,
    input  logic        rst_n,
    //---- Subsystem A: bus interface control --------------------------------
    input  logic        bus_start,
    output logic [7:0]  bus_result,
    output logic        bus_done,
    //---- Subsystem B: data interface control --------------------------------
    input  logic        data_start,
    output logic [7:0]  data_last_value,
    output logic [3:0]  data_status_out,
    output logic        data_done,
    output logic        data_error_out
);

    //=========================================================================
    // Subsystem A: Bus Interface (modport port connection pattern)
    //=========================================================================

    //---- Interface instance -------------------------------------------------
    bus_if u_bus (
        .clk   (clk),
        .rst_n (rst_n)
    );

    //---- Master module (Level 2, bus_if.master) ----------------------------
    master u_master (
        .bus    (u_bus.master),
        .start  (bus_start),
        .done   (bus_done),
        .result (bus_result)
    );

    //---- Slave module (Level 2, bus_if.slave) ------------------------------
    slave u_slave (
        .bus (u_bus.slave)
    );

    //=========================================================================
    // Subsystem B: Data Interface (struct typedef + modport pattern)
    //=========================================================================

    //---- Interface instance -------------------------------------------------
    data_if u_data (
        .clk   (clk),
        .rst_n (rst_n)
    );

    //---- Data source module (Level 2, data_if.source) ----------------------
    data_source u_source (
        .bus         (u_data.source),
        .start       (data_start),
        .done        (data_done),
        .last_data   (data_last_value),
        .status_code (data_status_out),
        .error_out   (data_error_out)
    );

    //---- Data sink module (Level 2, data_if.sink) --------------------------
    data_sink u_sink (
        .bus (u_data.sink)
    );

endmodule
