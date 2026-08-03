//==============================================================================
// Module: data_sink
// Level:  2 (instantiated inside top, connected via data_if.sink modport)
// Description: Data sink module that receives packet sequences from the
//              data_if interface, validates them, and generates status
//              responses. Internally instantiates two level-3 submodules:
//              data_checker and status_logger.
//
// Hierarchy:
//   data_sink (Level 2)
//   ├── u_checker (data_checker, Level 3)
//   └── u_logger  (status_logger, Level 3)
//
// Key design: this module bridges between the interface's structured types
// (packet_t, status_t) and the traditional-port Level 3 submodules.
// Packet struct fields are extracted into individual signals for submodules;
// submodule outputs are assembled into the status_t struct fields.
//==============================================================================

module data_sink (
    data_if.sink bus
);

    //---- Internal interconnect signals --------------------------------------
    // Extracted from interface packet struct
    logic [7:0]  pkt_data;
    logic [3:0]  pkt_id;
    logic        pkt_valid;
    logic        pkt_last;

    // Checker outputs
    logic [3:0]  chk_status;
    logic        chk_error;

    // Logger outputs
    logic        logger_ack;
    logic [3:0]  logger_final_status;
    logic        logger_error_flag;

    //---- Extract fields from interface packet struct -------------------------
    assign pkt_data  = bus.packet.data;
    assign pkt_id    = bus.packet.id;
    assign pkt_valid = bus.packet.valid;
    assign pkt_last  = bus.packet.last;

    //---- Assemble interface status struct from submodule outputs -------------
    assign bus.status.ack    = logger_ack;
    assign bus.status.status = logger_final_status;
    assign bus.status.error  = logger_error_flag;

    //---- Submodule: data_checker (Level 3) ----------------------------------
    data_checker u_checker (
        .clk        (bus.clk),
        .rst_n      (bus.rst_n),
        .data       (pkt_data),
        .id         (pkt_id),
        .valid      (pkt_valid),
        .last       (pkt_last),
        .chk_status (chk_status),
        .chk_error  (chk_error)
    );

    //---- Submodule: status_logger (Level 3) ---------------------------------
    status_logger u_logger (
        .clk          (bus.clk),
        .rst_n        (bus.rst_n),
        .valid        (pkt_valid),
        .last         (pkt_last),
        .chk_status   (chk_status),
        .chk_error    (chk_error),
        .ack          (logger_ack),
        .final_status (logger_final_status),
        .error_flag   (logger_error_flag)
    );

endmodule
