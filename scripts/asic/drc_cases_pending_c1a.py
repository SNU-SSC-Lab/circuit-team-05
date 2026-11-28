"""C1a (wave 2): Calibre oracle fixtures for not-yet-ported NSPL front-end DRC rules.

Same dict format as team-05 scripts/asic/drc_cases.py:
    dict(rule, label, shapes, fail, hierarchy, dbu, raises)
shapes = [gds_layer, [x1, y1, x2, y2]] or [gds_layer, [[x, y], ...]] (datatype 0, um).

`fail` is our hypothesis of Calibre's verdict on `rule` alone; Calibre decides.
Other rules may also fire on a fixture; compare per target rule.
cases_with_meta() adds rationale / deck line / uncertainty for manifest.json.

Every fixture gets a CHIPBOUNDARY (layer 0) rectangle 10 um around its shapes, so
the deck's BULK = SIZE EXTENT BY 0.01 (and hence PSUB/PWELL) never sits on a
test edge. Most fixtures also carry a contacted PTAP so 1.PWL.bad1 stays quiet.
"""

import math

CB, KEY, NW, PW, ACT, P1, P2, NSD, PSD = 0, 1, 2, 3, 11, 12, 13, 14, 15
CONT, M1, RES, CAP, BJT, DIODE, LVSD = 31, 32, 51, 53, 56, 57, 60

# Line numbers in NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal (sha256 6c012073...c4f0f).
DECK = {'1.NWL.S.1': 491, '1.NWL.S.2': 496, '1.NWL.bad2': 513, '1.PWL.bad1': 518,
        '1.PWL.bad2': 525, '2.ACT.W2': 540, '2.ACT.E1': 558, '2.ACT.E4': 574,
        '2.ACT.E5': 579, '2.ACT.T1': 585, '2.ACT.T2': 595, '2.ACT.bad1': 605,
        '2.ACT.bad2': 612, '2.ACT.bad3': 617, '3.PL1.W2': 635, '3.PL1.S1': 647,
        '3.PL1.S2': 653, '3.PL1.S3': 659, '3.PL1.S4': 664, '3.PL1.O': 671,
        '3.PL1.ANT': 679, '5.NSD.E': 751, '5.NSD.bad1': 763, '6.PSD.E': 784,
        '6.PSD.bad1': 796, '7.CONT.S3': 825, '7.CONT.S4': 832, '7.CONT.S6': 842,
        '7.CONT.S7': 847, '7.CONT.S8': 852, '7.CONT.E4': 874, 'SKEW': 202,
        'NONSIMPLE': 66, 'ACUTE': 68}


def r(v):
    return round(v+0.0, 3)+0.0


def snap(v):
    """Round down to the 0.01 um grid (centres of odd widths such as 100.01)."""
    return math.floor(v*100+1e-6)/100


def R(layer, x1, y1, x2, y2):
    return [layer, [r(x1), r(y1), r(x2), r(y2)]]


def P(layer, points):
    return [layer, [[r(x), r(y)] for x, y in points]]


def cont(x, y, metal=True):
    """0.6 um contact with lower-left (x, y) and MET1 enclosing it by 0.6."""
    shapes = [R(CONT, x, y, x+.6, y+.6)]
    if metal:
        shapes.append(R(M1, x-.6, y-.6, x+1.2, y+1.2))
    return shapes


def sides(value):
    return tuple(value) if isinstance(value, (tuple, list)) else (value,)*4


def tap(kind, x, y, w=1.6, h=1.6, imp=.5, contacted=True, cx=None, cy=None):
    """ACT (x..x+w, y..y+h) with NSD ('n') or PSD ('p'); imp = margin or (l, b, r, t)."""
    il, ib, ir, it = sides(imp)
    shapes = [R(ACT, x, y, x+w, y+h), R(NSD if kind == 'n' else PSD, x-il, y-ib, x+w+ir, y+h+it)]
    if contacted:
        shapes += cont(x+w/2-.3 if cx is None else cx, y+h/2-.3 if cy is None else cy)
    return shapes


def mos(kind, x, y, W=2.0, L=.5, sdl=2.0, sdr=2.0, endcap=.5, pad='top', pad_gap=1.1,
        pad_dx=0., imp=.5, cl=True, cr=True, implant=True):
    """Transistor, ACT lower-left (x, y), vertical gate. Source/drain contacts sit 0.5
    inside the outer ACT edges. pad='top'/'bottom' adds a contacted 1.6-wide poly pad
    pad_gap away from the ACT; `endcap` is the opposite gate end-cap."""
    xg, yt = x+sdl, y+W
    xr = xg+L+sdr
    shapes = [R(ACT, x, y, xr, yt)]
    if implant:
        il, ib, ir, it = sides(imp)
        shapes.append(R(NSD if kind == 'n' else PSD, x-il, y-ib, xr+ir, yt+it))
    cy = snap(y+W/2-.3)
    if cl:
        shapes += cont(x+.5, cy)
    if cr:
        shapes += cont(xr-1.1, cy)
    xc = snap(xg+L/2+pad_dx)
    reach = max(pad_gap, 1.1)+1.6
    if pad == 'top':
        shapes.append(R(P1, xg, y-endcap, xg+L, yt+pad_gap))
        shapes.append(R(P1, xc-.8, yt+pad_gap, xc+.8, yt+reach))
        shapes += cont(xc-.3, yt+reach-1.1)
    elif pad == 'bottom':
        shapes.append(R(P1, xg, y-pad_gap, xg+L, yt+endcap))
        shapes.append(R(P1, xc-.8, y-reach, xc+.8, y-pad_gap))
        shapes += cont(xc-.3, y-reach+.5)
    else:
        shapes.append(R(P1, xg, y-endcap, xg+L, yt+endcap))
    return shapes


def act_right(sdl=2.0, L=.5, sdr=2.0, x=0.):
    return x+sdl+L+sdr


def nmos_cell(x=0., y=0., W=2.0, ptap=True, **kw):
    """NMOS plus a contacted PTAP 2.4 um to its left (both in the substrate PWELL)."""
    shapes = mos('n', x, y, W=W, **kw)
    if ptap:
        shapes += tap('p', x-4.0, snap(y+W/2-.8))
    return shapes


def pmos_cell(x=0., y=0., W=2.0, ntap=True, outer_ptap=True, margin=2.0, **kw):
    """PMOS + contacted NTAP in one NWELL (margin 2.0) + PTAP outside the NWELL."""
    xr = act_right(kw.get('sdl', 2.0), kw.get('L', .5), kw.get('sdr', 2.0), x)
    shapes = mos('p', x, y, W=W, **kw)
    if ntap:
        shapes += tap('n', x-4.0, snap(y+W/2-.8))
    shapes.append(R(NW, x-6.0, y-margin, xr+margin, y+W+margin))
    if outer_ptap:
        shapes += tap('p', x-9.6, snap(y+W/2-.8))
    return shapes


def poly_bar(layer, x1, y1, x2, y2, cx, cy):
    """Contacted poly (layer 12 or 13) rectangle; contact lower-left (cx, cy)."""
    return [R(layer, x1, y1, x2, y2)]+cont(cx, cy)


