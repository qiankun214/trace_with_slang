#==============================================================================
# Filelist for GPIO Controller — iverilog compilation
#
# Compile with:
#   iverilog -g2012 -c filelist.f -o gpio_controller.vvp
#==============================================================================

# Configuration (macro definitions, must be compiled first)
gpio_config.svh

# Functional module
gpio_controller.sv
