"""KLayout port of the kit's separate Calibre ANT deck: all 12 RULECHECKs, per net, as the deck states them.

Deck: Calibre/ANT/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_ANT.cal of NSPL_05CMOS_PDK_260820, unmodified,
sha256 ANT_SOURCE_SHA. Line numbers below are that file's. Calibre agreement: verification/reliability
(golden/ant-fixtures-20261128, `reliability.py check`).

How one RULECHECK is evaluated (`DRC INCREMENTAL CONNECT YES`, deck line 69):
1. Derived layers as deck lines 61-67 (POLY = POLY1 OR POLY2, GATE, ALL_SD, CONT_ANTENNA).
2. The protection diode layer `ACTIVE_DIODE* = NET AREA ALL_SD >= 0.202` uses only the CONNECTs written
   above it in the RULECHECK's block (`diode_connect`): ALL_SD polygons whose net has >= 0.202 um2 of
   ALL_SD in total.
3. Every CONNECT of the block (`connect`) then defines the net of the ratio. `*_WO_DIODE` / `*_WITH_DIODE`
   (`NET AREA RATIO layer ACTIVE_DIODE* ==0` / `>0`) keep the measured layer on nets without / with
   diode area.
4. The bracketed expression is computed per net in double precision in the deck's operand order, with
   AREA = dbu^2 / precision^2 and PERIMETER = dbu / precision (precision = 1/dbu, the deck's
   PRECISION 1000 for 0.001 um GDS), and the net fires when it is > the constraint. `!!AREA(GATE)`
   short-circuits: a net without gate area gives 0. Equality does not fire, except where the double
   arithmetic itself lands above the limit (ANT_06 with the inexact coefficient 83.33, as Calibre did).

KLayout's `antenna_check` is not used: it has no per-RULECHECK connectivity (diode area is summed
before poly joins the net in ANT_02/03_1/05), no `!AREA(diode)` factor, no way to measure only the top
layer's perimeter of a multi-layer net, and its own ratio arithmetic would decide the equality cases.

`evaluate()` and RULES need no KLayout (unit tests run it with plain Python); `check()` needs pya.
"""
import json
import os
from pathlib import Path

ANT_SOURCE = 'Calibre/ANT/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_ANT.cal'
ANT_SOURCE_SHA = '80dc257e6778121ab9a61a444d0e82c79999dc785d8e6aa5a6a2a5318c7b94b5'
# Deck lines 20-58: GDS layer numbers (datatype 0, as drc_geometry.py reads the DRC deck layers).
LAYERS = dict(ACT=11, POLY1=12, POLY2=13, NSD=14, PSD=15, CONT=31, MET1=32, VIA1=33, MET2=34, VIA2=35,
              MET3=36, CAP=53, BJT=56, DIODE=57)
DIODE_MIN_AREA = 0.202  # `ACTIVE_DIODE* = NET AREA ALL_SD >= 0.202`, um2

# `CONNECT a b BY c` -> (a, b, c); `CONNECT a b` -> (a, b, None). 'DIODE' is the block's ACTIVE_DIODE*.
GATE_POLY = ('GATE', 'POLY', None)
M1_SD = ('MET1', 'ALL_SD', 'CONT')
M1_DIODE = ('MET1', 'DIODE', 'CONT')
M1_POLY = ('MET1', 'POLY', 'CONT')
M2_M1 = ('MET2', 'MET1', 'VIA1')
M3_M2 = ('MET3', 'MET2', 'VIA2')
V1_M1 = ('VIA1', 'MET1', None)
V2_M2 = ('VIA2', 'MET2', None)
CA_POLY = ('CONT_ANTENNA', 'POLY', 'CONT')


def _rule(line, expression_line, connect, layer, measure, kind, limit, diode_connect=None, select=None,
          factor=None, k=None, c=None):
    return dict(line=line, expression_line=expression_line, connect=connect, layer=layer, measure=measure,
                kind=kind, limit=limit, diode_connect=diode_connect, select=select, factor=factor, k=k, c=c)


