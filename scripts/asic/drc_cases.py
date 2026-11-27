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

    # Enclosure edge cases with no Calibre evidence yet; expected values are a reading of the deck
    # and stay uncertain until the Calibre run. outer-inside-inner: the outer shape lies wholly inside
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
    return result
