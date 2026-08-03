//==============================================================================
// Interface: data_if
// Type:     Interface with typedef struct packed + modport
// Description: Data streaming interface with structured packet/status types.
//              Contains two packed struct definitions (packet_t, status_t)
//              passed between source and sink modules via modports.
//              No procedural logic — pure type/signal/modport definition.
//
// Usage:
//   data_if u_data (.clk(clk), .rst_n(rst_n));
//   data_source u_source (.bus(u_data.source));
//   data_sink   u_sink   (.bus(u_data.sink));
//==============================================================================

interface data_if (
    input logic clk,
    input logic rst_n
);
    //---- Struct: data packet (source -> sink) -------------------------------
    typedef struct packed {
        logic [7:0] data;
        logic [3:0] id;
        logic       valid;
        logic       last;
    } packet_t;

    //---- Struct: status response (sink -> source) ---------------------------
    typedef struct packed {
        logic [3:0] status;
        logic       error;
        logic       ack;
    } status_t;

    //---- Interface signals --------------------------------------------------
    packet_t  packet;
    status_t  status;

    modport source (
        input  clk, rst_n, status,
        output packet
    );

    modport sink (
        input  clk, rst_n, packet,
        output status
    );
endinterface
