#!/usr/bin/env bash
#==============================================================================
# run_verilator.sh — Build & run top module under Verilator 5.032
#
# Usage: ./run_verilator.sh
#
# Steps:
#   1. Compile all SV files + main.cpp with Verilator
#   2. Run the generated simulation executable
#   3. Report pass/fail based on exit code
#==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VERILATOR="${VERILATOR:-/usr/bin/verilator}"
TOP="${TOP:-top}"

echo "=========================================="
echo " Verilator Build & Run: test_interface"
echo " Top module: $TOP"
echo "=========================================="

#---- Clean previous build ----------------------------------------------------
rm -rf obj_dir

#---- Source files (ordered for clarity) --------------------------------------
# Interface definitions first
SV_FILES=(
    bus_if.sv
    data_if.sv
)

# Subsystem A — Level 3 leaf modules
SV_FILES+=(
    addr_generator.sv
    data_buffer.sv
    reg_file.sv
    resp_arbiter.sv
)

# Subsystem A — Level 2 modules
SV_FILES+=(
    master.sv
    slave.sv
)

# Subsystem B — Level 3 leaf modules
SV_FILES+=(
    packet_gen.sv
    sequence_ctrl.sv
    data_checker.sv
    status_logger.sv
)

# Subsystem B — Level 2 modules
SV_FILES+=(
    data_source.sv
    data_sink.sv
)

# Top module
SV_FILES+=(
    top.sv
)

#---- Verilator compilation ---------------------------------------------------
echo ""
echo "[1/2] Compiling with Verilator..."
echo "  Source files: ${SV_FILES[*]}"

"$VERILATOR" --cc --build --exe -j 0 \
    --top-module "$TOP" \
    -I. \
    -Wall \
    -Wno-WIDTH \
    -Wno-UNUSEDSIGNAL \
    -Wno-UNOPTFLAT \
    --trace \
    "${SV_FILES[@]}" \
    main.cpp \
    -o Vtop 2>&1

echo "  Compilation: OK"

#---- Run simulation ----------------------------------------------------------
echo ""
echo "[2/2] Running simulation..."
./obj_dir/Vtop
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "=========================================="
    echo " RESULT: ALL TESTS PASSED (exit 0)"
    echo "=========================================="
else
    echo "=========================================="
    echo " RESULT: TEST FAILED (exit $EXIT_CODE)"
    echo "=========================================="
    exit 1
fi
