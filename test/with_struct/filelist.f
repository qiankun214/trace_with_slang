#==============================================================================
# Filelist for CSR System — iverilog / Verilator compilation
# Module hierarchy (4 levels, 3 levels of submodule instantiation):
#
#   Level 1: csr_system
#   Level 2: csr_regfile, intr_handler, bus_decoder
#   Level 3: baud_gen (inside csr_regfile), irq_arbiter (inside intr_handler)
#   Level 4: pulse_counter (inside baud_gen)
#
# 3-level submodule call chain: csr_system.u_regfile.u_baud.u_counter
#
# 5 struct scenarios:
#   S1: csr_regfile  — 结构体实例化在模块内部 (internal struct signals)
#   S2: baud_gen     — 结构体例化在端口上 (struct ports)
#   S3: intr_handler — 结构体定义在模块内部 (local typedef struct)
#   S4: csr_pkg      — 结构体定义在集中的SV文件 (package shared types)
#   S5: irq_arbiter  — 结构体嵌套 (nested struct field access)
#==============================================================================

# Package (must be compiled first)
csr_pkg.sv

# Level 4 — Leaf leaf
pulse_counter.sv

# Level 3 — Grandchild
baud_gen.sv
irq_arbiter.sv

# Level 2 — Child
csr_regfile.sv
intr_handler.sv
bus_decoder.sv

# Level 1 — Top
csr_system.sv