def nwell_with_tap(x1, y1, x2, y2, tx, ty):
    return [R(NW, x1, y1, x2, y2)]+tap('n', tx, ty)


def resistor(x, y, lvsd=True, implant=None):
    """P+ POLY2 resistor 2 x 10: RES over all of it, LVSD over the body, end contacts."""
    shapes = [R(P2, x, y, x+2, y+10), R(RES, x-.5, y-.5, x+2.5, y+10.5)]
    if lvsd:
        shapes.append(R(LVSD, x, y+1.6, x+2, y+8.4))
    if implant:
        shapes.append(R(implant, x-.5, y-.5, x+2.5, y+10.5))
    return shapes+cont(x+.7, y+.5)+cont(x+.7, y+8.9)


def pip_cap(x, y, implant=None, p2_cont=(3.7, 3.7)):
    """PIP capacitor: POLY1 11x8 bottom plate, POLY2 6x6 top plate, CAP marker, contacts."""
    shapes = [R(P1, x, y, x+11, y+8), R(P2, x+1, y+1, x+7, y+7), R(CAP, x-1, y-1, x+12, y+9)]
    if implant:
        shapes.append(R(implant, x-.5, y-.5, x+11.5, y+8.5))
    return shapes+cont(x+p2_cont[0], y+p2_cont[1])+cont(x+9.0, y+3.7)


def nwell_ring(x, y, size=20., bar=4.):
    """Closed NWELL ring (4 rectangles) with a contacted NTAP in the bottom bar."""
    return [R(NW, x, y, x+size, y+bar), R(NW, x, y+size-bar, x+size, y+size),
            R(NW, x, y+bar, x+bar, y+size-bar), R(NW, x+size-bar, y+bar, x+size, y+size-bar)
            ]+tap('n', x+size/2-.8, y+bar/2-.8)


