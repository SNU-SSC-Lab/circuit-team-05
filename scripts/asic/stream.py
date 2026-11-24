"""KLayout batch: DEF + original NSPL cell GDS -> independently reopened GDS.

SSC_DEF, SSC_TECH_LEF, SSC_CELL_LEF, SSC_CELL_GDS, SSC_TOP, SSC_GDS_OUT.
The import strategy follows the Team01 M0-09 experiment; this implementation
supports arbitrary core tops and independently verifies every used master.
"""
import hashlib
import json
import os
from pathlib import Path
import re

import pya


def main():
    output = Path(os.environ['SSC_GDS_OUT'])
    options = pya.LoadLayoutOptions()
    config = options.lefdef_config
    config.lef_files = [os.environ['SSC_TECH_LEF'], os.environ['SSC_CELL_LEF']]
    config.read_lef_with_def = False
    config.macro_layout_files = [os.environ['SSC_CELL_GDS']]
    config.macro_resolution_mode = 2
    config.dbu = 0.001
    mapping = pya.LayerMap()
    for name, number in [('MET1', 32), ('VIA1', 33), ('MET2', 34), ('VIA2', 35),
                          ('MET3', 36), ('MET1.LABEL', 42), ('MET2.LABEL', 44),
                          ('MET3.LABEL', 46)]:
        mapping.map(pya.LayerInfo(name), number, pya.LayerInfo(number, 0))
    for purpose in ['routing', 'special_routing', 'via_geometry', 'pins']:
        setattr(config, purpose+'_suffix', '')
        setattr(config, purpose+'_datatype', 0)
    for flag in ['produce_cell_outlines', 'produce_obstructions', 'produce_blockages',
                 'produce_lef_pins', 'produce_lef_labels', 'create_other_layers']:
        setattr(config, flag, False)
    config.instance_property_name = 'instance_name'
    config.layer_map = mapping
    options.lefdef_config = config
    layout = pya.Layout()
    layout.read(os.environ['SSC_DEF'], options)
    name = os.environ['SSC_TOP']
    top = layout.cell(name)
    if top is None or top.is_empty():
        raise ValueError('empty or missing DEF top')
    layout.write(str(output))
    saved, original = pya.Layout(), pya.Layout()
    saved.read(str(output))
    original.read(os.environ['SSC_CELL_GDS'])
    top = saved.cell(name)
    if saved.dbu != 0.001 or original.dbu != 0.001 or top is None:
        raise ValueError('GDS unit or top mismatch')
    definition = Path(os.environ['SSC_DEF']).read_text()
    section = re.search(r'(?ms)^COMPONENTS\s+\d+\s*;(.*?)^END COMPONENTS', definition)
    if section is None:
        raise ValueError('missing DEF components')
    components = re.findall(r'(?m)^\s*-\s+(\S+)\s+(\S+)\s+\+', section[1])
    masters = {master for _, master in components}
    if not masters:
        raise ValueError('no cell instances in GDS')
    placed = [i for i in top.each_inst() if i.cell.name in masters]
    if len(placed) != len(components):
        raise ValueError('DEF/GDS component count mismatch')
    via_helpers = {i.cell.name for i in top.each_inst() if i.cell.name not in masters}
    if any(not name.startswith('VIA_') for name in via_helpers):
        raise ValueError('unrecognized generated GDS hierarchy')
    checked = {}
    for master in sorted(masters):
        a, b = original.cell(master), saved.cell(master)
        if a is None or b is None or b.is_empty():
            raise ValueError('missing original master geometry: '+master)
        for li in original.layer_indices():
            info = original.get_info(li)
            lj = saved.find_layer(info)
            before = pya.Region(a.begin_shapes_rec(li))
            after = pya.Region() if lj is None else pya.Region(b.begin_shapes_rec(lj))
            if not (before ^ after).is_empty():
                raise ValueError('changed original cell geometry: '+master+' '+str(info))
        checked[master] = 'original geometry retained'
    labels = sorted({shape.text.string for li in saved.layer_indices()
                     for shape in top.shapes(li).each() if shape.is_text()})
    result = {'top': name, 'dbu_um': saved.dbu, 'instances': len(placed),
              'generated_via_cells': sorted(via_helpers),
              'masters': checked, 'top_labels': labels,
              'gds_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'scope': 'GDS merge/reimport/original masters; separate DRC/LVS required'}
    output.with_suffix('.json').write_text(json.dumps(result, indent=2)+'\n')
    view = pya.LayoutView()
    view.show_layout(saved, False)
    view.add_missing_layers()
    view.select_cell(top.cell_index(), 0)
    view.max_hier()
    view.zoom_fit()
    view.save_image(str(output.with_suffix('.png')), 1400, 1000)
    print(json.dumps(result))


main()
