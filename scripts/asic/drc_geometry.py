"""KLayout geometry ports of named NSPL checks, not qualified full-process DRC."""
import json
import os
from pathlib import Path
import pya

from drc_ports import PORTS

LAYERS = dict(CHIPBOUNDARY=0, KEY=1, NWELL=2, PWELL=3, HNWELL=4, HPWELL=5,
              DWELL=6, DNWELL=7, DPWELL=8, ACT=11, POLY1=12, POLY2=13, NSD=14,
              PSD=15, FVTN=16, FVTP=17, VTN=18, VTP=19, NHRI=20, PHRI=21,
              NPI=22, PPI=23, NDRIFT=24, PDRIFT=25, ESDI=26, TGOX=27, JISO=28,
              TISO=29, CONT=31, MET1=32, VIA1=33, MET2=34, VIA2=35, MET3=36,
              PAD=37, RES=51, ESD=52, CAP=53, HVMS=54, HVMA=55, BJT=56,
              DIODE=57, NODRC=58, ESDD=59, LVSD=60)
MASKED = set('NWELL HNWELL HPWELL DWELL DNWELL DPWELL ACT POLY1 POLY2 NSD PSD FVTN FVTP VTN VTP NHRI PHRI NPI PPI NDRIFT PDRIFT TGOX JISO TISO CONT MET1 VIA1 MET2 VIA2 MET3 PAD'.split())