# line: RULECHECK header; expression_line: the bracketed expression. kind:
#   ratio      [!!AREA(GATE)*(X * factor / AREA(GATE))]                (factor None: X / AREA(GATE))
#   no_diode   [!AREA(DIODE)*(!!AREA(GATE)*(AREA(X) / AREA(GATE)))]
#   diode      [((X * factor) - (AREA(GATE) * ((AREA(DIODE) * k) + c))) * !!AREA(GATE)]  (factor None: X)
RULES = {
    # 70-71 DISCONNECT; CONNECT GATE POLY. 75 NET AREA RATIO POLY GATE >200
    'ANT_01': _rule(73, 76, [GATE_POLY], 'POLY', 'perimeter', 'ratio', 200, factor=0.25),
    # 80-86: diode from M1-ALL_SD only; METAL1_WO_DIODE ==0. 90 NET AREA RATIO METAL1_WO_DIODE GATE >400
    'ANT_02_1': _rule(88, 91, [M1_SD, M1_DIODE, M1_POLY, GATE_POLY], 'MET1', 'perimeter', 'ratio', 400,
                      diode_connect=[M1_SD], select='without', factor=0.525),
    # 95-102: diode through MET2-MET1, before POLY joins. 106 >400
    'ANT_02_2': _rule(104, 107, [M2_M1, M1_SD, M1_DIODE, M1_POLY, GATE_POLY], 'MET2', 'perimeter', 'ratio', 400,
                      diode_connect=[M2_M1, M1_SD], select='without', factor=0.525),
    # 111-119. 123 >400, thickness factor 0.870
    'ANT_02_3': _rule(121, 124, [M3_M2, M2_M1, M1_SD, M1_DIODE, M1_POLY, GATE_POLY], 'MET3', 'perimeter',
                      'ratio', 400, diode_connect=[M3_M2, M2_M1, M1_SD], select='without', factor=0.870),
    # 128-134: METAL1_WITH_DIODE >0. 140-141 >0: diode area * 400 + 2200
    'ANT_03_1': _rule(136, 141, [M1_SD, M1_DIODE, M1_POLY, GATE_POLY], 'MET1', 'perimeter', 'diode', 0,
                      diode_connect=[M1_SD], select='with', factor=0.525, k=400, c=2200),
    # 145-152: POLY joins before the diode area. 158-159
    'ANT_03_2': _rule(154, 159, [M2_M1, M1_POLY, M1_SD, M1_DIODE, GATE_POLY], 'MET2', 'perimeter', 'diode', 0,
                      diode_connect=[M2_M1, M1_POLY, M1_SD], select='with', factor=0.525, k=400, c=2200),
    # 164-172. 178-179: the deck uses diode area * 8000 + 30000 (the comment's M6 formula) for MET3
    'ANT_03_3': _rule(174, 179, [M3_M2, M2_M1, M1_POLY, M1_SD, M1_DIODE, GATE_POLY], 'MET3', 'perimeter', 'diode',
                      0, diode_connect=[M3_M2, M2_M1, M1_POLY, M1_SD], select='with', factor=0.870, k=8000, c=30000),
    # 183-185: CONNECT CONT_ANTENNA POLY BY CONT; GATE-POLY. 189-190 NET AREA RATIO CONT_ANTENNA CONT GATE >10
    'ANT_04': _rule(187, 190, [CA_POLY, GATE_POLY], 'CONT_ANTENNA', 'area', 'ratio', 10),
    # 194-201: CONNECT VIA1 MET1 (no MET2). 205-206 >20
    'ANT_05_1': _rule(203, 206, [V1_M1, M1_SD, M1_DIODE, M1_POLY, GATE_POLY], 'VIA1', 'area', 'no_diode', 20,
                      diode_connect=[V1_M1, M1_SD], select='without'),
    # 210-218. 222-223 >20
    'ANT_05_2': _rule(220, 223, [V2_M2, M2_M1, M1_SD, M1_DIODE, M1_POLY, GATE_POLY], 'VIA2', 'area', 'no_diode', 20,
                      diode_connect=[V2_M2, M2_M1, M1_SD], select='without'),
    # 227-234: POLY joins before the diode area. 246-247 >0: diode area * 83.33 + 75
    'ANT_06_01': _rule(236, 247, [V1_M1, M1_POLY, M1_SD, M1_DIODE, GATE_POLY], 'VIA1', 'area', 'diode', 0,
                       diode_connect=[V1_M1, M1_POLY, M1_SD], select='with', k=83.33, c=75),
    # 251-259. 271-272
    'ANT_06_02': _rule(261, 272, [V2_M2, M2_M1, M1_POLY, M1_SD, M1_DIODE, GATE_POLY], 'VIA2', 'area', 'diode', 0,
                       diode_connect=[V2_M2, M2_M1, M1_POLY, M1_SD], select='with', k=83.33, c=75),
}


