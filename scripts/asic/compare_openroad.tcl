# NSPL physical experiment. Wire RC is an explicit estimate, not qualified PEX.
set_thread_count 1
read_lef technology.lef
read_lef cells.lef
read_liberty cells.lib
read_verilog input.v
link_design shift_reg_8bit
read_sdc constraints.sdc
initialize_floorplan -die_area {0 0 320 288} -core_area {16 36 304 252} -site core
make_tracks MET1 -x_offset 1.5 -x_pitch 3.0 -y_offset 1.5 -y_pitch 3.0
make_tracks MET2 -x_offset 1.6 -x_pitch 3.2 -y_offset 1.6 -y_pitch 3.2
make_tracks MET3 -x_offset 3.0 -x_pitch 3.0 -y_offset 3.0 -y_pitch 3.0
# Conservative placeholder for physical experimentation only. Report as estimated.
set_wire_rc -signal -resistance 0.08 -capacitance 0.0002
set_wire_rc -clock -resistance 0.05 -capacitance 0.0002
set_pin_length -hor_length 6 -ver_length 6
place_pins -hor_layers MET3 -ver_layers MET2
set_placement_padding -global -left 1 -right 1
global_placement -density 0.45
detailed_placement
check_placement -verbose
write_def placed.def
configure_cts_characterization -max_slew 2.2 -max_cap 1.2
clock_tree_synthesis -buf_list {CLKBUFX2 CLKBUFX4} -root_buf CLKBUFX4 -apply_ndr none \
    -sink_clustering_enable -sink_clustering_size 4 -sink_clustering_max_diameter 100
detailed_placement
check_placement -verbose
report_cts
write_def cts.def
write_verilog cts.v
add_global_connection -net VDD -pin_pattern VDD -power
add_global_connection -net VSS -pin_pattern VSS -ground
global_connect
set_voltage_domain -name CORE -power VDD -ground VSS
define_pdn_grid -name core -voltage_domains CORE -pins {MET3}
# Keep vertical power trunks outside the cells: their M1 clock pins otherwise
# have only one access track and can sit directly under a MET2 power stripe.
add_pdn_ring -grid core -layers {MET2 MET3} -widths {2 2} -spacings {2 2} -core_offsets {4 4}
add_pdn_stripe -grid core -layer MET1 -width 2 -followpins -extend_to_core_ring
add_pdn_connect -grid core -layers {MET1 MET2}
add_pdn_connect -grid core -layers {MET2 MET3}
pdngen
check_power_grid -net VDD
check_power_grid -net VSS
set_routing_layers -signal MET1-MET3 -clock MET1-MET3
global_route -guide_file route.guide
detailed_route -droute_end_iter 4 -output_drc route.drc -output_maze route.maze.log
write_def final.def
write_verilog final.v
write_db final.odb
set_propagated_clock [all_clocks]
estimate_parasitics -global_routing
report_checks -path_delay min_max -format full_clock_expanded
