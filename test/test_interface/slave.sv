//==============================================================================
// Module: slave
// Level:  2 (instantiated inside top, connected via bus_if.slave modport)
// Description: Bus slave module that services read/write transactions from
//              the bus_if interface. Internally instantiates two level-3
//              submodules: reg_file and resp_arbiter.
//
// Hierarchy:
//   slave (Level 2)
//   ├── u_regfile (reg_file,     Level 3)
//   └── u_arbiter (resp_arbiter, Level 3)
//
// Function:
//   - reg_file: stores/reads data at addressed location
//   - resp_arbiter: arbitrates write vs read, manages ready/ack handshake
//   - slave acts as a wiring bridge between the interface modport and submodules
//==============================================================================

module slave (
    bus_if.slave bus
);

    //---- Internal interconnect signals --------------------------------------
    logic [7:0] rdata_raw;
    logic [7:0] rdata_arb;
    logic       ready_int;

    //---- Submodule: reg_file (Level 3) --------------------------------------
    reg_file u_regfile (
        .clk   (bus.clk),
        .rst_n (bus.rst_n),
        .write (bus.write),
        .addr  (bus.addr),
        .wdata (bus.wdata),
        .rdata (rdata_raw)
    );

    //---- Submodule: resp_arbiter (Level 3) ----------------------------------
    resp_arbiter u_arbiter (
        .clk       (bus.clk),
        .rst_n     (bus.rst_n),
        .write     (bus.write),
        .read      (bus.read),
        .rdata_raw (rdata_raw),
        .rdata_out (rdata_arb),
        .ready     (ready_int)
    );

    //---- Interface output assignments ---------------------------------------
    assign bus.rdata = rdata_arb;
    assign bus.ready = ready_int;

endmodule