def evaluate(rule, measured, gate_area, diode_area):
    """Deck expression of `rule` for one net, in um / um2 (doubles, deck operand order).

    measured: PERIMETER or AREA of the RULECHECK's layer on the net before the WO/WITH diode selection.
    The RULECHECK fires on this net when the result is > RULES[rule]['limit']."""
    spec = RULES[rule]
    if spec['select'] == 'without' and diode_area != 0 or spec['select'] == 'with' and not diode_area > 0:
        measured = 0.0  # *_WO_DIODE / *_WITH_DIODE hold no polygon of this net
    if not gate_area:
        return 0.0  # !!AREA(GATE) = 0
    if spec['kind'] == 'ratio':
        return (measured if spec['factor'] is None else measured * spec['factor']) / gate_area
    if spec['kind'] == 'no_diode':
        return (0.0 if diode_area else 1.0) * (measured / gate_area)
    term = measured if spec['factor'] is None else measured * spec['factor']
    return (term - (gate_area * ((diode_area * spec['k']) + spec['c']))) * 1.0


def fires(rule, measured, gate_area, diode_area):
    return evaluate(rule, measured, gate_area, diode_area) > RULES[rule]['limit']


def user_units(value, scale, measure='area'):
    """Integer dbu (dbu^2 for an area) -> um / um2, divided by the precision as Calibre does: x 1e-6 instead
    would make the ANT_06 equality case 0 and miss Calibre's violation."""
    return value/scale if measure == 'perimeter' else value/scale**2


def precision(dbu):
    """Database units per um; the deck's AREA/PERIMETER are dbu^2 / precision^2 and dbu / precision."""
    grid = .01/dbu
    if abs(grid-round(grid)) > 1e-7 or grid < 1:
        raise ValueError('GDS dbu cannot represent the 0.01 um process grid exactly')
    return round(1/dbu)


class _Nets:
    """One netlist extraction over flat regions with the given CONNECTs (KLayout LayoutToNetlist)."""

    def __init__(self, regions, connections, dbu):
        import pya
        names = sorted({name for connection in connections for name in connection if name})
        self.layout = pya.Layout()  # kept alive: the extractor reads it
        self.layout.dbu = dbu
        cell = self.layout.create_cell('ANTENNA')
        index = {}
        for number, name in enumerate(names, start=1):
            index[name] = self.layout.layer(number, 0)
            cell.shapes(index[name]).insert(regions[name])
        self.l2n = pya.LayoutToNetlist(pya.RecursiveShapeIterator(self.layout, cell, []))
        self.layers = {name: self.l2n.make_layer(index[name], name) for name in names}
        for name in names:
            self.l2n.connect(self.layers[name])  # same-layer shapes that touch are one conductor
        for a, b, by in connections:
            if by:  # CONNECT a b BY by: the cut layer joins both
                self.l2n.connect(self.layers[a], self.layers[by])
                self.l2n.connect(self.layers[by], self.layers[b])
            else:
                self.l2n.connect(self.layers[a], self.layers[b])
        self.l2n.extract_netlist()
        circuit = self.l2n.netlist().circuit_by_name('ANTENNA')
        self.nets = [] if circuit is None else list(circuit.each_net())

    def shapes(self, net, name):
        return self.l2n.shapes_of_net(net, self.layers[name], True).merged()


def _regions(layout, top):
    import pya
    raw = {}
    for name, number in LAYERS.items():
        index = layout.find_layer(number, 0)
        raw[name] = pya.Region() if index is None else pya.Region(top.begin_shapes_rec(index)).merged()
    reg = dict(raw)
    reg['EXTLAYER'] = (raw['CAP'] | raw['BJT']) | raw['DIODE']                            # line 61
    active = (raw['ACT'] & raw['NSD']) | (raw['ACT'] & raw['PSD'])                         # line 62
    reg['ACTIVE_ALL'] = active - reg['EXTLAYER']                                           # line 63
    reg['POLY'] = raw['POLY1'] | raw['POLY2']                                              # line 67
    reg['GATE'] = reg['ACTIVE_ALL'] & reg['POLY']                                          # line 64
    reg['ALL_SD'] = reg['ACTIVE_ALL'] - reg['POLY']                                        # line 65
    reg['CONT_ANTENNA'] = raw['CONT'] & reg['POLY']                                        # line 66
    reg.pop('DIODE')  # the DIODE marker is only an EXTLAYER input; 'DIODE' below means ACTIVE_DIODE*
    return reg


