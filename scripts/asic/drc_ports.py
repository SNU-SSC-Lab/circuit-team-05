"""Explicit geometry translations. Source semantics still need golden comparison.

No polygon bbox approximation is used for WITH WIDTH or electrical potential.
Those checks remain unported. Distances below are in micrometres.
"""
PORTS = {}

def add(name, kind, layers, value=None):
    if name in PORTS:
        raise ValueError('duplicate geometry port: '+name)
    PORTS[name] = {'kind': kind, 'layers': layers.split(), 'value': value}

# These are the source BODY's names, including OFFGRID_FVTN -> FVTP.
GRID_LAYERS = '''CHIPBOUNDARY KEY NWELL PWELL HNWELL HPWELL DWELL DNWELL DPWELL
ACT POLY1 POLY2 NSD PSD FVTN VTN VTP NHRI NPI PPI NDRIFT PDRIFT TGOX JISO TISO
ESD ESDI CONT MET1 VIA1 MET2 VIA2 MET3 PAD RES CAP HVMS HVMA BJT DIODE ESDD LVSD'''.split()
for layer in GRID_LAYERS:
    add('OFFGRID_'+layer, 'grid', 'FVTP' if layer == 'FVTN' else layer, 0.01)

for name, layers, value in [
    ('1.NWL.W', 'NWELL', 2.5), ('1.NWL.R', 'RESNW', 5),
    ('2.ACT.W1', 'NMOS PMOS', 1.6), ('2.ACT.W3', 'NTAP PTAP', .7),
    ('3.PL1.W1', 'POLY1_ON_ACT', .5), ('3.PL1.W3', 'POLY1_NOT_ACT', .5),
    ('4.PL2.W', 'POLY2', .6), ('5.NSD.W', 'NSD', .75), ('6.PSD.W', 'PSD', .75),
    ('8.MET1.W', 'MET1', .8), ('10.MET2.W', 'MET2', 1), ('12.MET3.W', 'MET3', 1.2),
    ('13.PAD.A', 'PAD', 80), ('15.CAP.W1', 'POLY1_CAP', 4.6),
    ('19.IO.W3', 'IO_GATE_POLY', .7)]:
    add(name, 'width', layers, value)
for name, layer, value in [
    ('2.ACT.S', 'ACT', 1), ('4.PL2.S1', 'POLY2', .75),
    ('5.NSD.S1', 'NSD', .75), ('6.PSD.S1', 'PSD', .75),
    ('7.CONT.S1', 'CONT', .6), ('9.VIA1.S1', 'VIA1', .8),
    ('11.VIA2.S1', 'VIA2', .8), ('13.PAD.S', 'PAD', 40)]:
    add(name, 'space', layer, value)
for name, layers, value in [
    ('4.PL2.S2', 'POLY2 POLY1', .75), ('4.PL2.S3', 'POLY2 ACT', .5),
    ('7.CONT.S2', 'POLY1_ON_CONT ACT', 1), ('7.CONT.S5', 'POLY2_ON_CONT ACT', 1)]:
    add(name, 'separation', layers, value)
for name, layers in [('9.VIA1.S', 'VIA1 CONT'), ('11.VIA2.S', 'VIA2 VIA1')]:
    add(name, 'separation_no_stack', layers, .6)
for name, layers, value in [
    ('2.ACT.E2', 'PMOS NWELL', 1.4), ('2.ACT.E3', 'NTAP NWELL', .5),
    ('7.CONT.E1', 'CONT ACT', .5), ('7.CONT.E2', 'CONT POLY1', .5),
    ('7.CONT.E3', 'CONT MET1', .6), ('13.PAD.E', 'PAD MET1 MET2 MET3', 2.5)]:
    add(name, 'enclosure', layers, value)
for name, layers in [
    ('1.NWL.bad1', 'NWELL CONTACTED_NTAP'), ('2.ACT.bad4', 'ACT CONT'),
    ('3.PL1.bad1', 'POLY1_NOT_POLY2 CONT'), ('4.PL2.bad1', 'POLY2 CONT'),
    ('8.MET1.bad1', 'MET1 CONT_OR_VIA1'), ('10.MET2.bad1', 'MET2 VIA1_OR_VIA2'),
    ('11.VIA2.bad1', 'VIA2 MET2_AND_MET3'), ('12.MET3.bad1', 'MET3 VIA2')]:
    add(name, 'not_interacting', layers)
for name, layers in [('5.NSD.O', 'NSD PSD'), ('6.PSD.O', 'PSD NSD'),
                      ('7.CONT.bad3', 'CONT ALLGATE')]:
    add(name, 'overlap', layers)
for name in ['3.PL1.bad3', '4.PL2.bad2']:
    add(name, 'overlap_except', 'POLY1 POLY2 CAP')
for name, layers in [('7.CONT.bad1', 'CONT MET1'), ('9.VIA1.bad1', 'VIA1 MET1_AND_MET2')]:
    add(name, 'uncovered', layers)
add('7.CONT.bad2', 'not_interacting', 'CONT ACTIVE_OR_POLY')
add('7.CONT.W', 'cut_size', 'CONT', [[.6, .6], [.6, 1.2]])
add('9.VIA1.W', 'cut_size', 'VIA1', [[.8, .8]])
add('11.VIA2.W', 'cut_size', 'VIA2', [[.8, .8]])