def cases_with_meta():
    result = []

    def emit(rule, label, shapes, fail, why, hierarchy=False, uncertain=False):
        xs = [v for _, s in shapes for v in ([p[0] for p in s] if isinstance(s[0], list) else [s[0], s[2]])]
        ys = [v for _, s in shapes for v in ([p[1] for p in s] if isinstance(s[0], list) else [s[1], s[3]])]
        frame = R(CB, min(xs)-10, min(ys)-10, max(xs)+10, max(ys)+10)
        case = dict(rule=rule, label=label, shapes=shapes+[frame], fail=fail,
                    hierarchy=hierarchy, dbu=.001, raises=False)
        result.append((case, dict(rationale=why, deck_line=DECK[rule], uncertain=uncertain)))

    # ---------------- 1.NWL.S.1 / 1.NWL.S.2 : NWELL space by potential -------------
    def nwell_pair(g, net, res=False):
        """Two 6-wide NWELLs gap g, one NTAP each. net: 'same' (MET1 strap), 'diff', 'none' (no taps)."""
        h = 20 if res else 8
        ty = 17 if res else 3.2
        b = 6+g
        shapes = [R(NW, 0, 0, 6, h), R(NW, b, 0, b+6, h)]+tap('p', -4.0, ty)
        if net != 'none':
            shapes += tap('n', 2.2, ty)+tap('n', b+2.2, ty)
        if net == 'same':
            shapes.append(R(M1, 2.1, ty-.1, b+3.9, ty+1.7))
        if res:
            shapes += [R(RES, -.5, 4, 6.5, 16), R(RES, b-.5, 4, b+6.5, 16)]
        return shapes
    S1 = 'EXT NWELL < 1.25 CONNECTED: same-net NWELLs (NTAPs strapped by MET1; SCONNECT NTAP NWELL BY CONT) gap '
    for g, fail in [(1.24, True), (1.25, False), (1.26, False)]:
        emit('1.NWL.S.1', f'same-net-gap-{g:.2f}', nwell_pair(g, 'same'), fail, S1+f'{g}')
    emit('1.NWL.S.1', 'same-net-gap-1.24-child-rotated', nwell_pair(1.24, 'same'), True, S1+'1.24', hierarchy=True)
    emit('1.NWL.S.1', 'different-net-gap-1.24', nwell_pair(1.24, 'diff'), False,
         'separate MET1 per NTAP -> different nets; S.1 is CONNECTED only (S.2 fires instead)')
    emit('1.NWL.S.1', 'untapped-gap-1.24', nwell_pair(1.24, 'none'), False,
         'untapped NWELLs are separate nets (assumed), so CONNECTED does not apply', uncertain=True)
    S2 = 'EXT NWELL < 4 NOT CONNECTED: different-net NWELLs (separate MET1 per NTAP) gap '
    for g, fail in [(3.99, True), (4.0, False), (4.01, False)]:
        emit('1.NWL.S.2', f'different-net-gap-{g:.2f}', nwell_pair(g, 'diff'), fail, S2+f'{g}')
    emit('1.NWL.S.2', 'different-net-gap-3.99-child-rotated', nwell_pair(3.99, 'diff'), True, S2+'3.99', hierarchy=True)
    emit('1.NWL.S.2', 'same-net-gap-3.99', nwell_pair(3.99, 'same'), False,
         'NOT CONNECTED excludes same-net NWELLs; gap 3.99 >= 1.25 so S.1 is also clean')
    emit('1.NWL.S.2', 'same-net-gap-1.25', nwell_pair(1.25, 'same'), False,
         'same-potential NWELLs at the S.1 minimum do not trigger the 4 um rule')
    emit('1.NWL.S.2', 'untapped-gap-3.99', nwell_pair(3.99, 'none'), True,
         'untapped NWELL polygons are assumed to be distinct nets -> NOT CONNECTED < 4 fires', uncertain=True)
    RN = 'second statement OneSpace_check RESNW 4 (RESNW = NWELL AND RES); NWELLs strapped to one net so the first statement is silent; gap '
    for g, fail in [(3.99, True), (4.0, False)]:
        emit('1.NWL.S.2', f'nwell-resistors-same-net-gap-{g:.2f}', nwell_pair(g, 'same', res=True), fail, RN+f'{g}')

    # ---------------- 1.NWL.bad2 : PACT without poly inside NWELL -----------------
    def nwell_island(px, marker=None):
        shapes = nwell_with_tap(0, 0, 10, 6, 1.5, 2.2)+tap('p', -4.0, 2.2)+tap('p', px, 2.2)
        if marker:
            shapes.append(R(marker, px-1, 1.2, px+2.6, 4.8))
        return shapes
    B2 = 'AND NWELL ((PACT NOT INTERACT POLY1) NOT BJT NOT DIODE): '
    emit('1.NWL.bad2', 'p-plus-island-in-nwell', nwell_island(6.0), True, B2+'contacted P+ ACT (no poly) fully inside NWELL')
    emit('1.NWL.bad2', 'p-plus-island-straddles-nwell-edge', nwell_island(9.2), True, B2+'P+ ACT half inside NWELL (x 9.2..10.8, edge 10)')
    emit('1.NWL.bad2', 'p-plus-island-touches-nwell-from-outside', nwell_island(10.0), False, B2+'P+ ACT abuts NWELL from outside: AND area is zero')
    emit('1.NWL.bad2', 'p-plus-island-under-diode', nwell_island(6.0, DIODE), False, B2+'DIODE marker removes the P+ ACT')
    emit('1.NWL.bad2', 'p-plus-island-under-bjt', nwell_island(6.0, BJT), False, B2+'BJT marker removes the P+ ACT')
    emit('1.NWL.bad2', 'pmos-in-nwell', pmos_cell(), False, B2+'PMOS ACT interacts POLY1, so it is not a P+ island')
    emit('1.NWL.bad2', 'p-plus-island-in-nwell-child-rotated', nwell_island(6.0), True, B2+'as p-plus-island-in-nwell', hierarchy=True)

    # ---------------- 1.PWL.bad1 : PWELL must have a contacted PTAP ----------------
    PB1 = 'NOT INTERACT (PWELL NOT BJT-without-PNP NOT DIODE) (PTAP INTERACT CONT); PWELL = BULK NOT NWELL: '
    emit('1.PWL.bad1', 'contacted-ptap', nmos_cell(), False, PB1+'substrate PWELL holds a contacted PTAP')
    emit('1.PWL.bad1', 'uncontacted-ptap', mos('n', 0, 0)+tap('p', -4.0, .2, contacted=False), True, PB1+'PTAP without CONT does not count')
    emit('1.PWL.bad1', 'no-ptap', mos('n', 0, 0), True, PB1+'NMOS only, no PTAP')
    emit('1.PWL.bad1', 'ptap-inside-nwell-does-not-count',
         nwell_with_tap(0, 0, 10, 6, 1.5, 2.2)+tap('p', 6.0, 2.2), True, PB1+'P+ tap inside NWELL is not PTAP (PACT NOT NWELL)')
    ring = nwell_ring(0, 0)+tap('p', -4.0, 9.2)
    emit('1.PWL.bad1', 'isolated-island-without-tap', ring, True, PB1+'NWELL ring cuts a 12x12 PWELL island with no tap; outer PWELL is tapped')
    emit('1.PWL.bad1', 'isolated-island-with-nmos-no-tap', ring+mos('n', 5.75, 9.0), True, PB1+'island holds an NMOS but no tap')
    emit('1.PWL.bad1', 'isolated-island-with-tap', ring+tap('p', 9.2, 9.2), False, PB1+'both PWELL pieces tapped')
    emit('1.PWL.bad1', 'isolated-island-under-diode', ring+[R(DIODE, 4, 4, 16, 16)], False, PB1+'DIODE exactly covers the untapped island')
    emit('1.PWL.bad1', 'isolated-island-under-bjt', ring+[R(BJT, 4, 4, 16, 16)], False,
         PB1+'BJT without PNP emitter exactly covers the untapped island', uncertain=True)

    # ---------------- 1.PWL.bad2 : NACT without poly in PWELL ---------------------
    def n_island(marker=None):
        shapes = tap('p', -4.0, 0)+tap('n', 2.0, 0)
        if marker:
            shapes.append(R(marker, 1.0, -1.0, 4.6, 2.6))
        return shapes
    PB2 = 'AND (PWELL NOT BJT NOT DIODE) (NACT NOT INTERACT POLY1): '
    emit('1.PWL.bad2', 'n-plus-island-in-pwell', n_island(), True, PB2+'contacted N+ ACT outside any NWELL')
    emit('1.PWL.bad2', 'n-plus-island-under-diode', n_island(DIODE), False, PB2+'DIODE marker removes it')
    emit('1.PWL.bad2', 'n-plus-island-under-bjt', n_island(BJT), False, PB2+'BJT marker removes it')
    emit('1.PWL.bad2', 'nmos', nmos_cell(), False, PB2+'NMOS ACT interacts POLY1')
    emit('1.PWL.bad2', 'ntap-in-nwell', nwell_with_tap(0, 0, 6, 6, 2.2, 2.2)+tap('p', -4.0, 2.2), False, PB2+'NTAP inside NWELL')
    emit('1.PWL.bad2', 'ntap-straddles-nwell-edge', [R(NW, 0, 0, 6, 6)]+tap('n', 5.2, 2.2)+tap('p', -4.0, 2.2), True,
         PB2+'N+ ACT x 5.2..6.8 with NWELL edge at 6: outside part is in PWELL')
    emit('1.PWL.bad2', 'n-plus-island-child-rotated', n_island(), True, PB2+'as n-plus-island-in-pwell', hierarchy=True)

    # ---------------- 2.ACT.W2 : max transistor width 100 -------------------------
    W2 = 'LENGTH (PN_ACT NOT GATE) > 100: every edge of the source/drain pieces; transistor width W='
    for W, fail in [(99.99, False), (100.0, False), (100.01, True)]:
        emit('2.ACT.W2', f'nmos-W-{W:.2f}', nmos_cell(W=W), fail, W2+f'{W}')
    emit('2.ACT.W2', 'pmos-W-100.00', pmos_cell(W=100.0), False, W2+'100')
    emit('2.ACT.W2', 'pmos-W-100.01', pmos_cell(W=100.01), True, W2+'100.01')
    emit('2.ACT.W2', 'nmos-W-100.01-child-rotated', nmos_cell(W=100.01), True, W2+'100.01', hierarchy=True)
    emit('2.ACT.W2', 'nmos-W-2-long-drain-100.01', nmos_cell(sdr=100.01)+tap('p', act_right(sdr=100.01)+2.4, .2), True,
         'deck LENGTH also counts the 100.01-long drain edges of a W=2 transistor (deck-literal, not the PDF intent)')
    emit('2.ACT.W2', 'ptap-150-long-not-a-transistor', tap('p', 0, 0, h=150), False,
         'PTAP is not (NACT OR PACT) INTERACT ALLGATE')

    # ---------------- 2.ACT.E1 : ACT extension beyond gate 0.85 -------------------
    E1 = 'ENC NGATE_W/PGATE_W ACT < 0.85: uncontacted source length beyond the gate edge = '
    for e, fail in [(.84, True), (.85, False), (.86, False)]:
        emit('2.ACT.E1', f'nmos-sd-{e:.2f}', nmos_cell(sdl=e, cl=False), fail, E1+f'{e}')
    emit('2.ACT.E1', 'pmos-sd-0.84', pmos_cell(sdl=.84, cl=False), True, E1+'0.84')
    emit('2.ACT.E1', 'pmos-sd-0.85', pmos_cell(sdl=.85, cl=False), False, E1+'0.85')
    emit('2.ACT.E1', 'nmos-sd-0.84-child-rotated', nmos_cell(sdl=.84, cl=False), True, E1+'0.84', hierarchy=True)

    # ---------------- 2.ACT.E4 : PWELL enclosure of NMOS 1.4 ----------------------
    def nmos_nwell(d):
        x = 4.5+d
        return nmos_cell()+nwell_with_tap(x, -3, x+6, 5, max(x+2.2, 6.5), .2)
    E4 = 'ENC NMOS PWELL < 1.4; PWELL edge is the NWELL edge; NMOS ACT right edge to NWELL = '
    for d, fail in [(1.39, True), (1.4, False), (1.41, False)]:
        emit('2.ACT.E4', f'nwell-at-{d:.2f}', nmos_nwell(d), fail, E4+f'{d}')
    emit('2.ACT.E4', 'nwell-at-1.39-child-rotated', nmos_nwell(1.39), True, E4+'1.39', hierarchy=True)
    emit('2.ACT.E4', 'nwell-overlaps-nmos', nmos_nwell(-1.0), True, E4+'-1.0 (NWELL covers the drain)')
    emit('2.ACT.E4', 'drawn-pwell-1.0-merges-with-psub', nmos_cell()+[R(PW, -1, -1, 5.5, 3)], False,
         'PWELL = PWELLi OR PSUB: a tight drawn PWELL merges with the substrate, so enclosure is set by the extent')

    # ---------------- 2.ACT.E5 : PWELL enclosure of PTAP 0.5 ----------------------
    def ptap_nwell(d):
        x = 1.6+d
        return tap('p', 0, 0)+nwell_with_tap(x, -3, x+6, 4.6, x+2.2, 0)
    E5 = 'ENC PTAP PWELL < 0.5; PTAP ACT right edge to NWELL = '
    for d, fail in [(.49, True), (.5, False), (.51, False)]:
        emit('2.ACT.E5', f'nwell-at-{d:.2f}', ptap_nwell(d), fail, E5+f'{d}')
    emit('2.ACT.E5', 'nwell-at-0.49-child-rotated', ptap_nwell(.49), True, E5+'0.49', hierarchy=True)

    # ---------------- 2.ACT.T1 / T2 : tap within 60 um of the MOSFET --------------
    def far_pmos(D, tap_on=True):
        """Tall NTAP x 0..1.6, y 0..8; PMOS ACT (W=2, y 3..5) whose far edge is D from the tap."""
        xr = 1.6+D
        shapes = mos('p', xr-4.5, 3.0)+[R(NW, -2, -2, xr+2, 10)]+tap('p', -6.0, 3.2)
        if tap_on:
            shapes += tap('n', 0, 0, h=8)
        return shapes

    def far_nmos(D):
        xr = 1.6+D
        return mos('n', xr-4.5, 3.0)+tap('p', 0, 0, h=8)
    T1 = 'SD_ACT NOT (NTAP_A sized 2+29+29 um INSIDE OF NWELL): far PMOS ACT edge to tall NTAP edge = '
    for D, fail in [(10, False), (59.99, False), (60.0, False), (60.01, True), (70, True)]:
        emit('2.ACT.T1', f'pmos-at-{D:.2f}', far_pmos(D), fail, T1+f'{D}', uncertain=D in (60.0, 60.01))
    emit('2.ACT.T1', 'pmos-at-60.01-child-rotated', far_pmos(60.01), True, T1+'60.01', hierarchy=True, uncertain=True)
    emit('2.ACT.T1', 'pmos-cell-tapped', pmos_cell(), False, 'NTAP 2.4 um from the PMOS in the same NWELL')
    emit('2.ACT.T1', 'pmos-no-ntap', pmos_cell(ntap=False), True, 'no NTAP in the NWELL: all of SD_ACT remains')
    emit('2.ACT.T1', 'ntap-in-other-nwell', pmos_cell(ntap=False)+nwell_with_tap(8.5, -2, 14.5, 4, 10.7, .2), True,
         'NTAP sits in a separate NWELL 2 um away; sizing is INSIDE OF NWELL so it cannot reach')
    T2 = 'SD_ACT NOT (PTAP_A sized 2+29+29 um INSIDE OF PWELL): far NMOS ACT edge to tall PTAP edge = '
    for D, fail in [(10, False), (59.99, False), (60.0, False), (60.01, True), (70, True)]:
        emit('2.ACT.T2', f'nmos-at-{D:.2f}', far_nmos(D), fail, T2+f'{D}', uncertain=D in (60.0, 60.01))
    emit('2.ACT.T2', 'nmos-at-60.01-child-rotated', far_nmos(60.01), True, T2+'60.01', hierarchy=True, uncertain=True)
    emit('2.ACT.T2', 'nmos-cell-tapped', nmos_cell(), False, 'PTAP 2.4 um from the NMOS')
    emit('2.ACT.T2', 'nmos-no-ptap', mos('n', 0, 0), True, 'no PTAP at all')
    emit('2.ACT.T2', 'ptap-outside-nwell-ring', nwell_ring(0, 0)+tap('p', -4.0, 9.2)+mos('n', 5.75, 9.0), True,
         'NMOS in a PWELL island enclosed by an NWELL ring; PTAP outside the ring cannot grow through NWELL')

    # ---------------- 2.ACT.bad1 : ACT must have NSD or PSD -----------------------
    AB1 = 'NOT INTERACT ACT (NACT OR PACT) and ACT NOT (NACT OR PACT): '
    emit('2.ACT.bad1', 'act-without-implant', tap('p', -4.0, 0)+[R(ACT, 0, 0, 2, 2)]+cont(.7, .7), True, AB1+'bare contacted ACT')
    emit('2.ACT.bad1', 'act-half-implanted', tap('p', -4.0, 0)+[R(ACT, 0, 0, 4, 2), R(PSD, -.5, -.5, 2, 2.5)]+cont(.7, .7), True,
         AB1+'PSD covers only x<2 of a 4-long ACT')
    emit('2.ACT.bad1', 'act-implant-coincident', tap('p', -4.0, 0)+tap('p', 0, 0, imp=0), False,
         AB1+'PSD exactly equal to ACT covers it (6.PSD.E fires instead)')
    emit('2.ACT.bad1', 'butted-nsd-psd', tap('p', -4.0, 0)+[R(ACT, 0, 0, 4.6, 1.6), R(PSD, -.5, -.5, 2, 2.1), R(NSD, 2, -.5, 5.1, 2.1)]
         + cont(.5, .5)+cont(3.5, .5), False, AB1+'ACT fully covered by abutting PSD+NSD')
    emit('2.ACT.bad1', 'nmos', nmos_cell(), False, AB1+'implanted transistor')
    emit('2.ACT.bad1', 'act-without-implant-child-rotated', tap('p', -4.0, 0)+[R(ACT, 0, 0, 2, 2)]+cont(.7, .7), True,
         AB1+'bare contacted ACT', hierarchy=True)

    # ---------------- 2.ACT.bad2 / bad3 : wrong well -------------------------------
    AB2 = 'AND NMOS NWELL: '
    emit('2.ACT.bad2', 'nmos-inside-nwell', mos('n', 0, 0)+nwell_with_tap(-6, -2, 6.5, 4, -4.0, .2)+tap('p', -9.6, .2), True,
         AB2+'NMOS fully inside a tapped NWELL')
    emit('2.ACT.bad2', 'nmos-half-in-nwell', nmos_cell()+nwell_with_tap(2.5, -3, 10, 5, 6.6, .2), True, AB2+'NWELL covers x>=2.5 of the NMOS')
    emit('2.ACT.bad2', 'nmos-abuts-nwell', nmos_cell()+nwell_with_tap(4.5, -3, 11, 5, 7.0, .2), False, AB2+'NWELL edge on the ACT edge: zero-area AND')
    emit('2.ACT.bad2', 'nmos-in-pwell', nmos_cell(), False, AB2+'normal NMOS')
    emit('2.ACT.bad2', 'ntap-in-nwell', nwell_with_tap(0, 0, 6, 6, 2.2, 2.2)+tap('p', -4.0, 2.2), False, AB2+'N+ ACT without poly is not NMOS')
    emit('2.ACT.bad2', 'nmos-inside-nwell-child-rotated', mos('n', 0, 0)+nwell_with_tap(-6, -2, 6.5, 4, -4.0, .2)+tap('p', -9.6, .2),
         True, AB2+'as nmos-inside-nwell', hierarchy=True)
    AB3 = 'AND PMOS PWELL (PWELL = PWELLi OR (BULK NOT NWELL)): '
    emit('2.ACT.bad3', 'pmos-without-nwell', mos('p', 0, 0)+tap('p', -4.0, .2), True, AB3+'PMOS in the substrate')
    emit('2.ACT.bad3', 'pmos-half-outside-nwell', mos('p', 0, 0)+[R(NW, -6, -2, 2.5, 4)]+tap('n', -4.0, .2)+tap('p', -9.6, .2), True,
         AB3+'NWELL ends at x=2.5 inside the PMOS ACT')
    emit('2.ACT.bad3', 'pmos-in-nwell', pmos_cell(), False, AB3+'normal PMOS')
    emit('2.ACT.bad3', 'drawn-pwell-over-pmos', pmos_cell()+[R(PW, -.5, -.5, 5, 2.5)], True,
         AB3+'drawn PWELLi inside the NWELL is still PWELL')
    emit('2.ACT.bad3', 'ptap-in-pwell', tap('p', 0, 0), False, AB3+'P+ ACT without poly is not PMOS')
    emit('2.ACT.bad3', 'pmos-without-nwell-child-rotated', mos('p', 0, 0)+tap('p', -4.0, .2), True, AB3+'PMOS in the substrate', hierarchy=True)

    # ---------------- 3.PL1.W2 : max gate length 100 ------------------------------
    def long_gate(kind, L):
        """Taps at both ends (and an NTAP under the middle for PMOS) keep 2.ACT.T1/T2 quiet."""
        xr = act_right(L=L)
        if kind == 'n':
            return nmos_cell(L=L)+tap('p', xr+2.4, .2)
        return pmos_cell(L=L, margin=4.0)+tap('n', snap(xr/2-.8), -3.4)+tap('p', xr+6.0, .2)
    PW2 = 'NOT ALLGATE (INT (POLY1 INSIDE EDGE ACT) <= 100 REGION): gate length L='
    for L, fail in [(.5, False), (99.99, False), (100.0, False), (100.01, True)]:
        emit('3.PL1.W2', f'nmos-L-{L:.2f}', long_gate('n', L), fail, PW2+f'{L}')
    emit('3.PL1.W2', 'pmos-L-100.00', long_gate('p', 100.0), False, PW2+'100')
    emit('3.PL1.W2', 'pmos-L-100.01', long_gate('p', 100.01), True, PW2+'100.01')
    emit('3.PL1.W2', 'nmos-L-100.01-child-rotated', long_gate('n', 100.01), True, PW2+'100.01', hierarchy=True)

    # ---------------- 3.PL1.S1 : field poly space 0.6 -----------------------------
    def field_bars(g):
        b = 1.6+g
        return (tap('p', -4.0, 2.2)+poly_bar(P1, 0, 0, 1.6, 6, .5, 4.5)
                + poly_bar(P1, b, 0, b+1.6, 6, b+.5, .9))
    PS1 = 'OneSpace_check POLY1 0.6 NOT INTERACT ACT: two contacted field poly bars, gap '
    for g, fail in [(.59, True), (.6, False), (.61, False)]:
        emit('3.PL1.S1', f'field-gap-{g:.2f}', field_bars(g), fail, PS1+f'{g}')
    emit('3.PL1.S1', 'field-gap-0.59-child-rotated', field_bars(.59), True, PS1+'0.59', hierarchy=True)

    def two_fingers(kind, g):
        """Series stack: one ACT, gates at x 2.0 and 2.5+g, pads on opposite sides."""
        xr = 2.0+.5+g+.5+2.0
        shapes = [R(ACT, 0, 0, xr, 2), R(NSD if kind == 'n' else PSD, -.5, -.5, xr+.5, 2.5)]
        shapes += cont(.5, .7)+cont(xr-1.1, .7)
        g2 = 2.5+g
        shapes += [R(P1, 2.0, -.5, 2.5, 3.1), R(P1, 1.45-.5, 3.1, 3.05-.5, 4.7)]+cont(1.95-.5, 3.6)
        shapes += [R(P1, g2, -1.1, g2+.5, 2.5), R(P1, g2+.25-.8+.5, -2.7, g2+.25+.8+.5, -1.1)]+cont(g2+.25-.3+.5, -2.2)
        if kind == 'n':
            shapes += tap('p', -4.0, .2)
        else:
            shapes += [R(NW, -6, -2, xr+2, 4)]+tap('n', -4.0, .2)+tap('p', -9.6, .2)
        return shapes
    emit('3.PL1.S1', 'gap-0.59-over-act-is-S2', two_fingers('n', .59), False,
         'the 0.59 poly space region crosses ACT, so NOT INTERACT ACT drops it (3.PL1.S2 fires instead)')

    # ---------------- 3.PL1.S2 : gate to gate space 0.6 ---------------------------
    PS2 = 'OneSpace_check NGATE/PGATE 0.6: two gates on one ACT (series), gate gap '
    for g, fail in [(.59, True), (.6, False), (.61, False)]:
        emit('3.PL1.S2', f'nmos-gap-{g:.2f}', two_fingers('n', g), fail, PS2+f'{g}')
    emit('3.PL1.S2', 'pmos-gap-0.59', two_fingers('p', .59), True, PS2+'0.59')
    emit('3.PL1.S2', 'pmos-gap-0.60', two_fingers('p', .6), False, PS2+'0.60')
    emit('3.PL1.S2', 'nmos-gap-0.59-child-rotated', two_fingers('n', .59), True, PS2+'0.59', hierarchy=True)

    # ---------------- 3.PL1.S3 : field poly to ACT 0.5 ----------------------------
    def tap_bar(g, layer=P1, e=.5):
        """PTAP ACT x 0..1.6, y 0..1.6 (contact enclosure e toward the bar) + contacted bar at gap g right of it."""
        b = 1.6+g
        cx = 1.6-e-.6
        return tap('p', 0, 0, cx=cx)+poly_bar(layer, b, -5, b+1.6, 4, b+.5, -4.5)
    PS3 = 'TwoSpace_check ACT POLY1 0.5: PTAP ACT to contacted field poly bar gap '
    for g, fail in [(.49, True), (.5, False), (.51, False)]:
        emit('3.PL1.S3', f'tap-to-field-poly-{g:.2f}', tap_bar(g), fail, PS3+f'{g}')
    emit('3.PL1.S3', 'tap-to-field-poly-0.49-child-rotated', tap_bar(.49), True, PS3+'0.49', hierarchy=True)
    emit('3.PL1.S3', 'gate-pad-0.49-above-own-act', nmos_cell(pad_gap=.49), True, 'gate contact pad bottom edge 0.49 above its ACT')
    emit('3.PL1.S3', 'gate-pad-0.50-above-own-act', nmos_cell(pad_gap=.5), False, 'gate contact pad bottom edge 0.50 above its ACT')
    emit('3.PL1.S3', 'gate-crossing-act', nmos_cell(), False, 'plain transistor: gate edges cross ACT at 90 deg, end-cap 0.5')

    # ---------------- 3.PL1.S4 : transistor poly to transistor ACT 0.5 ------------
    PS4 = 'TwoSpace_check POLY1_TR TR_POLY1 0.5 (poly and ACT both part of transistors): '
    for g, fail in [(.49, True), (.5, False), (.51, False)]:
        emit('3.PL1.S4', f'own-gate-pad-{g:.2f}', nmos_cell(pad_gap=g), fail, PS4+f'gate pad {g} above its own ACT')

    def stacked(g):
        """Transistor A at origin (bottom end-cap 0.6) above transistor B whose ACT top is g below A's end-cap."""
        yb = -.6-g-2.0
        return (mos('n', 0, 0, endcap=.6)+mos('n', -4.0, yb, sdl=2.0, sdr=6.0, pad='bottom', imp=(.5, .5, .5, 1.0))
                + tap('p', -8.0, yb+.2))
    for g, fail in [(.49, True), (.5, False)]:
        emit('3.PL1.S4', f'endcap-to-other-transistor-act-{g:.2f}', stacked(g), fail,
             PS4+f"transistor A's gate end-cap {g} above transistor B's source/drain ACT")
    emit('3.PL1.S4', 'own-gate-pad-0.49-child-rotated', nmos_cell(pad_gap=.49), True, PS4+'gate pad 0.49', hierarchy=True)
    emit('3.PL1.S4', 'field-poly-bar-near-transistor-act', mos('n', 0, 0)+poly_bar(P1, -2.09, -3, -.49, 5, -1.59, -2.5)
         + tap('p', 6.9, .2), False, 'field bar (no ACT) 0.49 left of NMOS ACT: not POLY1_TR (3.PL1.S3 fires)')

    def pad_near_tap(g):
        return mos('n', 0, 0)+tap('p', 2.8, 4.7+g, w=4.6, cx=6.3)
    emit('3.PL1.S4', 'gate-pad-near-tap-act', pad_near_tap(.49), False,
         'gate pad 0.49 below a PTAP ACT: PTAP does not interact transistor poly, so not TR_POLY1 (3.PL1.S3 fires)')

    # ---------------- 3.PL1.O : end-cap 0.5 ---------------------------------------
    PO = 'INT (POLY1_ON_ACT NOT ACT) < 0.5 plus COIN EDGE POLY1_ON_ACT ACT: bottom end-cap '
    for e, fail in [(.49, True), (.5, False), (.51, False)]:
        emit('3.PL1.O', f'nmos-endcap-{e:.2f}', nmos_cell(endcap=e), fail, PO+f'{e}')
    emit('3.PL1.O', 'nmos-endcap-0-flush', nmos_cell(endcap=0), True, PO+'0 (poly edge coincident with ACT edge)')
    emit('3.PL1.O', 'nmos-poly-ends-inside-act', nmos_cell(endcap=-.5), False,
         'gate poly stops 0.5 inside ACT: no field piece and no coincident edge, so the deck reports nothing (deck-literal)', uncertain=True)
    emit('3.PL1.O', 'pmos-endcap-0.49', pmos_cell(endcap=.49), True, PO+'0.49')
    emit('3.PL1.O', 'pmos-endcap-0.50', pmos_cell(endcap=.5), False, PO+'0.50')
    emit('3.PL1.O', 'nmos-endcap-0.49-child-rotated', nmos_cell(endcap=.49), True, PO+'0.49', hierarchy=True)

    # ---------------- 3.PL1.ANT : poly area / gate area <= 200 --------------------
    def ant(kind, h, endcap=.5, x=0.):
        """W=2, L=0.5 gate (area 1.0) + 5-wide poly plate of height h: poly area 0.5*(3.0+endcap) + 5h."""
        shapes = mos(kind, x, 0, pad=None, endcap=endcap)
        shapes = [s for s in shapes if s[0] != P1]
        shapes += [R(P1, x+2.0, -endcap, x+2.5, 3.0), R(P1, x-.25, 3.0, x+4.75, 3.0+h)]+cont(x+1.95, 3.0+h-1.1)
        if kind == 'n':
            shapes += tap('p', x-4.0, .2)
        else:
            shapes += [R(NW, x-6, -2, x+6.5, 3.5)]+tap('n', x-4.0, .2)+tap('p', x-9.6, .2)
        return shapes
    PA = 'NET AREA RATIO NAREA/PAREA (whole poly on the net) over NGATE/PGATE (1.0 um2) > 200: ratio '
    emit('3.PL1.ANT', 'nmos-ratio-199.90', ant('n', 39.63), False, PA+'(1.75+198.15)/1 = 199.90')
    emit('3.PL1.ANT', 'nmos-ratio-200.00', ant('n', 39.65), False, PA+'(1.75+198.25)/1 = 200.00')
    emit('3.PL1.ANT', 'nmos-ratio-200.01', ant('n', 39.65, endcap=.52), True, PA+'(1.76+198.25)/1 = 200.01')
    emit('3.PL1.ANT', 'nmos-ratio-300', ant('n', 59.65), True, PA+'(1.75+298.25)/1 = 300')
    emit('3.PL1.ANT', 'pmos-ratio-200.00', ant('p', 39.65), False, PA+'200.00')
    emit('3.PL1.ANT', 'pmos-ratio-200.01', ant('p', 39.65, endcap=.52), True, PA+'200.01')
    emit('3.PL1.ANT', 'nmos-ratio-200.01-child-rotated', ant('n', 39.65, endcap=.52), True, PA+'200.01', hierarchy=True)
    shared = ant('n', 59.65)+mos('n', 12.0, 0)+[R(M1, 1.35, 3.0+59.65-1.7, 15.15, 3.0+59.65-.1), R(M1, 13.35, 3.0, 15.15, 3.0+59.65-.1)]
    emit('3.PL1.ANT', 'ratio-300-strapped-to-second-gate', shared, False,
         'the 300 um2 plate is MET1-strapped (CONNECT MET1 NAREA BY CONT) to a second W=2 gate: net ratio ~(300+4.4)/2 ~ 152',
         uncertain=True)

    # ---------------- 5.NSD.E / 6.PSD.E : implant enclosure of ACT 0.5 ------------
    for rule, kind, imp_layer in [('5.NSD.E', 'n', NSD), ('6.PSD.E', 'p', PSD)]:
        name = 'NSD' if kind == 'n' else 'PSD'
        why = f'(ACT INTERACT {name}) AND (EXPAND EDGE {name} INSIDE BY 0.5): {name} left margin over the tap ACT = '

        def implant_tap(m):
            if kind == 'n':
                return nwell_with_tap(-2, -2, 3.6, 3.6, 0, 0)[:1]+tap('n', 0, 0, imp=(m, .5, .5, .5))+tap('p', -6.0, 0)
            return tap('p', 0, 0, imp=(m, .5, .5, .5))
        for m, fail in [(.49, True), (.5, False), (.51, False)]:
            emit(rule, f'tap-margin-{m:.2f}', implant_tap(m), fail, why+f'{m}')
        emit(rule, 'tap-margin-0.49-child-rotated', implant_tap(.49), True, why+'0.49', hierarchy=True)
        cell = (lambda **kw: nmos_cell(**kw)) if kind == 'n' else (lambda **kw: pmos_cell(**kw))
        emit(rule, 'transistor-margin-0.49', cell(imp=(.49, .5, .5, .5)), True, f'{name} left margin over the transistor ACT 0.49')
        emit(rule, 'transistor-margin-0.50', cell(imp=.5), False, f'{name} margin 0.50 on all sides')
        emit(rule, 'butted-nsd-psd-on-one-act', tap('p', -4.0, 0)+[R(ACT, 0, 0, 4.6, 1.6), R(PSD, -.5, -.5, 2, 2.1), R(NSD, 2, -.5, 5.1, 2.1)]
             + cont(.5, .5)+cont(3.5, .5), True,
             f'the {name} edge at x=2 crosses the ACT, so the 0.5 inside band overlaps it (deck flags butted taps)')

    # ---------------- 5.NSD.bad1 / 6.PSD.bad1 : implant must cover something -----
    for rule, imp_layer in [('5.NSD.bad1', NSD), ('6.PSD.bad1', PSD)]:
        name = 'NSD' if imp_layer == NSD else 'PSD'
        why = f'NOT INTERACT {name} (ACT OR (POLY1 AND POLY2 AND {name} AND CAP) OR (POLY2 AND {name} AND RES)): '
        base = tap('p', -4.0, 0) if imp_layer == NSD else tap('n', -5.0, 0)+[R(NW, -7, -2, -1.4, 3.6)]+tap('p', -10.6, 0)
        emit(rule, 'floating-implant', base+[R(imp_layer, 0, 0, 2, 2)], True, why+'implant rectangle over nothing')
        emit(rule, 'over-act', nmos_cell() if imp_layer == NSD else pmos_cell(), False, why+'implant over transistor ACT')
        emit(rule, 'over-field-poly1-only', base+poly_bar(P1, 0, 0, 1.6, 6, .5, 4.5)+[R(imp_layer, -.5, -.5, 2.1, 3)], True,
             why+'implant over POLY1 only')
        emit(rule, 'over-poly2-without-res', base+poly_bar(P2, 0, 0, 1.6, 6, .5, 4.5)+[R(imp_layer, -.5, -.5, 2.1, 3)], True,
             why+'implant over POLY2 without RES')
        emit(rule, 'over-poly2-resistor', base+resistor(0, 0, implant=imp_layer), False, why+'implant over POLY2 AND RES')
        emit(rule, 'over-pip-cap', base+pip_cap(0, 0, implant=imp_layer), False, why+'implant over POLY1 AND POLY2 AND CAP')
        emit(rule, 'floating-implant-child-rotated', base+[R(imp_layer, 0, 0, 2, 2)], True, why+'floating', hierarchy=True)

    # ---------------- 7.CONT.S3 : S/D contact to gate 0.75 ------------------------
    CS3 = 'TwoSpace_check NGATE/PGATE ACT_ON_CONT 0.75: source contact edge to gate edge = '
    for g, fail in [(.74, True), (.75, False), (.76, False)]:
        emit('7.CONT.S3', f'nmos-{g:.2f}', nmos_cell(sdl=1.1+g), fail, CS3+f'{g}')
    emit('7.CONT.S3', 'pmos-0.74', pmos_cell(sdl=1.84), True, CS3+'0.74')
    emit('7.CONT.S3', 'pmos-0.75', pmos_cell(sdl=1.85), False, CS3+'0.75')
    emit('7.CONT.S3', 'nmos-0.74-child-rotated', nmos_cell(sdl=1.84), True, CS3+'0.74', hierarchy=True)

    # ---------------- 7.CONT.S4 : ACT contact to field poly 0.75 ------------------
    CS4 = 'TwoSpace_check POLY1_FIELD ACT_ON_CONT 0.75 (POLY1_FIELD = POLY1 NOT ALLGATE): '
    for e, fail in [(.24, True), (.25, False), (.26, False)]:
        emit('7.CONT.S4', f'tap-contact-to-field-poly-{e+.5:.2f}', tap_bar(.5, e=e), fail,
             CS4+f'field bar 0.5 from PTAP ACT, contact enclosure {e} toward it -> {e+.5:.2f} (7.CONT.E1 also fires)')
    emit('7.CONT.S4', 'tap-contact-to-field-poly-0.74-child-rotated', tap_bar(.5, e=.24), True, CS4+'0.74', hierarchy=True)

    def unimplanted(g, kind=None):
        shapes = mos('n', 0, 0, sdl=1.1+g, implant=False) if kind is None else mos('p', 0, 0, sdl=1.1+g)
        return shapes+tap('p', -4.0, .2)
    for g, fail in [(.74, True), (.75, False)]:
        emit('7.CONT.S4', f'poly-over-unimplanted-act-{g:.2f}', unimplanted(g), fail,
             CS4+f'poly over ACT without implant is not ALLGATE; contact {g} from it (7.CONT.S3 cannot fire)')
        emit('7.CONT.S4', f'pmos-shape-without-nwell-{g:.2f}', unimplanted(g, 'p'), fail,
             CS4+f'PACT outside NWELL is not PGATE; contact {g} from its poly')
    emit('7.CONT.S4', 'transistor-endcap-diagonal', nmos_cell(), False, 'plain NMOS: contact to end-cap corner ~1.14')

    # ---------------- 7.CONT.S6 : ACT contact to POLY2 1.0 ------------------------
    CS6 = 'TwoSpace_check POLY2 ACT_ON_CONT 1.0: PTAP contact to contacted POLY2 bar = '
    for g, fail in [(.49, True), (.5, False), (.51, False)]:
        emit('7.CONT.S6', f'poly2-gap-{g:.2f}', tap_bar(g, P2), fail, CS6+f'{g+.5:.2f} (POLY2 {g} from ACT, enclosure 0.5)')
    for e, fail in [(.39, True), (.4, False)]:
        emit('7.CONT.S6', f'contact-enclosure-{e:.2f}', tap_bar(.6, P2, e=e), fail, CS6+f'{e+.6:.2f} (POLY2 0.6 from ACT, enclosure {e})')
    emit('7.CONT.S6', 'poly2-gap-0.49-child-rotated', tap_bar(.49, P2), True, CS6+'0.99', hierarchy=True)

    # ---------------- 7.CONT.S7 : POLY1 contact to POLY2 resistor 1.25 ------------
    def poly1_by_resistor(d, e=.5, lvsd=True):
        x = 2+d
        return tap('p', -4.0, 4.2)+resistor(0, 0, lvsd=lvsd)+poly_bar(P1, x, 4.2, x+1.6, 5.8, x+e, 4.7)
    CS7 = 'TwoSpace_check POLY1_ON_CONT POLY2_RES 1.25 (POLY2_RES needs POLY2 AND LVSD AND RES): contact to resistor = '
    for d, e, fail in [(.74, .5, True), (.75, .5, False), (.76, .5, False), (.75, .49, True)]:
        emit('7.CONT.S7', f'poly1-gap-{d:.2f}-enc-{e:.2f}', poly1_by_resistor(d, e), fail, CS7+f'{d+e:.2f}')
    emit('7.CONT.S7', 'no-lvsd-not-a-resistor', poly1_by_resistor(.74, lvsd=False), False,
         'same 1.24 geometry without LVSD: POLY2 is not POLY2_RES (4.PL2.S2 still fires)')
    emit('7.CONT.S7', 'poly1-gap-0.74-child-rotated', poly1_by_resistor(.74), True, CS7+'1.24', hierarchy=True)

    # ---------------- 7.CONT.S8 : POLY2 contact to POLY1 1.25 ---------------------
    def poly2_by_poly1(d, e=.5, touch=False):
        b = 1.6+d
        shapes = tap('p', -4.0, 0)+[R(P2, 0, 0, 1.6, 1.6)]+cont(1.6-e-.6, .5)+poly_bar(P1, b, -4, b+1.6, 5.6, b+.5, -3.5)
        if touch:
            shapes += [R(P2, 0, 1.6, .8, 3.8), R(P2, 0, 3.0, b, 3.8)]
        return shapes
    CS8 = 'TwoSpace_check (CONT INTERACT (POLY2 NOT INTERACT POLY1)) POLY1 1.25: contact to POLY1 = '
    for d, e, fail in [(.74, .5, True), (.75, .5, False), (.76, .5, False), (.75, .49, True)]:
        emit('7.CONT.S8', f'poly1-gap-{d:.2f}-enc-{e:.2f}', poly2_by_poly1(d, e), fail, CS8+f'{d+e:.2f}')
    emit('7.CONT.S8', 'poly1-gap-0.74-child-rotated', poly2_by_poly1(.74), True, CS8+'1.24', hierarchy=True)
    emit('7.CONT.S8', 'poly2-touches-poly1-elsewhere', poly2_by_poly1(.74, touch=True), False,
         'same 1.24 contact, but the POLY2 arm abuts the POLY1 bar, so POLY2 INTERACT POLY1 and the contact is excluded', uncertain=True)
    emit('7.CONT.S8', 'pip-cap-top-plate-contact', tap('p', -4.0, 3.2)+pip_cap(0, 0), False,
         'contact on cap POLY2 (interacts POLY1) is excluded')

    # ---------------- 7.CONT.E4 : POLY2 enclosure of contact 0.5 ------------------
    def poly2_pad(e, outside=False):
        w = 1.1+e
        shapes = tap('p', -4.0, 0)+[R(P2, 0, 0, w, 1.6)]
        return shapes+cont(.5 if not outside else w-.3, .5)
    CE4 = 'Enc_check (CONT NOT INTERACT (POLY2 AND POLY1)) (POLY2 NOT RES) 0.5: right-side enclosure '
    for e, fail in [(.49, True), (.5, False), (.51, False)]:
        emit('7.CONT.E4', f'poly2-pad-enc-{e:.2f}', poly2_pad(e), fail, CE4+f'{e}')
    emit('7.CONT.E4', 'poly2-pad-enc-0.49-child-rotated', poly2_pad(.49), True, CE4+'0.49', hierarchy=True)
    emit('7.CONT.E4', 'contact-half-outside-poly2', poly2_pad(.5, outside=True), True, CE4+'-0.3 (contact crosses the POLY2 edge)')
    emit('7.CONT.E4', 'resistor-contact-enc-0.3', tap('p', -4.0, 4.2)+[R(P2, 0, 0, 2, 10), R(RES, -.5, -.5, 2.5, 10.5), R(LVSD, 0, 1.6, 2, 8.4)]
         + cont(.3, .5)+cont(.7, 8.9), False, 'contact 0.3 from POLY2 edge but POLY2 is inside RES: B = POLY2 NOT RES is empty there (14.PL2PR.E2 fires)')
    emit('7.CONT.E4', 'pip-cap-contact-enc-0.3', tap('p', -4.0, 3.2)+pip_cap(0, 0, p2_cont=(1.3, 3.7)), False,
         'contact 0.3 from the cap POLY2 edge but over POLY1 AND POLY2, so excluded (15.CAP.E2 fires)')

    # ---------------- SKEW / ACUTE / NONSIMPLE : drawn-geometry flags ------------
    octagon = P(M1, [(1, 0), (3, 0), (4, 1), (4, 3), (3, 4), (1, 4), (0, 3), (0, 1)])
    emit('SKEW', 'rectangle', [R(M1, 0, 0, 4, 4)], False, 'DRAWN SKEW: orthogonal edges only')
    emit('SKEW', 'octagon-45-degree', [octagon], False, 'DRAWN SKEW: 45-degree edges are allowed')
    emit('SKEW', 'slope-1-to-2-edge', [P(M1, [(0, 0), (4, 0), (4, 2), (0, 4)])], True, 'edge (4,2)-(0,4) has slope -1/2')
    emit('SKEW', 'near-45-off-by-one-grid', [P(M1, [(0, 0), (4, 0), (4, 2), (2, 4.01), (0, 4.01)])], True,
         'edge (4,2)-(2,4.01) is 0.01 off 45 degrees (PDF allows 0.01 deviation in 45-degree dimensions; deck DRAWN SKEW does not)')
    emit('SKEW', 'slope-edge-child-rotated', [P(M1, [(0, 0), (4, 0), (4, 2), (0, 4)])], True, 'slope -1/2 edge in a rotated child', hierarchy=True)
    emit('SKEW', 'slope-edge-on-key-layer', [P(KEY, [(0, 0), (4, 0), (4, 2), (0, 4)])], True,
         'DRAWN SKEW is expected to cover every input layer, including KEY (layer 1)', uncertain=True)
    emit('ACUTE', 'right-triangle-45', [P(M1, [(0, 0), (4, 0), (0, 4)])], True,
         'FLAG ACUTE YES: two 45-degree interior angles; expect a RUNTIME WARNING in the .rep, not a RULECHECK', uncertain=True)
    emit('ACUTE', 'octagon-135', [octagon], False, 'all interior angles 135 degrees')
    emit('ACUTE', 'rectangle', [R(M1, 0, 0, 4, 4)], False, 'all interior angles 90 degrees')
    emit('NONSIMPLE', 'bow-tie', [P(M1, [(0, 0), (4, 4), (4, 0), (0, 4)])], True,
         'FLAG NONSIMPLE YES: self-crossing polygon; expect "Non-simple boundary" in RUNTIME WARNINGS')
    emit('NONSIMPLE', 'orthogonal-self-crossing', [P(M1, [(0, 0), (4, 0), (4, 4), (2, 4), (2, -2), (0, -2)])], True,
         'edge x=2 crosses edge y=0 at (2,0)')
    emit('NONSIMPLE', 'self-touching-vertex', [P(M1, [(0, 0), (2, 0), (2, 2), (4, 2), (4, 4), (2, 4), (2, 2), (0, 2)])], True,
         'two squares sharing only vertex (2,2) in one boundary', uncertain=True)
    emit('NONSIMPLE', 'l-shape', [P(M1, [(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)])], False, 'simple L polygon')
    return result


def cases():
    return [case for case, _ in cases_with_meta()]
