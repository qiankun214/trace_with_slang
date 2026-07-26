#==============================================================================
# Filelist for ALU System — iverilog compilation
# Module hierarchy (3 levels):
#   Level 1: alu_system
#   Level 2: alu_core, alu_control, result_stage
#   Level 3: adder_8bit, logic_unit (inside alu_core)
#==============================================================================

# Level 3 — Leaf modules (must be compiled first)
adder_8bit.sv
logic_unit.sv

# Level 2 — Intermediate modules
alu_core.sv
alu_control.sv
result_stage.sv

# Level 1 — Top module
alu_system.sv
