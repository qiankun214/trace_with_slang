# Synthesis-Safe SystemVerilog Rules

## Allowed Constructs (Always OK)

| Construct | Usage |
|---|---|
| `module` / `endmodule` | Module definition |
| `input logic` / `output logic` | ANSI port declarations |
| `parameter int` / `localparam` | Constants with defaults |
| `logic [N:0]` | Packed vector types |
| `always_comb` | Combinational logic |
| `always_ff @(posedge clk or negedge rst_n)` | Sequential logic with async reset |
| `always_ff @(posedge clk)` | Sequential logic without reset |
| `assign` | Continuous assignments |
| `enum` | State encoding for FSMs |
| `typedef enum logic [N:0]` | Typedef for state types |
| `case` / `endcase` | Case statements |
| `unique case` | Parallel case (ignored by vvp but OK for synthesis) |
| `if` / `else if` / `else` | Conditional logic |
| `generate` / `if` / `for` | Conditional/generate instantiation |
| `genvar` | Generate loop variable |
| `$clog2()` | Ceiling log2 (synthesis-compatible constant function) |
| `.port_name(signal)` | Named port connections |
| `//` / `/* */` | Comments |

## Forbidden Constructs (Not Synthesis-Safe)

| Construct | Reason |
|---|---|
| `initial` | Testbench-only, not synthesizable |
| `$display` / `$monitor` / `$strobe` | Simulation-only system tasks |
| `$finish` / `$stop` | Simulation control |
| `#delay` | Timing control, not synthesizable |
| `class` / `endclass` | Object-oriented, not synthesizable |
| `new()` | Dynamic allocation |
| `dynamic arrays` (`[]`) | Dynamic memory, not synthesizable |
| `queues` (`[$]`) | Dynamic memory, not synthesizable |
| `associative arrays` | Not synthesizable |
| `fork` / `join` / `join_any` / `join_none` | Testbench concurrency |
| `wait` | Level-sensitive timing control |
| `@(posedge ...)` inside always_comb | Edge detection in combinational context |
| `force` / `release` | Testbench constructs |
| `assert` / `assume` / `cover` | Formal verification (acceptable but avoid for basic test data) |

## Coding Style Rules

1. **One register per `always_ff` block** — don't mix unrelated registers.
2. **Compute next-state in `always_comb`** — separate `_next` signals from `_reg` signals.
3. **Async active-low reset** — use `rst_n` consistently.
4. **Default assignments** — every `case` must have a `default` branch; every `always_comb` must assign every output in every branch.
5. **No latches** — ensure every combinational path assigns all outputs.
6. **Named connections only** — never use positional port connections.

## Icarus Verilog Known Warnings (Safe to Ignore)

| Warning | Explanation |
|---|---|
| `vvp.tgt sorry: Case unique/unique0 qualities are ignored` | vvp runtime doesn't enforce `unique` semantics; synthesis tools do |
| `warning: implicit wire '...' has no fanin` | Can appear for unused outputs; add a default assignment to suppress |

## Compile Command

```bash
iverilog -g2012 -c filelist.f -o <output>.vvp 2>&1
```

- `-g2012`: Enable SystemVerilog-2012 support
- `-c filelist.f`: Read source files from filelist
- `-o <output>.vvp`: Output compiled VVP file
