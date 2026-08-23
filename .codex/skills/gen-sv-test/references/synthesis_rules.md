# Synthesis-Safe SystemVerilog Rules

> 更新于 v1.1.0：新增 struct/package/Verilator 相关规则。

## Allowed Constructs (Always OK)

| Construct | Usage |
|---|---|
| `module` / `endmodule` | Module definition |
| `package` / `endpackage` | Package for shared type definitions (v1.1.0) |
| `import pkg::*;` | Import package types (at file scope for port visibility) |
| `typedef struct packed { ... } name;` | Packed struct type definition (v1.1.0) |
| `input logic` / `output logic` | ANSI port declarations |
| `<struct_type>` on ports | Packed struct types on module ports (v1.1.0) |
| `<struct>.field` access | Struct field read/write |
| `<struct> <= <struct>` | Whole-struct assignment (same type) |
| `<struct> <= '0` | Whole-struct zero initialization |
| `assign <vec> = <struct>` | Packed struct to vector bitstream |
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
| `unpacked struct` on ports | Verilator 5.x 不支持 unpacked struct 端口 |
| `typedef struct unpacked { ... }` on ports | 同上 |
| `'{field: value, ...}` assignment | Icarus 12 不支持此语法 |
| `'{default: ...}` assignment | Icarus 12 不支持此语法 |

## Coding Style Rules

1. **One register per `always_ff` block** — don't mix unrelated registers.
2. **Compute next-state in `always_comb`** — separate `_next` signals from `_reg` signals.
3. **Async active-low reset** — use `rst_n` consistently.
4. **Default assignments** — every `case` must have a `default` branch; every `always_comb` must assign every output in every branch.
5. **No latches** — ensure every combinational path assigns all outputs.
6. **Named connections only** — never use positional port connections.

### Struct-Specific Coding Rules (v1.1.0)

7. **`import pkg::*` at file scope** — if module ports use package types, the import must appear BEFORE `module ... (`; module-body import is invisible to port declarations.
8. **Pack-only on ports** — struct ports must use `packed` types; `unpacked` struct ports are rejected by Verilator 5.x.
9. **Field-by-field assignment** — avoid `'{field: value}` pattern; use `sig.field <= value;` (Icarus 12 compatible).
10. **Zero-init with `'0`** — use `cfg_reg <= '0;` for whole-struct zero initialization (supported by both Icarus and Verilator).
11. **Avoid SV keywords as field names** — known Icarus 12 rejects `priority`; prefer descriptive names with prefixes/suffixes (e.g. `prio_level` not `priority`).
12. **Provide debug bitstream** — `assign debug_o = <packed_struct>;` creates a vector copy C++ testbenches can directly verify.
13. **Top scalar ports** — keep top-level module ports as scalars/logic vectors so C++ testbench avoids Verilator's struct-port flattened-API naming.

## Icarus Verilog Known Warnings (Safe to Ignore)

| Warning | Explanation |
|---|---|
| `vvp.tgt sorry: Case unique/unique0 qualities are ignored` | vvp runtime doesn't enforce `unique` semantics; synthesis tools do |
| `warning: implicit wire '...' has no fanin` | Can appear for unused outputs; add a default assignment to suppress |
| `sorry: constant selects in always_* processes` | Icarus 12 对 struct 字段访问的保守处理，不影响功能 |

## Verilator Known Warnings (Safe to Ignore)

| Warning | Explanation |
|---|---|
| `IMPORTSTAR` | `import pkg::*` at file scope for port type visibility — unavoidable |
| `PINCONNECTEMPTY` | Intentional empty port connections (`.port_name()`) — suppress with `-Wno-PINCONNECTEMPTY` |
| `MISINDENT` | Minor indentation mismatch in field assignments — cosmetic only |
| `WIDTHEXPAND` / `WIDTHTRUNC` | Bit-width mismatches that are intentional — suppress with `-Wno-` flags |

## Compile Commands

### Icarus Verilog

```bash
iverilog -g2012 -c filelist.f -o <output>.vvp 2>&1
```

- `-g2012`: Enable SystemVerilog-2012 support (required for package, struct, enum)
- `-c filelist.f`: Read source files from filelist
- `-o <output>.vvp`: Output compiled VVP file

### Verilator (v1.1.0)

```bash
verilator --cc --exe --build -f filelist.f sim_main.cpp \
  --top-module <top_module> \
  -Wall -Wno-fatal \
  -Wno-UNUSEDSIGNAL \
  -Wno-UNUSEDPARAM \
  -Wno-WIDTHEXPAND \
  -Wno-WIDTHTRUNC
```

```bash
./obj_dir/V<top_module>   # 运行仿真
```

- `--cc --exe --build`: Generate C++ model, link with exe, build in one step
- `-f filelist.f`: Read SV source files from filelist
- `--top-module <name>`: Specify top-level module for elaboration
- `-Wall -Wno-fatal`: Enable all warnings but don't treat them as errors
- `-Wno-UNUSEDSIGNAL` etc.: Suppress benign warnings about unconnected pins
