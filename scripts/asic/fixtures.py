"""KLayout batch: manufacture independent positive/negative geometry fixtures."""
import json
import os
from pathlib import Path
import pya

out = Path(os.environ['SSC_FIXTURES'])
out.mkdir(parents=True, exist_ok=True)

def box(cell, layer, bounds):
    cell.shapes(cell.layout().layer(layer, 0)).insert(pya.DBox(*bounds))

for name in ['clean', 'stacked', 'narrow', 'hierarchy']:
    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell('fixture')
    box(top, 32, [0, 0, 10, 4])
    box(top, 34, [0, 0, 10, 4])
    box(top, 33, [2.6, 1.6, 3.4, 2.4])
    if name == 'stacked':
        box(top, 31, [2.7, 1.7, 3.3, 2.3])
    if name == 'narrow':
        box(top, 32, [12, 0, 12.4, 5])
    if name == 'hierarchy':
        child = layout.create_cell('bad_child')
        box(child, 32, [12, 0, 12.4, 5])
        top.insert(pya.CellInstArray(child.cell_index(), pya.Trans()))
    layout.write(str(out/(name+'.gds')))

layout = pya.Layout()
layout.dbu = 0.001
core = layout.create_cell('core')
box(core, 32, [0, 0, 2, 2])
box(core, 32, [5, 0, 7, 2])
layout.write(str(out/'core.gds'))
for name in ['connected', 'open', 'internal-short']:
    chip_layout = pya.Layout()
    chip_layout.dbu = 0.001
    chip = chip_layout.create_cell('chip')
    box(chip, 32, [10, 10, 12, 12])
    box(chip, 32, [15, 10, 17, 12])
    probes = [{'net': 'A', 'layer': 32, 'xy': [10.5, 10.5]},
              {'net': 'A', 'layer': 32, 'xy': [11.5, 11.5]}]
    if name == 'open':
        probes[1]['xy'] = [30, 30]
    if name == 'internal-short':
        # Only A is probed. The component comparison must still detect the
        # new connection to the otherwise unobserved second core conductor.
        box(chip, 32, [11.8, 10.5, 15.2, 11.5])
    chip_layout.write(str(out/(name+'.gds')))
    (out/(name+'-assembly.json')).write_text(json.dumps({
        'top': 'chip', 'core_origin': [10, 10], 'probes': probes}))