def check(layout, top, selected=None):
    if top is None or top.is_empty():
        raise ValueError('missing or empty DRC top')
    grid = .01/layout.dbu
    if abs(grid-round(grid)) > 1e-7 or grid < 1:
        raise ValueError('GDS dbu cannot represent the 0.01 um process grid exactly')
    if grid < 2:
        # WITH WIDTH >= 10 keeps a 10.00 um wire and drops a 9.99 um one (C1b fixtures); with integer
        # sizing that needs a threshold between two grid steps, so at least two dbu per grid step.
        raise ValueError('GDS dbu cannot represent the WITH WIDTH threshold: dbu must be at most half the 0.01 um grid')
    scale = lambda x: round(x/layout.dbu)
    raw = {}
    for name, number in LAYERS.items():
        index = layout.find_layer(number, 0)
        raw[name] = pya.Region() if index is None else pya.Region(top.begin_shapes_rec(index)).merged()
    reg = {name: (value-raw['NODRC'] if name in MASKED else value) for name, value in raw.items()}
    bulk = pya.Region(top.bbox()).sized(scale(.01))
    psub = bulk-(reg['NWELL'] | reg['HNWELL'] | reg['DNWELL'])-(raw['PWELL'] | reg['HPWELL'] | reg['DPWELL'])-reg['DWELL']
    reg['PWELL'] = (raw['PWELL'] | psub)-raw['NODRC']
    reg['RESNW'] = reg['NWELL'] & reg['RES']
    reg['NACT'], reg['PACT'] = reg['ACT'] & reg['NSD'], reg['ACT'] & reg['PSD']
    reg['NMOS'] = reg['NACT'].interacting(reg['POLY1'])
    reg['PMOS'] = reg['PACT'].interacting(reg['POLY1'])
    reg['NTAP'] = (reg['NACT'] & reg['NWELL']).not_interacting(reg['POLY1'])
    reg['PTAP'] = (reg['PACT']-reg['NWELL']).not_interacting(reg['POLY1'])
    reg['CONTACTED_NTAP'] = reg['NTAP'].interacting(reg['CONT'])
    reg['POLY1_ON_ACT'] = reg['POLY1'].interacting(reg['POLY1'] & reg['ACT'])
    reg['POLY1_NOT_ACT'] = reg['POLY1']-reg['POLY1_ON_ACT']
    reg['POLY1_CAP'] = reg['POLY1'].interacting(reg['CAP'])
    reg['IO_GATE_POLY'] = reg['POLY1_ON_ACT'] & reg['ESD']
    reg['ALLGATE'] = ((reg['NACT'] & reg['POLY1'])-reg['NWELL']) | (reg['PACT'] & reg['POLY1'] & reg['NWELL'])
    reg['POLY1_ON_CONT'] = reg['CONT'].interacting(reg['POLY1'])
    reg['POLY2_ON_CONT'] = reg['CONT'].interacting(reg['POLY2'])
    reg['POLY1_NOT_POLY2'] = reg['POLY1']-reg['POLY2']
    reg['CONT_OR_VIA1'] = reg['CONT'] | reg['VIA1']
    reg['VIA1_OR_VIA2'] = reg['VIA1'] | reg['VIA2']
    reg['MET1_AND_MET2'] = reg['MET1'] & reg['MET2']
    reg['MET2_AND_MET3'] = reg['MET2'] & reg['MET3']
    reg['ACTIVE_OR_POLY'] = reg['ACT'] | reg['POLY1'] | reg['POLY2']
    # Deck `MET1UP10 = WITH WIDTH MET1 >= 10`, `MET1UN10 = WITH WIDTH MET1 < 10` (same for MET2/MET3).
    # WITH WIDTH keeps parts, not whole polygons: the 2 um tail of a 20 um plate is UN10 (C1b 0014,
    # 0030, 0128). The wide part is the opening (size down, then up) by just under half of 10 um, so a
    # 10.00 um wire stays wide and a 9.99 um wire does not (C1b width-10.00/9.99 fixtures).
    half = scale(10/2)-1
    for metal in ('MET1', 'MET2', 'MET3'):
        wide = reg[metal].sized(-half).sized(half) & reg[metal]
        reg[metal+'UP10'], reg[metal+'UN10'] = wide, reg[metal]-wide
    # Deck `ARRAY_VIA1 = SIZE (SIZE VIA1 BY 0.8) BY 2.4 UNDEROVER`, `ARRAY1 = VIA1 AND ARRAY_VIA1`.
    # A grown block exactly 4.8 um wide vanishes (C1b 3x3-s0.40-degenerate: Calibre clean).
    for cut in ('VIA1', 'VIA2'):
        block = reg[cut].sized(scale(.8)).sized(-scale(2.4)).sized(scale(2.4))
        reg[cut+'_ARRAY'] = reg[cut] & block
    # Deck `PITCHPAD = SIZE PAD BY 19.99 OVERUNDER`, `A = PITCHPAD NOT PAD`; 13.PAD.P is `PAD INTERACT A`.
    reg['PAD_PITCH_FILL'] = reg['PAD'].sized(scale(19.99)).sized(-scale(19.99))-reg['PAD']
    names = sorted(PORTS if selected is None else selected)
    rules = {}
    for name in names:
        spec = PORTS[name]
        regions = [reg[layer] for layer in spec['layers']]
        kind, value = spec['kind'], spec['value']
        errors = []
        if kind in ['width', 'space']:
            errors = [getattr(layer, kind+'_check')(scale(value)) for layer in regions]
        elif kind == 'grid':
            errors = [regions[0].grid_check(scale(value), scale(value))]
        elif kind in ['separation', 'separation_no_stack']:
            errors = [regions[0].separation_check(regions[1], scale(value))]
            if kind == 'separation_no_stack':
                errors.append(regions[0] & regions[1])
        elif kind == 'separation_unshielded':
            # Deck `EXT MET1UP10 MET1 < v`: the wide part against its own metal. Every UP10 edge has a
            # coincident MET1 edge, and KLayout's default shielding then hides the facing edge across the
            # gap (C1b S2 fixtures: 0 markers). Calibre EXT measures without shielding unless the deck says
            # EXCLUDE SHIELDED, so measure unshielded. Coincident edges face the same way and are not pairs.
            errors = [regions[0].separation_check(regions[1], scale(value), False, pya.Region.Euclidian,
                                                  None, None, None, False)]
        elif kind == 'enclosure':
            # Deck: ENC inner outer < v ABUT < 90 SINGULAR OVERLAP REGION. ENC compares
            # interacting layers only: contacts solely on ACT must not fail the separate
            # POLY1 enclosure check, and vice versa. OVERLAP also flags an inner shape
            # whose boundary crosses the outer boundary: part of its edges inside the
            # outer layer and part outside. An outer shape (or hole) lying wholly inside
            # the inner shape crosses no inner edge and does not fire (Calibre C9).
            inner = regions[0]
            edges = inner.edges()
            for outer in regions[1:]:
                crossing = inner.interacting(edges.inside_part(outer)).interacting(edges.outside_part(outer))
                errors += [outer.enclosing_check(inner, scale(value)), crossing]
        elif kind == 'not_interacting':
            errors = [regions[0].not_interacting(regions[1])]
        elif kind == 'interacting':
            errors = [regions[0].interacting(regions[1])]
        elif kind == 'overlap':
            errors = [regions[0] & regions[1]]
        elif kind == 'overlap_except':
            errors = [(regions[0] & regions[1])-regions[2]]
        elif kind == 'uncovered':
            errors = [regions[0]-regions[1]]
        elif kind == 'cut_size':
            bad = pya.Region()
            allowed = {tuple(sorted(scale(x) for x in pair)) for pair in value}
            for poly in regions[0].each():
                box = poly.bbox()
                if not poly.is_box() or tuple(sorted([box.width(), box.height()])) not in allowed:
                    bad.insert(poly)
            errors = [bad]
        else:
            raise ValueError('unimplemented geometry operator: '+kind)
        boxes = []
        for collection in errors:
            for marker in collection.each():
                if len(boxes) == 30:
                    break
                box = marker.bbox()
                boxes.append([round(v*layout.dbu, 6) for v in [box.left, box.bottom, box.right, box.top]])
        rules[name] = {'errors': sum(c.count() for c in errors), 'first_boxes_um': boxes,
                       'input_polygons': sum(r.count() for r in regions), 'operator': kind}
    return {'top': top.name, 'profile': 'expanded-geometry', 'qualified_process_drc': False,
            'scope': 'named geometry ports; no Calibre/Assura golden comparison',
            'selected_rules': names, 'rules': rules, 'errors': sum(x['errors'] for x in rules.values()),
            'original_nodrc_area_um2': round(raw['NODRC'].area()*layout.dbu**2, 6),
            'masked_area_um2': {name: round((raw[name].area()-reg[name].area())*layout.dbu**2, 6)
                                for name in sorted(MASKED) if raw[name].area() != reg[name].area()},
            'source_semantics_notes': ['NODRC subtraction follows the pinned source; no new waiver inserted',
                'OFFGRID_FVTN checks FVTP as written; source naming disagreement remains',
                'PWELL substrate extent uses top bbox + 0.01 um; golden EXTENT comparison pending',
                'marker counts can duplicate a physical problem; not unique defect counts']}

def main():
    layout = pya.Layout()
    layout.read(os.environ['SSC_GDS'])
    result = check(layout, layout.cell(os.environ['SSC_TOP']))
    catalog = json.loads((Path(__file__).resolve().parents[2]/'verification/asic/drc-rules.json').read_text())
    result['source_deck_sha256'] = catalog['sources']['calibre']['sha256']
    result['unimplemented_rules'] = [r['id'] for r in catalog['rules'] if r['id'] not in PORTS]
    result['subset_status'] = 'fail' if result['errors'] else 'pass'
    Path(os.environ['SSC_DRC_OUT']).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['rules', 'selected_rules', 'unimplemented_rules']}))
    for name, item in result['rules'].items():
        if item['errors']:
            print(name, item['errors'], item['first_boxes_um'][:3])
    if result['errors']:
        raise ValueError('expanded NSPL geometry violations: '+str(result['errors']))
