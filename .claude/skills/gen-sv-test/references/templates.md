# Module Templates

## Leaf Module (Level 3) — Pure Combinational

```systemverilog
//==============================================================================
// Module: <module_name>
// Level:  3 (leaf module, instantiated inside <parent_module>)
// Description: <one-line purpose>
//              Pure combinational logic, synthesis-safe.
//==============================================================================

module <module_name> (
    input  logic [7:0] a,
    input  logic [7:0] b,
    input  logic       sel,
    output logic [7:0] result,
    output logic       flag
);

    always_comb begin
        // Combinational logic here
        result = <expression>;
        flag   = <expression>;
    end

endmodule
```

## Leaf Module (Level 3) — Sequential (single register)

```systemverilog
//==============================================================================
// Module: <module_name>
// Level:  3 (leaf module, instantiated inside <parent_module>)
// Description: <one-line purpose>
//              Sequential logic with async reset, synthesis-safe.
//==============================================================================

module <module_name> (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        en,
    input  logic [7:0]  data_in,
    output logic [7:0]  data_out
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            data_out <= 8'b0;
        end else if (en) begin
            data_out <= data_in;
        end
    end

endmodule
```

## Intermediate Module (Level 2) — Instantiates Children

```systemverilog
//==============================================================================
// Module: <module_name>
// Level:  2 (instantiated inside <top_module>)
// Description: <one-line purpose>
//              Instantiates <child_a> and <child_b> (Level 3).
//==============================================================================

module <module_name> (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  operand_a,
    input  logic [7:0]  operand_b,
    input  logic [1:0]  op,
    output logic [7:0]  result
);

    //---- Internal signals ------------------------------------------------
    logic [7:0] child_a_result;
    logic [7:0] child_b_result;
    logic       sel_int;

    //---- Child instantiation: <child_a> (Level 3) ------------------------
    <child_a> u_child_a (
        .a      (operand_a),
        .b      (operand_b),
        .result (child_a_result)
    );

    //---- Child instantiation: <child_b> (Level 3) ------------------------
    <child_b> u_child_b (
        .a      (operand_a),
        .sel    (op[0]),
        .result (child_b_result)
    );

    //---- Output mux ------------------------------------------------------
    always_comb begin
        case (op[1])
            1'b0: result = child_a_result;
            1'b1: result = child_b_result;
        endcase
    end

endmodule
```

## Top Module (Level 1) — System Integration

```systemverilog
//==============================================================================
// Module: <top_module>
// Level:  1 (top-level parent module)
// Description: <one-line purpose>
//
// Module hierarchy:
//   Level 1: <top_module>
//   Level 2: ├── <child_a>
//            ├── <child_b>
//            └── <child_c>
//   Level 3:     ├── <grandchild_a1>  (inside child_a)
//                └── <grandchild_a2>  (inside child_a)
//
// All modules use synthesis-safe SystemVerilog constructs only.
//==============================================================================

module <top_module> (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  input_a,
    input  logic [7:0]  input_b,
    input  logic [1:0]  opcode,
    input  logic        start,
    output logic [7:0]  output_data,
    output logic        done
);

    //---- Internal interconnect signals -----------------------------------
    logic [7:0] child_a_result;
    logic [7:0] child_b_result;

    //---- Submodule: <child_a> (Level 2) ----------------------------------
    <child_a> u_child_a (
        .clk       (clk),
        .rst_n     (rst_n),
        .operand_a (input_a),
        .operand_b (input_b),
        .result    (child_a_result)
    );

    //---- Submodule: <child_b> (Level 2) ----------------------------------
    <child_b> u_child_b (
        .clk    (clk),
        .rst_n  (rst_n),
        .start  (start),
        .result (child_b_result)
    );

    //---- Submodule: <child_c> (Level 2) ----------------------------------
    <child_c> u_child_c (
        .clk       (clk),
        .rst_n     (rst_n),
        .data_in   (child_a_result),
        .ctrl_in   (child_b_result),
        .data_out  (output_data),
        .done      (done)
    );

endmodule
```

## Filelist Template

```
#==============================================================================
# Filelist for <design_name> — iverilog compilation
# Module hierarchy (3 levels):
#   Level 1: <top_module>
#   Level 2: <child_a>, <child_b>, <child_c>
#   Level 3: <grandchild_a1>, <grandchild_a2>
#==============================================================================

# Level 3 — Leaf modules (must be compiled first)
<grandchild_a1>.sv
<grandchild_a2>.sv

# Level 2 — Intermediate modules
<child_a>.sv
<child_b>.sv
<child_c>.sv

# Level 1 — Top module
<top_module>.sv
```

## FSM Control Module Template

```systemverilog
//==============================================================================
// Module: <fsm_name>
// Level:  2 (instantiated inside <top_module>)
// Description: Simple FSM controller, synthesis-safe.
//==============================================================================

module <fsm_name> (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    output logic enable,
    output logic done
);

    typedef enum logic [1:0] {
        S_IDLE    = 2'b00,
        S_ACTIVE  = 2'b01,
        S_DONE    = 2'b10
    } state_t;

    state_t state_next, state_reg;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_reg <= S_IDLE;
        end else begin
            state_reg <= state_next;
        end
    end

    always_comb begin
        state_next = state_reg;
        case (state_reg)
            S_IDLE:   if (start)  state_next = S_ACTIVE;
            S_ACTIVE:             state_next = S_DONE;
            S_DONE:   if (!start) state_next = S_IDLE;
            default:              state_next = S_IDLE;
        endcase
    end

    always_comb begin
        enable = (state_reg == S_ACTIVE);
        done   = (state_reg == S_DONE);
    end

endmodule
```
