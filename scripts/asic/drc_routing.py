"""KLayout batch subset of pinned NSPL routing rules, not full process signoff.

SSC_GDS, SSC_TOP, SSC_DRC_OUT. Full supported/unsupported scope is in JSON.
"""
import json
import os
from pathlib import Path

import pya


def main():
    layout = pya.Layout()
    layout.read(os.environ['SSC_GDS'])
    top = layout.cell(os.environ['SSC_TOP'])
    if top is None or top.is_empty():
        raise ValueError('DRC top missing or empty')
    dbu = layout.dbu
    scale = lambda value: round(value/dbu)
    layers = {}
    for name, number in [('CONT', 31), ('MET1', 32), ('VIA1', 33), ('MET2', 34), ('VIA2', 35), ('MET3', 36)]:
        index = layout.find_layer(number, 0)
        layers[name] = pya.Region() if index is None else pya.Region(top.begin_shapes_rec(index)).merged()
    rules = {}

    def record(name, errors, detail):
        boxes = []
        for index, error in enumerate(errors.each()):
            if index >= 30:
                break
            b = error.bbox()
            boxes.append([round(c*dbu, 4) for c in [b.left, b.bottom, b.right, b.top]])
        rules[name] = {'errors': errors.count(), 'detail': detail, 'first_boxes_um': boxes}

    for name, group, width, space in [('MET1', 8, 0.8, 0.8), ('MET2', 10, 1.0, 1.0), ('MET3', 12, 1.2, 1.0)]:
        reg = layers[name]
        record(f'{group}.{name}.W', reg.width_check(scale(width)), f'minimum width {width} um')
        # S1 applies to narrow wires; report this as a narrow-wire check only.
        # The separate wide-wire spacing classification is not qualified yet.
        narrow = reg - reg.sized(-scale(5.0)).sized(scale(5.0))
        record(f'{group}.{name}.S1', narrow.space_check(scale(space)), f'narrow-wire spacing {space} um')
    for cut, group, size, gap in [('CONT', 7, 0.6, 0.6), ('VIA1', 9, 0.8, 0.8), ('VIA2', 11, 0.8, 0.8)]:
        reg = layers[cut]
        bad = pya.Region()
        allowed = {(scale(size), scale(size))}
        if cut == 'CONT':
            allowed.add((scale(0.6), scale(1.2)))
        for poly in reg.each():
            box = poly.bbox()
            if not poly.is_box() or tuple(sorted([box.width(), box.height()])) not in allowed:
                bad.insert(poly)
        record(f'{group}.{cut}.W', bad, 'fixed cut rectangle dimensions; no seal-ring waiver applied')
        record(f'{group}.{cut}.S1', reg.space_check(scale(gap)), f'cut spacing {gap} um')
    for rule, inner, outer in [('7.CONT.E3', 'CONT', 'MET1'),
                               ('9.VIA1.E1-E2', 'VIA1', 'MET1'), ('9.VIA1.E3-E4', 'VIA1', 'MET2'),
                               ('11.VIA2.E1-E2', 'VIA2', 'MET2'), ('11.VIA2.E3-E4', 'VIA2', 'MET3')]:
        record(rule, layers[outer].enclosing_check(layers[inner], scale(0.6)),
               f'{outer} enclosure of {inner} >= 0.6 um; narrow/wide have same threshold')
    for rule, first, second in [('9.VIA1.S', 'VIA1', 'CONT'), ('11.VIA2.S', 'VIA2', 'VIA1')]:
        record(rule, layers[first].separation_check(layers[second], scale(0.6)),
               f'{first} to {second} spacing >= 0.6 um')
        record(rule+'.overlap', layers[first] & layers[second], 'stacked cuts forbidden')
    for rule, cut, low, high in [('9.VIA1.bad1', 'VIA1', 'MET1', 'MET2'),
                                ('11.VIA2.bad1', 'VIA2', 'MET2', 'MET3')]:
        record(rule, layers[cut] - (layers[low] & layers[high]), 'cut must be covered by both metal layers')
    total = sum(item['errors'] for item in rules.values())
    result = {'top': top.name, 'subset_status': 'pass' if not total else 'fail',
              'errors': total, 'qualified_process_drc': False,
              'source_deck_sha256': '6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f',
              'scope': 'routing subset only; full NSPL rule coverage not qualified', 'rules': rules,
              'not_implemented': ['wide-wire spacing classification validation', 'well/active/poly/implant rules',
                                  'tap/latchup/pad/analog rules', 'full rule-by-rule validation']}
    Path(os.environ['SSC_DRC_OUT']).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rules'}))
    for name, item in rules.items():
        if item['errors']:
            print(name, item['errors'], item['first_boxes_um'][:3])
    if total:
        raise ValueError(f'NSPL routing subset: {total} violation markers')


if __name__ == '__main__':
    main()
