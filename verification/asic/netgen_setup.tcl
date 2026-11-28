# NSPL ordinary 5 V core MOS devices. Keep W/L comparison enabled.
# Both netlists are first rewritten by scripts/asic/lvs_reduce.py with the kit
# Calibre LVS deck's LVS REDUCE PARALLEL MOS YES, LVS RECOGNIZE GATES ALL and
# LVS REDUCE SPLIT GATES YES. Each line below names the deck statement it matches.

# Source/drain swap. Deck: DEVICE MN(NMOS4) NGATE NGATE(G) NISD(S) NISD(D) ...
# (and MP with PISD): S and D come from the same layer, so they are not ordered.
permute default

# Drop AS/AD/PS/PD and keep W/L. Deck: TRACE PROPERTY lists only W and L.
property default

# W and L must be equal. Deck: TRACE PROPERTY MN(NMOS4) W W 0, L L 0 (same for
# MP(PMOS4)): tolerance 0. Netgen's own default is 1 %. Chain inputs carry the
# W/L of the transistor they came from, so they get the same rule.
foreach side {-circuit1 -circuit2} {
    foreach model [cells list -all $side] {
        if {[regexp {^[np]mos4(_chain_gate)?$} $model]} {
            property "$side $model" tolerance {w 0} {l 0}
        }
    }
}
