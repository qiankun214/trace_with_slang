---
name: gen-sv-test
description: This skill should be used when the user asks to generate SystemVerilog test data, create multi-level module hierarchies for testing, produce SV test fixtures with submodules, or batch-generate synthesizable SV modules for tool validation. Triggers on phrases like "生成测试数据", "generate test SystemVerilog", "create multi-level SV modules", "批量生成SV模块", "generate SV test fixtures", or similar requests for creating hierarchical SystemVerilog designs for testing purposes.
version: 1.0.0
---

# SystemVerilog Test Data Generator

Generate multi-level, hierarchical SystemVerilog module designs suitable for testing downstream tools (parsers, linters, synthesizers, waveform viewers). Every generated design must compile cleanly under Icarus Verilog and use only synthesis-safe constructs.

## Design Constraints (non-negotiable)

1. **Hierarchy depth ≥ 2 levels** — a top module must instantiate at least 2 child modules, at least one of which instantiates at least 1 grandchild module.
2. **Submodule count ≥ 2** — the top module must contain at least 2 direct child instances.
3. **Synthesizable syntax only** — `always_ff`, `always_comb`, `assign`, `logic` types, `enum` for FSM states. No `initial`, `$display`, `$monitor`, `class`, dynamic arrays, queues, or fork/join.
4. **Icarus Verilog 12.0** — compile with `iverilog -g2012 -c filelist.f` and confirm exit code 0.
5. **ANSI-style port lists** — `input logic` / `output logic` with packed vector ranges.

## Workflow

### Step 1: Determine Target Directory and Design Theme

Ask the user (or infer from context) the target directory. Default to `test/with_instance/` under the current project root.

Choose a **realistic hardware theme** that naturally produces hierarchy. Preferred themes (pick one that fits the user's need):

| Theme | Top Module | Level-2 Children | Level-3 Grandchildren |
|---|---|---|---|
| ALU System | `alu_system` | `alu_core`, `alu_control`, `result_stage` | `adder_8bit`, `logic_unit` (inside alu_core) |
| GPIO Controller | `gpio_controller` | `gpio_regfile`, `gpio_pad_ctrl`, `intr_handler` | `reg_bank`, `sync_ff` (inside gpio_regfile) |
| FIFO Pipeline | `fifo_pipeline` | `sync_fifo`, `pipe_stage`, `flow_ctrl` | `fifo_mem`, `ptr_sync` (inside sync_fifo) |
| Counter System | `counter_system` | `cnt_8bit`, `cnt_16bit`, `cmp_unit` | `adder_8bit`, `mux_2to1` (inside cnt_8bit) |

### Step 2: Design the Module Hierarchy

Before writing code, plan the full hierarchy on paper/plan file:

```
top_module (Level 1)
├── child_a (Level 2)
│   ├── grandchild_a1 (Level 3)
│   └── grandchild_a2 (Level 3)
├── child_b (Level 2)
└── child_c (Level 2)
```

Define port lists for every module. Each module must have a clearly defined function — no "dummy" or empty modules.

### Step 3: Create Source Files (Bottom-Up)

Write modules from **leaf to root** so iverilog compilation order matches filelist order:

1. **Level 3 modules first** — pure combinational or simple sequential logic. These are the building blocks. See `references/templates.md` for starter code.
2. **Level 2 modules** — instantiate Level 3 children, add muxing/control logic.
3. **Level 1 (top) module** — instantiate all Level 2 children, wire them together.

Coding rules per module:
- One module per file, filename = module name + `.sv`
- Header comment block identifying the module's level and its parent
- ANSI port declarations
- Separate `always_comb` for next-state logic and `always_ff` for registers
- Named port connections on all instantiations (`.port_name(signal_name)` style)
- Instance names use `u_` prefix

### Step 4: Create filelist.f

Write `filelist.f` with modules ordered bottom-up (Level 3 → Level 2 → Level 1). Each line is a relative filename. Add a header comment showing the hierarchy.

### Step 5: Compile and Verify

```bash
cd <target_directory>
iverilog -g2012 -c filelist.f -o <top_module>.vvp 2>&1
```

Checklist:
- [ ] Exit code = 0
- [ ] No errors (warnings about `unique case` from vvp are acceptable)
- [ ] The `.vvp` output file exists
- [ ] Verify file count matches the plan

If compilation fails, read the error, fix the file, and recompile. Do NOT leave broken code.

### Step 6: Report

Summarize the generated design:
- Module hierarchy diagram (ASCII tree)
- File listing with levels
- Compilation result

## Parameterization

When generating multiple test datasets, vary these dimensions across runs:

- **Hierarchy depth** (2, 3, or 4 levels)
- **Number of children per parent** (2, 3, or more)
- **Design theme** (ALU, GPIO, FIFO, Counter, custom)
- **Interface complexity** (number of ports, data width)
- **Control logic style** (FSM vs. pipelined vs. purely combinational)

Each variant goes into its own subdirectory under `test/`.

## Reference Files

- `references/templates.md` — Starter templates for leaf, intermediate, and top modules
- `references/synthesis_rules.md` — Detailed synthesis-safety checklist
