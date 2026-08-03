//==============================================================================
// Interface: bus_if
// Type:     Interface with modport — port connection pattern
// Description: Simple 8-bit bus interface connecting master and slave modules.
//              Contains 6 internal signals mapped through master/slave modports.
//              No procedural logic — pure signal + modport definition.
//
// Usage:
//   bus_if u_bus (.clk(clk), .rst_n(rst_n));
//   master u_master (.bus(u_bus.master));
//   slave  u_slave  (.bus(u_bus.slave));
//==============================================================================

interface bus_if (
    input logic clk,
    input logic rst_n
);
    logic [7:0] addr;
    logic [7:0] wdata;
    logic [7:0] rdata;
    logic       write;
    logic       read;
    logic       ready;

    modport master (
        input  clk, rst_n, rdata, ready,
        output addr, wdata, write, read
    );

    modport slave (
        input  clk, rst_n, addr, wdata, write, read,
        output rdata, ready
    );
endinterface
