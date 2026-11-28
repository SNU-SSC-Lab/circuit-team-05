"""Hand-specified source-rule fixtures, independent of executable PORTS values."""

def cases():
    result = []
    def emit(rule, label, shapes, fail, hierarchy=False, dbu=.001, raises=False):
        result.append(dict(rule=rule, label=label, shapes=shapes, fail=fail,
                           hierarchy=hierarchy, dbu=dbu, raises=raises))
    def rectangle(layer, x1, y1, x2, y2):
        return [layer, [x1, y1, x2, y2]]

    # Source-body layer assignments, not names guessed from the rule ID.
    grids = dict(CHIPBOUNDARY=0, KEY=1, NWELL=2, PWELL=3, HNWELL=4, HPWELL=5,
        DWELL=6, DNWELL=7, DPWELL=8, ACT=11, POLY1=12, POLY2=13, NSD=14,
        PSD=15, FVTN=17, VTN=18, VTP=19, NHRI=20, NPI=22, PPI=23, NDRIFT=24,
        PDRIFT=25, TGOX=27, JISO=28, TISO=29, ESD=52, ESDI=26, CONT=31,
        MET1=32, VIA1=33, MET2=34, VIA2=35, MET3=36, PAD=37, RES=51,
        CAP=53, HVMS=54, HVMA=55, BJT=56, DIODE=57, ESDD=59, LVSD=60)
    for name, layer in grids.items():
        for label, x, fail, hierarchy in [('on-grid', .01, False, False),
             ('positive-half-grid', .005, True, False), ('negative-half-grid', -.005, True, False),
             ('child-rotated', .005, True, True)]:
            emit('OFFGRID_'+name, label, [rectangle(layer, x, 0, 2+x, 2)], fail, hierarchy)
    emit('OFFGRID_FVTN', 'source-does-not-check-layer-16', [rectangle(16, .005, 0, 2.005, 2)], False)
    emit('OFFGRID_MET1', 'finer-dbu', [rectangle(32, .005, 0, 2.005, 2)], True, dbu=.0005)
    emit('OFFGRID_MET1', 'incompatible-dbu', [rectangle(32, 0, 0, 2, 2)], True, dbu=.003, raises=True)
    emit('OFFGRID_ESDI', 'source-marker-is-not-nodrc-masked',
         [rectangle(26, .005, 0, 2.005, 2), rectangle(58, -1, -1, 3, 3)], True)

    widths = [('1.NWL.W', 2, 2.5, ''), ('1.NWL.R', 2, 5, 'res'),
        ('2.ACT.W1', 11, 1.6, 'nmos'), ('2.ACT.W1', 11, 1.6, 'pmos'),
        ('2.ACT.W3', 11, .7, 'ntap'), ('2.ACT.W3', 11, .7, 'ptap'),
        ('3.PL1.W1', 12, .5, 'gatepoly'), ('3.PL1.W3', 12, .5, ''),
        ('4.PL2.W', 13, .6, ''), ('5.NSD.W', 14, .75, ''), ('6.PSD.W', 15, .75, ''),
        ('8.MET1.W', 32, .8, ''), ('10.MET2.W', 34, 1, ''), ('12.MET3.W', 36, 1.2, ''),
        ('13.PAD.A', 37, 80, ''), ('15.CAP.W1', 12, 4.6, 'cap'), ('19.IO.W3', 12, .7, 'esdpoly')]
    for rule, layer, threshold, context in widths:
        for label, delta, fail, hierarchy in [('below', -.01, True, False),
             ('boundary', 0, False, False), ('above', .01, False, False), ('child-rotated', -.01, True, True)]:
            width = round(threshold+delta, 4)
            shapes = [rectangle(layer, 0, 0, width, 200)]
            if context == 'res': shapes += [rectangle(51, 0, 0, width, 200)]
            if context in ['nmos', 'pmos', 'ntap', 'ptap']:
                implant = 14 if context in ['nmos', 'ntap'] else 15
                shapes += [rectangle(implant, 0, 0, width, 200)]
                if context in ['nmos', 'pmos']:
                    shapes += [rectangle(12, -2, 50, width+2, 52)]
                if context in ['pmos', 'ntap']:
                    shapes += [rectangle(2, -20, -20, width+20, 220)]
            if context in ['gatepoly', 'esdpoly']:
                shapes += [rectangle(11, -2, 50, width+2, 52)]
            if context == 'esdpoly': shapes += [rectangle(52, -1, -1, width+1, 201)]
            if context == 'cap': shapes += [rectangle(53, -1, 50, width+1, 52)]
            emit(rule, context+'-'+label, shapes, fail, hierarchy)
    emit('13.PAD.A', 'larger-than-80-is-minimum-rule', [rectangle(37, 0, 0, 90, 100)], False)
    emit('3.PL1.W1', 'whole-interacting-poly-has-narrow-tail', [
        [12, [[0, 0], [2, 0], [2, 4], [1.2, 4], [1.2, 8], [.8, 8], [.8, 4], [0, 4]]],
        rectangle(11, -1, 0, 3, 3)], True)
    emit('8.MET1.W', 'hole-keeps-a-thin-wall', [
        [32, [0, 0, 4, .4]], [32, [0, 3.6, 4, 4]], [32, [0, 0, .4, 4]], [32, [3.6, 0, 4, 4]]], True)
    emit('8.MET1.W', 'source-nodrc-mask', [rectangle(32, 0, 0, .4, 4), rectangle(58, -1, -1, 2, 5)], False)

    for rule, layer, threshold in [('2.ACT.S', 11, 1), ('4.PL2.S1', 13, .75),
         ('5.NSD.S1', 14, .75), ('6.PSD.S1', 15, .75), ('7.CONT.S1', 31, .6),
         ('9.VIA1.S1', 33, .8), ('11.VIA2.S1', 35, .8), ('13.PAD.S', 37, 40)]:
        for label, gap, fail, hierarchy in [('below', threshold-.01, True, False),
             ('boundary', threshold, False, False), ('above', threshold+.01, False, False),
             ('child-rotated', threshold-.01, True, True), ('touch-merges', 0, False, False)]:
            emit(rule, label, [rectangle(layer, 0, 0, 4, 40), rectangle(layer, 4+gap, 0, 8+gap, 40)], fail, hierarchy)

    for rule, first, second, threshold, context in [
         ('4.PL2.S2', 13, 12, .75, ''), ('4.PL2.S3', 13, 11, .5, ''),
         ('7.CONT.S2', 31, 11, 1, 'poly1'), ('7.CONT.S5', 31, 11, 1, 'poly2'),
         ('9.VIA1.S', 33, 31, .6, 'stack'), ('11.VIA2.S', 35, 33, .6, 'stack')]:
        for label, gap, fail, hierarchy in [('below', threshold-.01, True, False),
             ('boundary', threshold, False, False), ('above', threshold+.01, False, False),
             ('child-rotated', threshold-.01, True, True)]:
            shapes = [rectangle(first, 0, 0, 4, 40), rectangle(second, 4+gap, 0, 8+gap, 40)]
            if context in ['poly1', 'poly2']:
                shapes += [rectangle(12 if context == 'poly1' else 13, 0, 0, 4, 40)]
            emit(rule, label, shapes, fail, hierarchy)
        if context == 'stack':
            emit(rule, 'stacked', [rectangle(first, 0, 0, 4, 4), rectangle(second, 0, 0, 4, 4)], True)

    enclosures = [
         ('2.ACT.E2', 11, [2], 1.4, 'pmos'), ('2.ACT.E3', 11, [2], .5, 'ntap'),
         ('7.CONT.E1', 31, [11], .5, ''), ('7.CONT.E2', 31, [12], .5, ''),
         ('7.CONT.E3', 31, [32], .6, ''), ('13.PAD.E', 37, [32, 34, 36], 2.5, '')]
    for rule, first, others, threshold, context in enclosures:
        for label, delta, fail, hierarchy in [('below', -.01, True, False),
             ('boundary', 0, False, False), ('above', .01, False, False), ('child-rotated', -.01, True, True)]:
            margin = round(threshold+delta, 4)
            size = 80 if first == 37 else 2
            shapes = [rectangle(first, 0, 0, size, size)]
            shapes += [rectangle(layer, -margin, -margin, size+margin, size+margin) for layer in others]
            if context == 'pmos':
                shapes += [rectangle(15, 0, 0, size, size), rectangle(12, .5, -1, 1.5, size+1)]
            if context == 'ntap': shapes += [rectangle(14, 0, 0, size, size)]
            emit(rule, label, shapes, fail, hierarchy)
    emit('7.CONT.E2', 'contact-only-on-active-is-not-poly-enclosure',
         [rectangle(31, 0, 0, .6, .6), rectangle(11, -1, -1, 2, 2)], False)

    presence = [('2.ACT.bad4', 11, [31]), ('3.PL1.bad1', 12, [31]),
        ('4.PL2.bad1', 13, [31]), ('8.MET1.bad1', 32, [31]), ('8.MET1.bad1', 32, [33]),
        ('10.MET2.bad1', 34, [33]), ('10.MET2.bad1', 34, [35]),
        ('11.VIA2.bad1', 35, [34, 36]), ('12.MET3.bad1', 36, [35]),
        ('7.CONT.bad2', 31, [11]), ('7.CONT.bad2', 31, [12]), ('7.CONT.bad2', 31, [13])]
    for rule, first, others in presence:
        for label, x, fail, hierarchy in [('interacts', 1, False, False),
             ('absent', 10, True, False), ('child-rotated', 10, True, True), ('edge-touch', 4, False, False)]:
            shapes = [rectangle(first, 0, 0, 4, 4)]+[rectangle(layer, x, 1, x+1, 2) for layer in others]
            emit(rule, str(others)+'-'+label, shapes, fail, hierarchy)
    for label, x, fail in [('contacted', 1, False), ('uncontacted', 10, True)]:
        emit('1.NWL.bad1', label, [rectangle(2, 0, 0, 4, 4), rectangle(11, 1, 1, 2, 2),
             rectangle(14, 1, 1, 2, 2), rectangle(31, x, 1, x+1, 2)], fail)
    emit('3.PL1.bad1', 'poly2-exclusion', [rectangle(12, 0, 0, 2, 2), rectangle(13, 0, 0, 2, 2)], False)

    for rule, first, second in [('5.NSD.O', 14, 15), ('6.PSD.O', 15, 14),
                              ('3.PL1.bad3', 12, 13), ('4.PL2.bad2', 13, 12)]:
        for label, x, fail, hierarchy in [('separate', 3, False, False), ('overlap', 1, True, False),
             ('touch-is-not-area-overlap', 2, False, False), ('child-rotated', 1, True, True)]:
            emit(rule, label, [rectangle(first, 0, 0, 2, 2), rectangle(second, x, 0, x+2, 2)], fail, hierarchy)
        if rule.startswith(('3.', '4.')):
            emit(rule, 'capacitor-exception', [rectangle(first, 0, 0, 2, 2), rectangle(second, 0, 0, 2, 2), rectangle(53, 0, 0, 2, 2)], False)
    for label, x, fail in [('clear', 3, False), ('on-gate', 1, True)]:
        emit('7.CONT.bad3', label, [rectangle(31, 0, 0, 2, 2), rectangle(11, -1, -1, 6, 3),
             rectangle(14, -1, -1, 6, 3), rectangle(12, x, 0, x+2, 2)], fail)
    for rule, first, others in [('7.CONT.bad1', 31, [32]), ('9.VIA1.bad1', 33, [32, 34])]:
        for label, edge, fail in [('covered', 3, False), ('partial-coverage', 1.9, True), ('absent', -.1, True)]:
            emit(rule, label, [rectangle(first, 0, 0, 2, 2)]+[rectangle(layer, -1, -1, edge, 3) for layer in others], fail)
    for rule, layer, good in [('7.CONT.W', 31, .6), ('9.VIA1.W', 33, .8), ('11.VIA2.W', 35, .8)]:
        for label, width, height, fail in [('valid-square', good, good, False),
             ('small', good-.01, good, True), ('large', good+.01, good, True)]:
            emit(rule, label, [rectangle(layer, 0, 0, width, height)], fail)
        emit(rule, 'nonrectangular-bbox-is-insufficient', [[layer, [[0, 0], [good, 0], [good, good], [.1, good], [.1, .1], [0, .1]]]], True)
    emit('7.CONT.W', 'bar-vertical', [rectangle(31, 0, 0, .6, 1.2)], False)
    emit('7.CONT.W', 'bar-horizontal', [rectangle(31, 0, 0, 1.2, .6)], False)
    emit('7.CONT.W', 'bar-wrong-length', [rectangle(31, 0, 0, .6, 1.19)], True)

    # Deck `ENC a b < v ... OVERLAP` (DMACRO Enc_check): an inner shape partly outside the enclosing
    # layer fails; one that does not overlap it is not measured (other rules may fire). For 2.ACT.E3
    # NTAP is clipped to NWELL, so the partial case is an NTAP edge on the NWELL edge. Appended last
    # so earlier fixtures keep their numbered names.
    for rule, first, others, threshold, context in enclosures:
        size = 80 if first == 37 else 2
        margin = threshold+1
        for label, outer, fail in [('partial-overlap', [-margin, -margin, size/2, size+margin], True),
                                   ('outside-no-overlap', [size+5, -margin, 2*size+5, size+margin], False)]:
            shapes = [rectangle(first, 0, 0, size, size)]+[[layer, outer] for layer in others]
            if context == 'pmos':
                shapes += [rectangle(15, 0, 0, size, size), rectangle(12, .5, -1, 1.5, size+1)]
            if context == 'ntap': shapes += [rectangle(14, 0, 0, size, size)]
            emit(rule, label, shapes, fail)

    # Enclosure edge cases (0439-0450). The expected values were first a reading of the deck; the
    # 2026-11-28 Calibre run agreed with all of them (golden/drc-fixtures-20261128b in
    # verification/reliability). outer-inside-inner: the outer shape lies wholly inside
    # the inner one (for 13.PAD.E a hole in each metal under the PAD). No inner edge crosses an outer
    # edge or faces its inside, so ENC ... OVERLAP is read as not firing. Exception 2.ACT.E3: NTAP is
    # NACT AND NWELL, so NTAP equals the NWELL island and every edge coincides, which fired in Calibre
    # for 0429 (coincident edge) -> expected to fire. near-outside: the inner shape is outside the outer
    # one, closer than the rule value; facing outside edges are spacing, not enclosure -> expected not
    # to fire. For 2.ACT.E3 NTAP is empty there (no NACT inside NWELL), so it is vacuous.
    for rule, first, others, threshold, context in enclosures:
        size = 80 if first == 37 else 2
        margin = threshold+1
        if first == 37:
            low, high = -margin, size+margin
            island = [[low, low, high, 30], [low, 50, high, high], [low, 30, 30, 50], [50, 30, high, 50]]
        else:
            island = [[size/4, size/4, size*3/4, size*3/4]]
        gap = round(threshold-.2, 4)
        for label, outers, fail in [('outer-inside-inner', island, context == 'ntap'),
                                    ('near-outside', [[size+gap, -margin, 2*size+gap, size+margin]], False)]:
            shapes = [rectangle(first, 0, 0, size, size)]+[[layer, box] for layer in others for box in outers]
            if context == 'pmos':
                shapes += [rectangle(15, 0, 0, size, size), rectangle(12, .5, -1, 1.5, size+1)]
            if context == 'ntap': shapes += [rectangle(14, 0, 0, size, size)]
            emit(rule, label, shapes, fail)

    # ---- Kit ANT deck (Calibre/ANT/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_ANT.cal), all 12 RULECHECKs.
    # The 102 fixtures Calibre judged on 2026-11-28 (golden/ant-fixtures-20261128), moved from
    # drc_cases_pending_c1b.py when drc_antenna.py ported the deck. The code is that file's, with names
    # changed for this file's rules (no leading `_`), so every case_sha256 is the one Calibre read.
    # The rationale strings are the deck reading behind each `fail`; Calibre agreed with all but the two
    # ANT_06 equality cases, which are set to Calibre's verdict below (fail=True).
    NWELL, ACT, POLY1, POLY2, NSD, PSD = 2, 11, 12, 13, 14, 15
    CONT, MET1, VIA1, MET2, VIA2, MET3 = 31, 32, 33, 34, 35, 36
    CAP, DIODE = 53, 57

    def snap(v):
        return round(v + 0.0, 4)

    def R(layer, x1, y1, x2, y2):
        return [layer, [snap(x1), snap(y1), snap(x2), snap(y2)]]

    def P(layer, points):
        return [layer, [[snap(x), snap(y)] for x, y in points]]

    def ant(rule, label, shapes, fail, rationale, hierarchy=False, uncertain=False, calc=None):
        emit(rule, label, shapes, fail, hierarchy)

    L_GATE = .5

    def mos(wg, implant=NSD, marker=None, head=True):
        """NMOS-like gate at the origin: ACT x[-1.5,2.0] y[0,wg]; POLY1 x[0,0.5]; Ag = 0.5*wg."""
        s = [R(ACT, -1.5, 0, L_GATE + 1.5, wg)]
        if implant:
            s.append(R(implant, -2, -.5, L_GATE + 2, wg + .5))
        if marker:
            s.append(R(marker, -2, -.5, L_GATE + 2, wg + .5))
        if head:
            s += [R(POLY1, 0, -.6, L_GATE, wg + 2.0), R(POLY1, -.3, wg + 1.6, L_GATE + .3, wg + 2.7),
                  R(CONT, -.05, wg + 1.85, .55, wg + 2.45)]
        return s

    def diode(wg, w=1.0, h=1.0, dy=0.0, implant=NSD, marker=None):
        """Contacted ACT+implant region (ALL_SD) under the M1 pad; area w*h."""
        x1, x2, y1 = 1.5 - w / 2, 1.5 + w / 2, wg + 2.0 + dy
        s = [R(ACT, x1, y1, x2, y1 + h), R(implant, x1 - .1, y1 - .1, x2 + .1, y1 + h + .1),
             R(CONT, 1.2, wg + 2.2 + dy, 1.8, wg + 2.8 + dy)]
        if implant == PSD:
            s.append(R(NWELL, 0.0, y1 - 1, 3.0, y1 + h + 1))
        if marker:
            s.append(R(marker, x1 - .1, y1 - .1, x2 + .1, y1 + h + .1))
        return s

    def m1_wire(wg, H):
        return R(MET1, -.5, wg + 1.5, 2.5, wg + 1.5 + H)        # P = 2(3+H)

    def m1_pad(wg, x2=4.0):
        return [R(MET1, -.5, wg + 1.5, x2, wg + 3.5), R(VIA1, 2.9, wg + 2.1, 3.7, wg + 2.9)]

    def m2_pad(wg):
        return [R(MET2, 2.3, wg + 1.5, 8.0, wg + 3.5), R(VIA2, 6.6, wg + 2.1, 7.4, wg + 2.9)]

    def comb(layer, x0, y0, bus_h, fingers, l):
        """2-wide bus x[x0,x0+2] + `fingers` 2-wide fingers of length l at pitch 4; P = 2(2+bus_h) + 2*fingers*l."""
        pts = [(x0, y0), (x0 + 2, y0)]
        for i in range(fingers):
            yb, yt = y0 + 2 + 4 * i, y0 + 4 + 4 * i
            pts += [(x0 + 2, yb), (x0 + 2 + l, yb), (x0 + 2 + l, yt), (x0 + 2, yt)]
        pts += [(x0 + 2, y0 + bus_h), (x0, y0 + bus_h)]
        assert 4 * fingers + 2 <= bus_h
        return P(layer, pts)

    # ---------------- ANT_01: poly perimeter, no diode exemption
    rule = 'ANT_01'
    base = ('deck: CONNECT GATE POLY; NET AREA RATIO POLY GATE > 200 [PERIMETER(POLY)*0.25/AREA(GATE)]; '
            'GATE = (ACT AND NSD|PSD, NOT CAP|BJT|DIODE) AND (POLY1 OR POLY2). ')
    wg = 2.0
    ag = L_GATE * wg

    def poly_case(H, extra=(), implant=NSD, marker=None):
        s = [R(ACT, -1.5, 0, 2.0, wg)]
        if implant:
            s.append(R(implant, -2, -.5, 2.5, wg + .5))
        if marker:
            s.append(R(marker, -2, -.5, 2.5, wg + .5))
        return s + [R(POLY1, 0, -.6, L_GATE, -.6 + H)] + list(extra)
    for label, H, fail, h in [('below', 399.49, False, False), ('boundary', 399.5, False, False),
                              ('above', 399.51, True, False), ('child-rotated-above', 399.51, True, True),
                              ('far-below', 100, False, False), ('far-above', 800, True, False)]:
        p = 2 * (L_GATE + H)
        ratio = .25 * p / ag
        ant(rule, label, poly_case(H), fail,
             base + 'Ag=%g (0.5x%g); poly 0.5 x %g single rect, P=%g -> ratio %.4f vs 200.' % (ag, wg, H, snap(p), ratio),
             h, calc=dict(Ag=ag, P=snap(p), ratio=ratio, limit=200, perim_layer='POLY'))
    p = 2 * (L_GATE + 490.6)
    ant(rule, 'poly2-extension-counted', poly_case(100, [R(POLY2, 0, 90, L_GATE, 490)]), True,
         base + 'POLY1 100 long + overlapping POLY2 to y=490: POLY = POLY1 OR POLY2 merges, P=%g -> ratio %.4f.'
         % (snap(p), .25 * p / ag), uncertain=True, calc=dict(Ag=ag, P=snap(p), ratio=.25 * p / ag, limit=200))
    p = 2 * (L_GATE + 600)
    ant(rule, 'second-gate-halves-ratio',
         poly_case(600, [R(ACT, -1.5, 300, 2.0, 302), R(NSD, -2, 299.5, 2.5, 302.5)]), False,
         base + 'poly P=%g crosses two 0.5x2 gates: Ag=2 -> ratio %.4f (one gate alone would be %.4f).'
         % (snap(p), .25 * p / 2, .25 * p / ag), calc=dict(Ag=2.0, P=snap(p), ratio=.25 * p / 2, limit=200))
    ant(rule, 'no-implant-no-gate', poly_case(800, implant=None), False,
         base + 'ACT without NSD/PSD is not ACTIVE_ALL -> no GATE -> !!AREA(GATE)=0.')
    ant(rule, 'cap-marker-removes-gate', poly_case(800, marker=CAP), False,
         base + 'CAP over the active removes it from ACTIVE_ALL -> no GATE.')

    # ---------------- ANT_02_1 / ANT_03_1: MET1 perimeter
    rule = 'ANT_02_1'
    base = ('deck: CONNECT MET1 ALL_SD/POLY BY CONT, GATE-POLY; ACTIVE_DIODE1 = NET AREA ALL_SD >= 0.202; '
            'METAL1_WO_DIODE = MET1 on nets without diode; NET AREA RATIO METAL1_WO_DIODE GATE > 400 '
            '[PERIMETER*0.525/AREA(GATE)]. ')
    wg = 2.1
    ag = L_GATE * wg

    def m1_ratio(H):
        p = 2 * (3 + H)
        return snap(p), .525 * p / ag
    for label, H, fail, h in [('below', 396.99, False, False), ('boundary', 397, False, False),
                              ('above', 397.01, True, False), ('child-rotated-above', 397.01, True, True),
                              ('far-below', 200, False, False), ('ratio800-no-diode', 797, True, False)]:
        p, ratio = m1_ratio(H)
        ant(rule, label, mos(wg) + [m1_wire(wg, H)], fail,
             base + 'Ag=%g; M1 3 x %g single rect, P=%g -> ratio %.4f vs 400.' % (ag, H, p, ratio), h,
             calc=dict(Ag=ag, P=p, ratio=ratio, limit=400, perim_layer='MET1'))
    p, ratio = m1_ratio(797)
    dtxt = base + 'M1 P=%g, ratio %.4f (> 400 without diode). ' % (p, ratio)
    for label, d, fail, unc, why in [
            ('ratio800-ndiode-1.0', diode(wg), False, False, 'N+ 1x1 diode on the net -> WITH_DIODE, limit 400*1+2200'),
            ('ratio800-pdiode-1.0', diode(wg, implant=PSD), False, False, 'P+ 1x1 diode in NWELL -> counts too'),
            ('ratio800-diode-marker', diode(wg, marker=DIODE), True, True,
             'DIODE layer over the diode: EXTLAYER removes it from ACTIVE_ALL -> no diode'),
            ('ratio800-diode-0.200', diode(wg, .2, 1.0), True, False, 'diode area 0.200 < 0.202 -> not a diode'),
            ('ratio800-diode-0.202', diode(wg, .2, 1.01), False, True, 'diode area 0.202 >= 0.202 -> diode'),
            ('ratio800-diode-0.204', diode(wg, .2, 1.02), False, False, 'diode area 0.204 -> diode'),
            ('ratio800-two-diodes-0.12-each', diode(wg, .2, .6) + diode(wg, .2, .6, dy=8), False, True,
             'two 0.12 diodes on the net: NET AREA sums per net -> 0.24 >= 0.202')]:
        ant(rule, label, mos(wg) + [m1_wire(wg, 797)] + d, fail, dtxt + why + '.', uncertain=unc,
             calc=dict(Ag=ag, P=p, ratio=ratio, limit=400))
    ant(rule, 'ratio800-own-drain-as-diode',
         mos(wg) + [m1_wire(wg, 797), R(CONT, 1.0, .5, 1.6, 1.1), R(MET1, .9, .4, 2.5, wg + 1.6)], False,
         dtxt + 'M1 also contacts the transistor drain (ALL_SD 1.5x2.1): own S/D counts as diode.')
    jumper = [R(VIA1, 1.5, wg + 5.0, 2.3, wg + 5.8)] + \
        [R(ACT, 10, wg + 2, 11, wg + 3), R(NSD, 9.9, wg + 1.9, 11.1, wg + 3.1), R(CONT, 10.2, wg + 2.2, 10.8, wg + 2.8),
         R(MET1, 9.5, wg + 1.5, 14.5, wg + 6.5), R(VIA1, 12.9, wg + 5.0, 13.7, wg + 5.8),
         R(MET2, 1.0, wg + 4.5, 14.2, wg + 6.3)]
    ant(rule, 'ratio800-diode-only-via-m2', mos(wg) + [m1_wire(wg, 797)] + jumper, True,
         dtxt + 'diode reached only through an M2 jumper: at the M1 step (no MET2 in CONNECT) the gate net '
         'has no diode -> error (partial-net check).')
    ant(rule, 'ratio800-no-implant-no-gate', mos(wg, implant=None) + [m1_wire(wg, 797)], False,
         dtxt + 'no NSD on the transistor -> no GATE.')

    rule = 'ANT_03_1'
    base = ('deck: METAL1_WITH_DIODE; NET AREA RATIO ... > 0 [(PERIMETER(M1)*0.525 - AREA(GATE)*(AREA(DIODE)*400+2200))'
            '*!!AREA(GATE)] -> fail when 0.525*P/Ag > 400*Ad+2200. ')
    wg = .42
    ag = L_GATE * wg
    for label, H, d, ad, fail, h in [
            ('below', 516.99, diode(wg), 1.0, False, False), ('boundary', 517, diode(wg), 1.0, False, False),
            ('above', 517.01, diode(wg), 1.0, True, False), ('child-rotated-above', 517.01, diode(wg), 1.0, True, True),
            ('far-above', 1000, diode(wg), 1.0, True, False),
            ('diode-2.0-raises-limit', 517.01, diode(wg, 1.0, 2.0), 2.0, False, False)]:
        p = 2 * (3 + H)
        lim = 400 * ad + 2200
        ant(rule, label, mos(wg) + [m1_wire(wg, H)] + d, fail,
             base + 'Ag=%g, Ad=%g; M1 P=%g -> ratio %.4f vs limit %g; expr %.5f.'
             % (ag, ad, snap(p), .525 * p / ag, lim, .525 * p - ag * lim), h,
             calc=dict(Ag=ag, Ad=ad, P=snap(p), ratio=.525 * p / ag, limit=lim, perim_layer='MET1'))
    p = 2 * (3 + 517.01)
    ant(rule, 'diode-0.200-falls-to-ANT_02_1', mos(wg) + [m1_wire(wg, 517.01)] + diode(wg, .2, 1.0), False,
         base + 'diode 0.200 < 0.202 -> net is WO_DIODE, ANT_03_1 silent; ANT_02_1 fires (ratio %.4f).' % (.525 * p / ag))

    # ---------------- ANT_02_2 / ANT_03_2: MET2 perimeter
    def m2_case(wg, H, extra=(), via=True):
        s = mos(wg) + [m1_pad(wg)[0]] + ([m1_pad(wg)[1]] if via else [])
        return s + [R(MET2, 2.3, wg + 1.5, 4.3, wg + 1.5 + H)] + list(extra)   # P = 2(2+H)
    rule = 'ANT_02_2'
    base = ('deck: CONNECT MET2-MET1 BY VIA1 (+M1 to ALL_SD/POLY); METAL2_WO_DIODE; NET AREA RATIO METAL2_WO_DIODE GATE > 400 '
            '[PERIMETER*0.525/AREA(GATE)]; only MET2 perimeter counts. ')
    wg = 2.1
    ag = L_GATE * wg
    for label, H, fail, h in [('below', 397.99, False, False), ('boundary', 398, False, False),
                              ('above', 398.01, True, False), ('child-rotated-above', 398.01, True, True),
                              ('ratio800-no-diode', 798, True, False)]:
        p = 2 * (2 + H)
        ant(rule, label, m2_case(wg, H), fail,
             base + 'Ag=%g; M2 2 x %g, P=%g -> ratio %.4f.' % (ag, H, snap(p), .525 * p / ag), h,
             calc=dict(Ag=ag, P=snap(p), ratio=.525 * p / ag, limit=400, perim_layer='MET2'))
    ant(rule, 'ratio800-ndiode-1.0', m2_case(wg, 798, diode(wg)), False,
         base + 'ratio 800 with a 1x1 diode under the M1 pad -> WITH_DIODE (limit 2600).')
    ant(rule, 'ratio800-diode-0.200', m2_case(wg, 798, diode(wg, .2, 1.0)), True,
         base + 'ratio 800, diode area 0.200 -> not a diode.')
    ant(rule, 'ratio800-m2-floating', m2_case(wg, 798, via=False), False,
         base + 'no VIA1: M2 is not on the gate net.')
    cum = mos(wg) + [R(MET1, -.5, wg + 1.5, 4.0, wg + 1.5 + 295.5), R(VIA1, 2.9, wg + 2.1, 3.7, wg + 2.9),
                      R(MET2, 2.3, wg + 1.5, 4.3, wg + 1.5 + 298)]
    ant(rule, 'cumulative-m1-300-m2-300', cum, False,
         base + 'M1 4.5 x 295.5 (P=600, ratio 300) + M2 2 x 298 (P=600, ratio 300): per-layer check, '
         'deck does not sum layers -> neither ANT_02_1 nor ANT_02_2.', uncertain=True,
         calc=dict(Ag=ag, P_M1=600, P_M2=600, ratio_M1=300, ratio_M2=300, limit=400))
    rule = 'ANT_03_2'
    base = ('deck: METAL2_WITH_DIODE; expr (PERIMETER(M2)*0.525 - AREA(GATE)*(AREA(DIODE)*400+2200))*!!AREA(GATE) > 0. ')
    wg = .42
    ag = L_GATE * wg
    for label, H, fail, h in [('below', 517.99, False, False), ('boundary', 518, False, False),
                              ('above', 518.01, True, False), ('child-rotated-above', 518.01, True, True)]:
        p = 2 * (2 + H)
        ant(rule, label, m2_case(wg, H, diode(wg)), fail,
             base + 'Ag=%g, Ad=1; M2 P=%g -> ratio %.4f vs 2600; expr %.5f.'
             % (ag, snap(p), .525 * p / ag, .525 * p - ag * 2600), h,
             calc=dict(Ag=ag, Ad=1.0, P=snap(p), ratio=.525 * p / ag, limit=2600, perim_layer='MET2'))
    ant(rule, 'diode-0.200-falls-to-ANT_02_2', m2_case(wg, 518.01, diode(wg, .2, 1.0)), False,
         base + 'diode 0.200 -> WO_DIODE; ANT_03_2 silent, ANT_02_2 fires.')

    # ---------------- ANT_02_3 / ANT_03_3: MET3 perimeter, thickness 0.870
    def m3_case(wg, m3, extra=(), via2=True):
        s = mos(wg) + m1_pad(wg) + [m2_pad(wg)[0]] + ([m2_pad(wg)[1]] if via2 else [])
        return s + [m3] + list(extra)
    rule = 'ANT_02_3'
    base = ('deck: CONNECT MET3-MET2 BY VIA2, MET2-MET1 BY VIA1; METAL3_WO_DIODE; NET AREA RATIO > 400 '
            '[PERIMETER(M3)*0.870/AREA(GATE)]. ')
    wg = 3.48
    ag = L_GATE * wg
    for label, H, fail, h in [('below', 397.99, False, False), ('boundary', 398, False, False),
                              ('above', 398.01, True, False), ('child-rotated-above', 398.01, True, True),
                              ('ratio800-no-diode', 798, True, False)]:
        p = 2 * (2 + H)
        ant(rule, label, m3_case(wg, R(MET3, 6.0, wg + 1.5, 8.0, wg + 1.5 + H)), fail,
             base + 'Ag=%g; M3 2 x %g, P=%g -> ratio %.4f.' % (ag, H, snap(p), .87 * p / ag), h,
             calc=dict(Ag=ag, P=snap(p), ratio=.87 * p / ag, limit=400, perim_layer='MET3'))
    ant(rule, 'ratio800-ndiode-1.0', m3_case(wg, R(MET3, 6.0, wg + 1.5, 8.0, wg + 799.5), diode(wg)), False,
         base + 'ratio 800 with a 1x1 diode under the M1 pad -> WITH_DIODE.')
    ant(rule, 'ratio800-m3-floating', m3_case(wg, R(MET3, 6.0, wg + 1.5, 8.0, wg + 799.5), via2=False), False,
         base + 'no VIA2: M3 not on the gate net.')
    cum = mos(wg) + [R(MET1, -.5, wg + 1.5, 4.0, wg + 1.5 + 575.5), R(VIA1, 2.9, wg + 2.1, 3.7, wg + 2.9),
                      R(MET2, 2.3, wg + 1.5, 8.0, wg + 1.5 + 574.3), R(VIA2, 6.6, wg + 2.1, 7.4, wg + 2.9),
                      R(MET3, 6.0, wg + 1.5, 8.0, wg + 1.5 + 348)]
    ant(rule, 'cumulative-m1-m2-m3-350-each', cum, False,
         base + 'Ag=1.74; M1 P=1160 (0.525 -> 350), M2 P=1160 (350), M3 P=700 (0.87 -> 350): each layer below 400, '
         'sum 1050; deck is per-layer -> no ANT_02_x.', uncertain=True,
         calc=dict(Ag=ag, P_M1=1160, P_M2=1160, P_M3=700, ratio_each=350, limit=400))
    rule = 'ANT_03_3'
    base = ('deck: METAL3_WITH_DIODE; expr (PERIMETER(M3)*0.870 - AREA(GATE)*(AREA(DIODE)*8000+30000))*!!AREA(GATE) > 0 '
            '(the deck uses the comment\'s "M6 single layer" formula for MET3). M3 is a comb (bus 2x402 + 100 fingers) '
            'so P = 808 + 200*l. ')
    wg = .87
    ag = L_GATE * wg
    for label, l, fail, h in [('below', 90.95, False, False), ('boundary', 90.96, False, False),
                              ('above', 90.97, True, False), ('child-rotated-above', 90.97, True, True)]:
        p = 808 + 200 * l
        ant(rule, label, m3_case(wg, comb(MET3, 6.0, wg + 1.5, 402, 100, l), diode(wg)), fail,
             base + 'Ag=%g, Ad=1 -> limit 38000; l=%g, P=%g -> ratio %.4f; expr %.5f.'
             % (ag, l, snap(p), .87 * p / ag, .87 * p - ag * 38000), h,
             calc=dict(Ag=ag, Ad=1.0, P=snap(p), ratio=.87 * p / ag, limit=38000, perim_layer='MET3'))
    wg2 = 3.48
    ant(rule, 'ratio4000-uses-m6-formula',
         m3_case(wg2, comb(MET3, 6.0, wg2 + 1.5, 402, 100, 35.96), diode(wg2)), False,
         base + 'Ag=1.74, Ad=1, P=8000 -> ratio 4000: above the M1-5 formula (2600) but below the deck\'s 38000.',
         calc=dict(Ag=1.74, Ad=1.0, P=8000, ratio=4000, limit=38000, perim_layer='MET3'))
    ant(rule, 'diode-0.200-falls-to-ANT_02_3', m3_case(wg, comb(MET3, 6.0, wg + 1.5, 402, 100, 90.97),
                                                        diode(wg, .2, 1.0)), False,
         base + 'diode 0.200 -> WO_DIODE; ANT_03_3 silent, ANT_02_3 fires.')

    # ---------------- ANT_04: contact-on-poly area
    rule = 'ANT_04'
    base = ('deck: CONT_ANTENNA = CONT AND POLY; CONNECT CONT_ANTENNA POLY BY CONT, GATE-POLY; '
            'NET AREA RATIO CONT_ANTENNA CONT GATE > 10 [AREA(CONT_ANTENNA)/AREA(GATE)]. ')
    wg = .72
    ag = L_GATE * wg

    def cont_case(n_full, last_h=None, half_off=0):
        n = n_full + (1 if last_h else 0)
        s = [R(ACT, -1.5, 0, 2.0, wg), R(NSD, -2, -.5, 2.5, wg + .5), R(POLY1, 0, -.6, L_GATE, wg + 2.0),
             R(POLY1, -.3, wg + 1.6, .8 + 1.2 * (max(n, half_off) - 1), wg + 3.9)]
        for i in range(n_full):
            s.append(R(CONT, -.05 + 1.2 * i, wg + 1.85, .55 + 1.2 * i, wg + 2.45))
        if last_h:
            i = n_full
            s.append(R(CONT, -.05 + 1.2 * i, wg + 1.85, .55 + 1.2 * i, wg + 1.85 + last_h))
        for i in range(half_off):
            s.append(R(CONT, -.05 + 1.2 * i, wg + 3.6, .55 + 1.2 * i, wg + 4.2))
        return s
    for label, nf, lh, fail, h in [('below', 9, .59, False, False), ('boundary-10', 10, None, False, False),
                                   ('above', 9, .61, True, False), ('child-rotated-above', 9, .61, True, True),
                                   ('far-above-15', 15, None, True, False), ('far-below-3', 3, None, False, False)]:
        area = .36 * nf + (.6 * lh if lh else 0)
        ant(rule, label, cont_case(nf, lh), fail,
             base + 'Ag=%g; %d contacts 0.6x0.6%s on the gate poly: area %.4f -> ratio %.4f vs 10.'
             % (ag, nf, ' + one 0.6x%g' % lh if lh else '', area, area / ag), h,
             calc=dict(Ag=ag, A=snap(area), ratio=area / ag, limit=10))
    ant(rule, 'half-off-poly-counts-overlap-only', cont_case(7, None, 5), False,
         base + '7 full contacts + 5 contacts half over the poly edge: AND area 2.52+0.90=3.42 -> 9.5 '
         '(whole contacts would give 12).', calc=dict(Ag=ag, A=3.42, ratio=9.5, limit=10))

    # ---------------- ANT_05_x / ANT_06_0x: via area
    def via_row(L, x0, wg, n, last_h=None):
        s = [R(L, x0 + 1.6 * i, wg + 2.1, x0 + 1.6 * i + .8, wg + 2.9) for i in range(n)]
        if last_h:
            s.append(R(L, x0 + 1.6 * n, wg + 2.1, x0 + 1.6 * n + .8, wg + 2.1 + last_h))
        return s, x0 + 1.6 * (n if last_h else n - 1) + .8 + .5

    def via_array(L, x0, wg, n_full, odd_h=None, cols=12):
        s = []
        for k in range(n_full):
            i, j = k % cols, k // cols
            s.append(R(L, x0 + 1.6 * i, wg + 2.1 + 1.6 * j, x0 + 1.6 * i + .8, wg + 2.9 + 1.6 * j))
        if odd_h:
            i, j = n_full % cols, n_full // cols
            s.append(R(L, x0 + 1.6 * i, wg + 2.1 + 1.6 * j, x0 + 1.6 * i + .5, wg + 2.1 + 1.6 * j + odd_h))
        rows = (n_full + (1 if odd_h else 0) + cols - 1) // cols
        return s, x0 + 1.6 * (cols - 1) + .8 + .5, wg + 2.1 + 1.6 * (rows - 1) + .8 + .5

    def v1_case(wg, vias, xe, ye=None, extra=()):
        ye = ye if ye is not None else wg + 3.5
        return mos(wg) + [R(MET1, -.5, wg + 1.5, xe, ye), R(MET2, 2.5, wg + 1.5, xe, ye)] + vias + list(extra)

    def v2_case(wg, vias, xe, ye=None, extra=()):
        ye = ye if ye is not None else wg + 3.5
        return mos(wg) + m1_pad(wg) + [R(MET2, 2.3, wg + 1.5, xe, ye), R(MET3, 4.5, wg + 1.5, xe, ye)] + vias + list(extra)

    for vrule, L, x0, mk, nm, conn in [('ANT_05_1', VIA1, 3.0, v1_case, 'VIA1', 'CONNECT VIA1 MET1 (no MET2)'),
                                       ('ANT_05_2', VIA2, 5.0, v2_case, 'VIA2', 'CONNECT VIA2 MET2, MET2-MET1 BY VIA1')]:
        base = ('deck: %s; %s_WO_DIODE; NET AREA RATIO > 20 [!AREA(DIODE)*!!AREA(GATE)*AREA(%s_WO_DIODE)/AREA(GATE)]. '
                % (conn, nm, nm))
        wg = .64
        ag = L_GATE * wg
        for label, nf, lh, d, fail, h in [
                ('below', 9, .79, (), False, False), ('boundary-10', 10, None, (), False, False),
                ('above', 9, .81, (), True, False), ('child-rotated-above', 9, .81, (), True, True),
                ('far-above-15', 15, None, (), True, False), ('far-below-5', 5, None, (), False, False),
                ('15-with-diode-1.0', 15, None, diode(wg), False, False),
                ('15-with-diode-0.200', 15, None, diode(wg, .2, 1.0), True, False),
                ('15-with-diode-0.202', 15, None, diode(wg, .2, 1.01), False, True)]:
            vias, xe = via_row(L, x0, wg, nf, lh)
            area = .64 * nf + (.8 * lh if lh else 0)
            ant(vrule, label, mk(wg, vias, xe, extra=d), fail,
                 base + 'Ag=%g; %d vias 0.8x0.8%s: area %.4f -> ratio %.4f vs 20%s.'
                 % (ag, nf, ' + one 0.8x%g' % lh if lh else '', area, area / ag,
                    '; diode %s' % ('present -> exempt' if d and not fail else 'too small -> not a diode') if d else ''),
                 h, uncertain=('0.202' in label),
                 calc=dict(Ag=ag, A=snap(area), ratio=area / ag, limit=20))

    for vrule, L, x0, mk, nm, fallback in [('ANT_06_01', VIA1, 3.0, v1_case, 'VIA1', 'ANT_05_1'),
                                           ('ANT_06_02', VIA2, 5.0, v2_case, 'VIA2', 'ANT_05_2')]:
        base = ('deck: %s_WITH_DIODE; expr (AREA(%s_WITH_DIODE) - AREA(GATE)*(AREA(DIODE)*83.33+75))*!!AREA(GATE) > 0. '
                % (nm, nm))
        wg = 1.0
        ag = L_GATE * wg
        lim = ag * (83.33 * 1.0 + 75)
        # boundary: exact arithmetic equals the limit, but Calibre fired (124): 83.33 is not binary-exact.
        for label, nf, oh, fail, h in [('below', 123, .88, False, False), ('boundary', 123, .89, True, False),
                                       ('above', 123, .90, True, False), ('child-rotated-above', 123, .90, True, True),
                                       ('far-above-132', 132, None, True, False), ('far-below-50', 50, None, False, False)]:
            vias, xe, ye = via_array(L, x0, wg, nf, oh)
            area = .64 * nf + (.5 * oh if oh else 0)
            ant(vrule, label, mk(wg, vias, xe, ye, diode(wg)), fail,
                 base + 'Ag=0.5, Ad=1 -> allowed via area %.5f; %d vias%s: area %.4f; expr %.5f.'
                 % (lim, nf, ' + one 0.5x%g' % oh if oh else '', area, area - lim), h,
                 calc=dict(Ag=ag, Ad=1.0, A=snap(area), allowed=lim))
        wg = .64
        vias, xe, ye = via_array(L, x0, wg, 50)
        lim2 = .32 * (83.33 * .3 + 75)
        ant(vrule, 'coefficient-83.33-literal-50-vias', mk(wg, vias, xe, ye, diode(wg, .5, .6)), True,
             base + 'Ag=0.32, Ad=0.30 -> allowed %.6f (83.33 literal; 250/3 would give exactly 32); '
             '50 vias = 32.0 -> exceeds by %.5f.' % (lim2, 32 - lim2), uncertain=True,
             calc=dict(Ag=.32, Ad=.3, A=32.0, allowed=lim2))
        wg = 1.0
        vias, xe, ye = via_array(L, x0, wg, 132)
        ant(vrule, 'no-diode-goes-to-%s' % fallback, mk(wg, vias, xe, ye), False,
             base + '132 vias without diode: %s_WITH_DIODE empty -> silent; %s fires.' % (nm, fallback))

    # ---- Batch 1 of the unported DRC deck rules (SPEC 0021): metal spacing by width class, via
    # enclosure by width class, via arrays, pad pitch. The 228 fixtures Calibre judged on 2026-11-28
    # (golden/drc-fixtures-20261128c), moved from drc_cases_pending_c1b.py when drc_ports.py ported the
    # rules. The code is that file's, with names changed for this file's rules (no leading `_`, no import:
    # floor(s / sqrt 2 * 100) is int(s / 2 ** .5 * 100), the same float), so every case_sha256 is the one
    # Calibre read. The rationale strings are the deck reading behind each `fail`; Calibre agreed with all.
    PAD = 37

    def c1b(rule, label, shapes, fail, rationale, hierarchy=False, uncertain=False):
        emit(rule, label, shapes, fail, hierarchy)

    def diag(s):
        """Grid offsets d (dx=dy) just inside / outside Euclidean corner distance s."""
        d_in = int(s / 2 ** .5 * 100) / 100
        d_out = snap(d_in + .01)
        assert d_in * 2 ** .5 < s <= d_out * 2 ** .5
        return snap(d_in), d_out

    def plate_tail(layer):
        """20x20 plate (width >= 10) with a 2-wide, 20-long tail on its right side."""
        return P(layer, [(0, 0), (20, 0), (20, 9), (40, 9), (40, 11), (20, 11), (20, 20), (0, 20)])

    # metal spacing S1 (both narrow) and S2 (one or both wide)
    metals = [('8.MET1', MET1, .8, 1.0, 'MET1'), ('10.MET2', MET2, 1.0, 1.2, 'MET2'),
              ('12.MET3', MET3, 1.0, 1.2, 'MET3')]
    n, length = 2.0, 40
    for prefix, L, s1, s2, name in metals:
        S1, S2 = prefix + '.S1', prefix + '.S2'
        gm = snap((s1 + s2) / 2)
        un = '%sUN10 = WITH WIDTH %s < 10' % (name, name)
        up = '%sUP10 = WITH WIDTH %s >= 10' % (name, name)
        r1 = 'deck: OneSpace_check %sUN10 %g -> EXT %sUN10 < %g ABUT < 90 SINGULAR REGION; %s. ' % (name, s1, name, s1, un)
        r2 = 'deck: TwoSpace_check %sUP10 %s %g -> EXT %sUP10 %s < %g ABUT < 90 SINGULAR REGION; %s. ' % (name, name, s2, name, name, s2, up)

        def pair(w1, w2, g):
            return [R(L, 0, 0, w1, length), R(L, w1 + g, 0, w1 + g + w2, length)]

        # ---- S1: both lines narrow
        for label, g, fail, h in [('below', s1 - .01, True, False), ('boundary', s1, False, False),
                                  ('above', s1 + .01, False, False), ('child-rotated', s1 - .01, True, True),
                                  ('touch-merges', 0, False, False)]:
            c1b(S1, label, pair(n, n, snap(g)), fail,
                 r1 + 'two %g-wide x %g lines, gap %g vs %g.' % (n, length, snap(g), s1), h)
        for w, fail in [(9.99, True), (10.0, False), (10.01, False)]:
            c1b(S1, 'both-width-%.2f-gap-below' % w, pair(w, w, snap(s1 - .01)), fail,
                 r1 + 'both lines %.2f wide at gap %g: %s. (S2 also fires for >=10.)'
                 % (w, snap(s1 - .01), 'both UN10 -> error' if fail else 'both UP10 -> not in S1 layer'),
                 uncertain=(w == 10.0))
        c1b(S1, 'narrow-to-wide-gap-below', pair(20, n, snap(s1 - .01)), False,
             r1 + '20-wide (UP10) next to 2-wide at gap %g: only one UN10 polygon -> no S1 pair (S2 fires).' % snap(s1 - .01))
        for label, g, fail in [('notch-below', snap(s1 - .01), True), ('notch-boundary', s1, False)]:
            pts = [(0, 0), (4 + g, 0), (4 + g, 20), (2 + g, 20), (2 + g, 2), (2, 2), (2, 20), (0, 20)]
            c1b(S1, label, [P(L, pts)], fail,
                 r1 + 'single narrow U polygon, notch %g: single-layer EXT measures notches.' % g)
        d_in, d_out = diag(s1)
        for label, d, fail in [('corner-diagonal-below', d_in, True), ('corner-diagonal-above', d_out, False)]:
            c1b(S1, label, [R(L, 0, 0, n, length), R(L, n + d, length + d, 2 * n + d, 2 * length + d)], fail,
                 r1 + 'corner-to-corner dx=dy=%g -> Euclidean %.4f vs %g.' % (d, d * 2 ** .5, s1))
        c1b(S1, 'corner-touch-singular', [R(L, 0, 0, n, length), R(L, n, length, 2 * n, 2 * length)], True,
             r1 + 'two narrow lines touching at one vertex: SINGULAR keyword.', uncertain=True)
        c1b(S1, 'narrow-tail-of-wide-below', [plate_tail(L), R(L, 25, 11 + s1 - .01, 45, 13 + s1 - .01)], True,
             r1 + 'T: 20x20 plate + 2-wide tail; 2-wide wire parallel to the tail at gap %g, 5 um from plate. '
             'If WITH WIDTH keeps only the >=10 region, the tail is UN10 -> S1 error; '
             'if it selects whole polygons, no S1 error (S2 would fire instead).' % snap(s1 - .01), uncertain=True)

        # ---- S2: one or both lines wide
        def wide_pair(g, w=20, w2=n):
            return [R(L, 0, 0, w, length), R(L, w + g, 0, w + g + w2, length)]
        for label, g, fail, h in [('below', s2 - .01, True, False), ('boundary', s2, False, False),
                                  ('above', s2 + .01, False, False), ('child-rotated', s2 - .01, True, True)]:
            c1b(S2, label, wide_pair(snap(g)), fail,
                 r2 + '20-wide plate and 2-wide line, gap %g vs %g.' % (snap(g), s2), h)
        c1b(S2, 'wide-to-wide-below', wide_pair(snap(s2 - .01), 20, 20), True,
             r2 + 'two 20-wide plates, gap %g.' % snap(s2 - .01))
        for w, fail in [(9.99, False), (10.0, True), (10.01, True)]:
            c1b(S2, 'width-%.2f-gap-mid' % w, wide_pair(gm, w), fail,
                 r2 + '%.2f-wide line + 2-wide line at gap %g (S1 %g passes): %s.'
                 % (w, gm, s1, 'UP10 -> error' if fail else 'UN10 -> S2 not applicable'),
                 uncertain=(w == 10.0))
        c1b(S2, 'facing-short-side-gap-mid',
             [R(L, 0, 0, 40, 10), R(L, 40 + gm, -15, 42 + gm, 25)], True,
             r2 + '40x10 plate (width 10); line faces its 10-long end at gap %g.' % gm, uncertain=True)
        c1b(S2, 'short-parallel-run-gap-mid',
             [R(L, 0, 0, 20, 20), R(L, 20 + gm, 19, 22 + gm, 59)], True,
             r2 + 'parallel run only 1 um at gap %g; deck has no run-length condition.' % gm)
        d_in, d_out = diag(s2)
        for label, d, fail in [('corner-diagonal-below', d_in, True), ('corner-diagonal-above', d_out, False)]:
            c1b(S2, label, [R(L, 0, 0, 20, 20), R(L, 20 + d, 20 + d, 22 + d, 60 + d)], fail,
                 r2 + 'plate corner to line corner dx=dy=%g -> Euclidean %.4f vs %g.' % (d, d * 2 ** .5, s2))
        g = snap(s2 - .01)
        pts = [(0, 0), (20 + g, 0), (20 + g, 40), (10 + g, 40), (10 + g, 10), (10, 10), (10, 40), (0, 40)]
        c1b(S2, 'wide-notch-below', [P(L, pts)], True,
             r2 + 'single U polygon, arms 10 wide, notch %g: two-layer EXT of a polygon against itself '
             '(UP10 edge vs MET edge across the notch).' % g, uncertain=True)
        c1b(S2, 'single-wide-plate', [R(L, 0, 0, 20, length)], False,
             r2 + 'one plate alone: UP10 edges coincide with its own MET edges, nothing faces.')
        c1b(S2, 'tee-alone', [plate_tail(L)], False,
             r2 + 'T alone: checks no spurious result at the UP10/UN10 cut where the tail joins the plate.',
             uncertain=True)
        c1b(S2, 'narrow-tail-of-wide-gap-mid', [plate_tail(L), R(L, 25, 11 + gm, 45, 13 + gm)], False,
             r2 + 'wire parallel to the 2-wide tail at gap %g, 5 um from the plate: region-based WITH WIDTH '
             '-> tail is UN10 -> no S2 (S1 %g passes).' % (gm, s1), uncertain=True)

    # via arrays (9.VIA1.S2, 11.VIA2.S2)
    for rule, L, name in [('9.VIA1.S2', VIA1, 'VIA1'), ('11.VIA2.S2', VIA2, 'VIA2')]:
        base = ('deck: ARRAY_%s = SIZE (SIZE %s BY 0.8) BY 2.4 UNDEROVER; ARRAY%s = %s AND ARRAY_%s; '
                'EXT ARRAY%s < 0.8 ABUT < 90 SINGULAR REGION. Grown block span = 0.8N + s(N-1) + 1.6 '
                'must exceed 4.8 in both directions to survive UNDEROVER. '
                % (name, name, name[-1], name, name, name[-1]))

        def array(nx, ny, s, x0=0, y0=0):
            p = .8 + s
            return [R(L, x0 + i * p, y0 + j * p, x0 + i * p + .8, y0 + j * p + .8)
                    for i in range(nx) for j in range(ny)]

        def span(N, s):
            return .8 * N + s * (N - 1) + 1.6
        for label, nx, ny, s, fail, h, unc in [
                ('3x3-below', 3, 3, .79, True, False, False), ('3x3-boundary', 3, 3, .8, False, False, False),
                ('3x3-above', 3, 3, .81, False, False, False), ('3x3-child-rotated', 3, 3, .79, True, True, False),
                ('2x2-below', 2, 2, .79, False, False, False), ('3x2-below', 3, 2, .79, False, False, False),
                ('1x5-below', 1, 5, .79, False, False, False), ('3x3-s0.41', 3, 3, .41, True, False, False),
                ('3x3-s0.40-degenerate', 3, 3, .40, False, False, True), ('3x3-s0.39', 3, 3, .39, False, False, False),
                ('4x4-s0.30', 4, 4, .30, True, False, False)]:
            sx, sy = span(nx, s), span(ny, s)
            kept = min(sx, sy) > 4.8 + 1e-9
            verdict = ('kept, s < 0.8 -> error' if kept and s < .8 else 'kept, s >= 0.8 -> clean' if kept
                       else 'not kept (span <= 4.8) -> no S2 result')
            c1b(rule, label, array(nx, ny, s), fail,
                 base + '%dx%d at s=%g: grown block %.2f x %.2f, %s. (%s.S1 fires for s<0.8 regardless.)'
                 % (nx, ny, s, sx, sy, verdict, rule.split('.S2')[0]), h, uncertain=unc)
            assert fail == (kept and s < .8), label
        for label, g, fail, unc in [('outlier-0.79-from-3x3', .79, True, True), ('outlier-0.80-from-3x3', .8, False, False)]:
            shapes = array(3, 3, .8) + [R(L, 4.0 + g, 1.6, 4.8 + g, 2.4)]
            c1b(rule, label, shapes, fail,
                 base + '3x3 at s=0.8 (array) + one extra via %g from it: the restored array region reaches 0.8 '
                 'beyond the array vias, so ARRAY keeps a %s sliver of the extra via -> EXT %s.'
                 % (g, '0.01-wide' if fail else 'no', 'error at %g' % g if fail else 'clean'), uncertain=unc)

    # via enclosure by the width class of the metal
    specs = [('9.VIA1.E1', VIA1, MET1, MET2, False), ('9.VIA1.E2', VIA1, MET1, MET2, True),
             ('9.VIA1.E3', VIA1, MET2, MET1, False), ('9.VIA1.E4', VIA1, MET2, MET1, True),
             ('11.VIA2.E1', VIA2, MET2, MET3, False), ('11.VIA2.E2', VIA2, MET2, MET3, True),
             ('11.VIA2.E3', VIA2, MET3, MET2, False), ('11.VIA2.E4', VIA2, MET3, MET2, True)]
    lname = {VIA1: 'VIA1', VIA2: 'VIA2', MET1: 'MET1', MET2: 'MET2', MET3: 'MET3'}
    for rule, V, M, O, wide in specs:
        mset = '%s%s10' % (lname[M], 'UP' if wide else 'UN')
        base = ('deck: Enc_check %s %s 0.6 -> ENC %s %s < 0.6 ABUT < 90 SINGULAR OVERLAP REGION; %s = WITH WIDTH %s %s 10. '
                'Other metal %s encloses the via by 1.0 (narrow) so its own E rule stays clean. '
                % (lname[V], mset, lname[V], mset, mset, lname[M], '>=' if wide else '<', lname[O]))

        def at(x, y, extra):
            return [R(V, x, y, x + .8, y + .8), R(O, x - 1, y - 1, x + 1.8, y + 1.8)] + extra
        for label, e, fail, h in [('below', .59, True, False), ('boundary', .6, False, False),
                                  ('above', .61, False, False), ('child-rotated', .59, True, True)]:
            if wide:
                m = R(M, -e, -e, 20 - e, 20 - e)
                txt = 'via at the corner of a 20x20 plate, enclosure %g on two sides.' % e
            else:
                m = R(M, -e, -e, .8 + e, .8 + e)
                txt = 'metal = via grown by %g (%.2f wide, narrow).' % (e, .8 + 2 * e)
            c1b(rule, label, at(0, 0, [m]), fail, base + txt, h)
        for w in (9.99, 10.0, 10.01):
            fail = (w >= 10) == wide
            c1b(rule, 'width-%.2f-side-below' % w, at(0, 0, [R(M, -.59, -5, -.59 + w, 20)]), fail,
                 base + '%.2f x 25 metal, via 0.59 from its left edge: metal is %s -> %s.'
                 % (w, 'UP10' if w >= 10 else 'UN10', 'error' if fail else 'checked by the other E rule'),
                 uncertain=(w == 10.0))
        if wide:
            c1b(rule, 'center-of-wide', at(0, 0, [R(M, -10, -10, 10.8, 10.8)]), False,
                 base + 'via in the middle of a 20.8 plate.')
            c1b(rule, 'partially-outside', at(0, 0, [R(M, -.6, -19.6, 19.4, .4)]), True,
                 base + 'via crosses the plate top edge (0.4 inside): OVERLAP.')
        else:
            c1b(rule, 'line-end-below', at(0, 0, [R(M, -.6, -.59, 1.4, 20)]), True,
                 base + '2-wide line, via 0.59 from the line end, 0.6 on the sides.')
            c1b(rule, 'partially-outside', at(0, 0, [R(M, -.6, -.6, 1.4, .4)]), True,
                 base + 'via crosses the metal top edge (0.4 inside): OVERLAP.')
        # T-shape: 20x20 plate x[-20,0] + 2-wide tail x[0,20]; the WITH WIDTH cut is x=0, y in [-1,1].
        tee = P(M, [(-20, -10), (0, -10), (0, -1), (20, -1), (20, 1), (0, 1), (0, 10), (-20, 10)])
        tt = 'T: plate x[-20,0] y[-10,10] + tail x[0,20] y[-1,1]; region-based WITH WIDTH cuts at x=0. '
        c1b(rule, 'straddles-wide-narrow-cut', at(-.4, -.4, [tee]), True,
             base + tt + 'via centred on the cut: the %s edge at x=0 runs through the via (OVERLAP).' % mset,
             uncertain=True)
        if wide:
            for label, x, fail in [('plate-0.59-from-cut', -1.39, True), ('plate-0.60-from-cut', -1.4, False)]:
                c1b(rule, label, at(x, -.4, [tee]), fail,
                     base + tt + 'via inside the plate, %g from the cut; real plate edges are >0.8 away (corner).'
                     % snap(-x - .8), uncertain=True)
        else:
            for label, x, fail in [('tail-0.59-from-cut', .59, True), ('tail-0.60-from-cut', .6, False)]:
                c1b(rule, label, at(x, -.4, [tee]), fail,
                     base + tt + 'via inside the tail (0.6 to its sides), %g from the cut edge.' % x,
                     uncertain=True)

    # 13.PAD.P
    rule = '13.PAD.P'
    base = ('deck: PITCHPAD = SIZE PAD BY 19.99 OVERUNDER; A = PITCHPAD NOT PAD; PAD INTERACT A. '
            'Two pads bridge when grown by 19.99 they overlap/abut (gap <= 39.98); this is a space test, '
            'not a centre-pitch test (PDF: pitch >= 120 with 80x80 pads; Assura does not check it). ')

    def pad(x, y, s=80):
        return R(PAD, x, y, x + s, y + s)
    for label, g, fail, h, unc in [('gap-50', 50, False, False, False), ('gap-40-pitch-120', 40, False, False, False),
                                   ('gap-39.99-pitch-119.99', 39.99, False, False, True),
                                   ('gap-39.98-grown-abut', 39.98, True, False, True),
                                   ('gap-39.97', 39.97, True, False, False), ('gap-30', 30, True, False, False),
                                   ('child-rotated-gap-39.97', 39.97, True, True, False)]:
        c1b(rule, label, [pad(0, 0), pad(80 + g, 0)], fail,
             base + 'two 80x80 pads, gap %g (pitch %g).' % (g, 80 + g), h, uncertain=unc)
    c1b(rule, 'row-of-3-pitch-120', [pad(0, 0), pad(120, 0), pad(240, 0)], False, base + 'three pads at pitch 120.')
    c1b(rule, 'diagonal-corner-10', [pad(0, 0), pad(90, 90)], False,
         base + 'corner-to-corner offset 10/10: grown squares only overlap at a corner, UNDEROVER restores '
         'two squares -> no bridge (13.PAD.S fires).', uncertain=True)
    c1b(rule, 'partial-projection-gap-30', [pad(0, 0), pad(110, 70)], True,
         base + 'gap 30 with 10 um projection overlap: bridge 30 x 10 survives.')
    c1b(rule, 'single-pad-notch-30',
         [P(PAD, [(0, 0), (190, 0), (190, 80), (110, 80), (110, 40), (80, 40), (80, 80), (0, 80)])], True,
         base + 'one U-shaped PAD polygon with a 30-wide notch: OVERUNDER fills the notch -> PAD interacts.',
         uncertain=True)
    c1b(rule, 'pads-100-pitch-120-gap-20', [pad(0, 0, 100), pad(120, 0, 100)], True,
         base + '100x100 pads at pitch 120 (gap 20): fails by space although pitch = 120.')
    c1b(rule, 'pads-70-pitch-110-gap-40', [pad(0, 0, 70), pad(110, 0, 70)], False,
         base + '70x70 pads at pitch 110 (gap 40): deck passes although pitch < 120 (13.PAD.A fires).')
    return result
