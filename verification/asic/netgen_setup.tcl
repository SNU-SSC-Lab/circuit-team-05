# NSPL ordinary 5 V core MOS devices. Keep W/L comparison enabled.
# Both netlists are first rewritten by scripts/asic/lvs_reduce.py with the kit
# Calibre LVS deck's LVS REDUCE PARALLEL MOS YES, LVS RECOGNIZE GATES ALL and
# LVS REDUCE SPLIT GATES YES. Each line below names the deck statement it matches.
# Not done, so stricter than the deck: LVS REDUCE SERIES MOS YES (line 77,
# series MOS sharing one gate), and series-order freedom outside chains with
# one end on VDD/VSS (see lvs_reduce.py).

# Source/drain swap. Deck: DEVICE MN(NMOS4) NGATE NGATE(G) NISD(S) NISD(D) ...
# (and MP with PISD): S and D come from the same layer, so they are not ordered.
permute default

# Drop AS/AD/PS/PD and keep W/L. Deck: TRACE PROPERTY lists only W and L.
property default

# W and L must be equal. Deck: TRACE PROPERTY MN(NMOS4) W W 0, L L 0 (same for
# MP(PMOS4)): tolerance 0. Netgen's own default is 1 %. Chain inputs carry the
# W/L of the transistor they came from, so they get the same rule. Model names
# are matched without case (Netgen reads SPICE names without case). A side with
# no such class would silently keep 1 %, so it stops instead.
foreach side {-circuit1 -circuit2} {
    set found 0
    foreach model [cells list -all $side] {
        if {[regexp -nocase {^[np]mos4(_chain_gate)?$} $model]} {
            property "$side $model" tolerance {w 0} {l 0}
            incr found
        }
    }
    if {$found == 0} {
        error "netgen_setup.tcl: no nmos4/pmos4 class in $side, W/L tolerance 0 not applied"
    }
}
