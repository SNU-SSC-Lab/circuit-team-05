"""KLayout batch audit: compare LEF obstruction rectangles with original GDS.

Read-only inputs. Run with SSC_LEF, SSC_GDS and SSC_AUDIT_OUT in the environment:
    klayout -b -r scripts/asic/audit_lef.py
"""
import hashlib
import json
import os
from pathlib import Path
import re

import pya


def region(layout, cell, number):
    layer = layout.find_layer(number, 0)
    return pya.Region() if layer is None else pya.Region(cell.begin_shapes_rec(layer)).merged()


def main():
    lef, gds = Path(os.environ['SSC_LEF']), Path(os.environ['SSC_GDS'])
    target = Path(os.environ['SSC_AUDIT_OUT'])
    layout = pya.Layout()
    layout.read(str(gds))
    result = {'lef_sha256': hashlib.sha256(lef.read_bytes()).hexdigest(),
              'gds_sha256': hashlib.sha256(gds.read_bytes()).hexdigest(),
              'dbu_um': layout.dbu, 'cells': {}}
    for match in re.finditer(r'^MACRO (\w+)\n(.*?)^END \1\s*$', lef.read_text(), re.M | re.S):
        name, body = match.groups()
        if '\n  OBS\n' not in body:
            continue
        cell = layout.cell(name)
        if cell is None:
            raise ValueError(f'GDS master missing: {name}')
        obs = body.split('\n  OBS\n', 1)[1].split('\n  END', 1)[0]
        layer, rectangles = None, {}
        for line in obs.splitlines():
            lm = re.search(r'\bLAYER (\w+)', line)
            if lm:
                layer = lm[1]
            rm = re.search(r'\bRECT\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)', line)
            if rm:
                coords = [round(float(x) / layout.dbu) for x in rm.groups()]
                rectangles.setdefault(layer, pya.Region()).insert(pya.Box(*coords))
        item = {}
        for source, reg in rectangles.items():
            reg = reg.merged()
            comparisons = {}
            for physical, number in [('CONT', 31), ('VIA1', 33), ('VIA2', 35), ('MET1', 32)]:
                actual = region(layout, cell, number)
                comparisons[physical] = {
                    'equal': (reg ^ actual).is_empty(),
                    'gds_polygons': actual.count(),
                    'lef_outside_gds_area_um2': (reg - actual).area() * layout.dbu ** 2,
                    'gds_outside_lef_area_um2': (actual - reg).area() * layout.dbu ** 2,
                }
            item[source] = {'lef_polygons': reg.count(), 'gds_comparison': comparisons}
        result['cells'][name] = item
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + '\n')
    for name, item in result['cells'].items():
        if 'VIA1' in item:
            c = item['VIA1']['gds_comparison']
            print(f"{name}: LEF VIA1 equals GDS CONT={c['CONT']['equal']}, VIA1={c['VIA1']['equal']}")


main()