def check(layout, top, selected=None):
    """{'rules': {RULECHECK: {'errors': violating nets, 'first_boxes_um', 'first_values', ...}}, 'errors': n}."""
    import pya
    if top is None or top.is_empty():
        raise ValueError('missing or empty DRC top')
    scale = precision(layout.dbu)
    reg = _regions(layout, top)
    cache = {}

    def nets(connections, regions):
        key = (tuple(connections), id(regions.get('DIODE')))
        if key not in cache:
            cache[key] = _Nets(regions, connections, layout.dbu)
        return cache[key]
    diodes = {}

    def diode_region(connections):
        """ACTIVE_DIODE*: ALL_SD of nets (these CONNECTs only) with >= 0.202 um2 of ALL_SD."""
        key = tuple(connections)
        if key not in diodes:
            found = pya.Region()
            extraction = nets(connections, reg)
            for net in extraction.nets:
                shapes = extraction.shapes(net, 'ALL_SD')
                if not shapes.is_empty() and user_units(shapes.area(), scale) >= DIODE_MIN_AREA:
                    found += shapes
            diodes[key] = found.merged()
        return diodes[key]
    names = sorted(RULES if selected is None else selected)
    rules = {}
    for name in names:
        spec = RULES[name]
        regions = dict(reg)
        if spec['diode_connect']:
            regions['DIODE'] = diode_region(spec['diode_connect'])
        extraction = nets(spec['connect'], regions)
        errors, boxes, values, checked, highest = 0, [], [], 0, None
        for net in extraction.nets:
            gate = extraction.shapes(net, 'GATE')
            if gate.is_empty():
                continue  # !!AREA(GATE) = 0: the expression is 0
            checked += 1
            layer = extraction.shapes(net, spec['layer'])
            raw = layer.perimeter() if spec['measure'] == 'perimeter' else layer.area()
            measured = user_units(raw, scale, spec['measure'])
            gate_area = user_units(gate.area(), scale)
            diode_area = user_units(extraction.shapes(net, 'DIODE').area(), scale) if spec['diode_connect'] else 0.0
            value = evaluate(name, measured, gate_area, diode_area)
            highest = value if highest is None else max(highest, value)
            if value > spec['limit']:
                errors += 1
                if len(boxes) < 30:
                    box = (layer if not layer.is_empty() else gate).bbox()
                    boxes.append([round(v*layout.dbu, 6) for v in [box.left, box.bottom, box.right, box.top]])
                    values.append({'value': value, 'limit': spec['limit'], spec['measure']: measured,
                                   'gate_area_um2': gate_area, 'diode_area_um2': diode_area})
        # max_value: the largest expression value over nets with gate area (None: no such net), vs limit.
        rules[name] = {'errors': errors, 'first_boxes_um': boxes, 'first_values': values, 'nets_with_gate': checked,
                       'max_value': highest, 'limit': spec['limit'], 'operator': 'antenna_'+spec['kind'],
                       'deck_line': spec['line']}
    return {'top': top.name, 'profile': 'antenna', 'deck': ANT_SOURCE, 'deck_sha256': ANT_SOURCE_SHA,
            'selected_rules': names, 'rules': rules, 'errors': sum(x['errors'] for x in rules.values())}


def main():
    import pya
    layout = pya.Layout()
    layout.read(os.environ['SSC_GDS'])
    result = check(layout, layout.cell(os.environ['SSC_TOP']))
    result['status'] = 'fail' if result['errors'] else 'pass'
    Path(os.environ['SSC_DRC_OUT']).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['rules', 'selected_rules']}))
    for name, item in result['rules'].items():
        print(name, item['errors'], item['nets_with_gate'], item['first_boxes_um'][:3])
    if result['errors']:
        raise ValueError('NSPL antenna violations: '+str(result['errors']))
