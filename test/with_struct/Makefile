#==============================================================================
# Makefile — CSR System Verilator 仿真 + Icarus 编译检查
#==============================================================================

VERILATOR ?= verilator
IVERILOG  ?= iverilog
TOP        = csr_system
TRACE      ?= 0

.PHONY: all iv-check verilate sim trace clean

all: iv-check verilate sim

# ── Icarus Verilog 编译检查 ──────────────────────────────────────
iv-check:
	@echo "=== Icarus Verilog compilation check ==="
	$(IVERILOG) -g2012 -c filelist.f -o $(TOP).vvp
	@echo "  Icarus compilation: OK"

# ── Verilator C++ 模型构建 ───────────────────────────────────────
verilate:
	@echo "=== Verilator C++ model build ==="
	$(VERILATOR) --cc --exe --build -f filelist.f sim_main.cpp \
	  --top-module $(TOP) \
	  -Wall -Wno-fatal \
	  -Wno-UNUSEDSIGNAL \
	  -Wno-UNUSEDPARAM \
	  -Wno-WIDTHEXPAND \
	  -Wno-WIDTHTRUNC \
	  $(if $(filter 1,$(TRACE)),--trace,)

# ── 仿真执行 ────────────────────────────────────────────────────
sim: verilate
	@echo "=== Simulation run ==="
	./obj_dir/V$(TOP)

# ── 波形生成 (TRACE=1) ──────────────────────────────────────────
trace:
	$(MAKE) verilate TRACE=1
	@echo "=== Simulation with VCD trace ==="
	./obj_dir/V$(TOP)
	@echo "  VCD file: $(TOP).vcd (use GTKWave to view)"

# ── 清理 ────────────────────────────────────────────────────────
clean:
	rm -rf obj_dir *.vvp *.vcd *.lxt
