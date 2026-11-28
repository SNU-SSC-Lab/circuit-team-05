# SPDX-License-Identifier: GPL-3.0-only
# GPIO/frame placement recipe adapted from SNU-SSC-Lab/circuit-team-01,
# commit 4c6542af1a2943dde15cfcaf3e1927151e474f25, chiptop/assemble.py.
# See COPYING.Team01. Pin alignment and core-specific routing are local work.
"""KLayout batch: proposed SOP28 assembly, never fabrication approval.

SSC_PAD_ROOT, SSC_CORE_GDS, SSC_CORE_TOP, SSC_CHIP_PLAN, SSC_POWER_ANCHORS,
SSC_CHIP_OUT. The core was implemented with the matching proposed pin plan.
"""
import hashlib
import json
import os
from pathlib import Path

import pya


def main():
    root = Path(os.environ['SSC_PAD_ROOT'])
    files = {'MPW_PAD_28pin.gds': '608111891a2969323abe94b74733781cde5319955638092b3c79a2f28d7eedf7',
             'ETRI_NSPL_GPIO_250610.gds': '7d54a4948e775fc3a99faf157f91a3510a82c22cc134d677de83dd2214b6e971'}
    plan = json.loads(Path(os.environ['SSC_CHIP_PLAN']).read_text())
    output = Path(os.environ['SSC_CHIP_OUT'])
    layout = pya.Layout()
    for name, digest in files.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
            raise ValueError('unreviewed pad source: '+name)
        layout.read(str(root/name))
    layout.read(os.environ['SSC_CORE_GDS'])
    if layout.dbu != 0.001:
        raise ValueError('chip GDS requires 0.001 um database units')
    frame = layout.cell('MPW_PAD_28pin')
    pads = [i for i in frame.each_inst() if i.cell.name == 'PAD80']
    if len(pads) != 28:
        raise ValueError('expected exactly 28 template pad positions')
    for item in pads:
        item.delete()
    top = layout.create_cell('ternary8_sop28')
    top.insert(pya.DCellInstArray(frame.cell_index(), pya.DTrans()))
    core = layout.cell(os.environ['SSC_CORE_TOP'])
    ox, oy = plan['core_origin']
    top.insert(pya.DCellInstArray(core.cell_index(), pya.DTrans(ox, oy)))
    placed, routes, probes = [], [], []

    def place(name, master, angle, mirror, x, y):
        cell = layout.cell(master)
        if cell is None:
            raise ValueError('missing GPIO master: '+master)
        trans = pya.DCplxTrans(1, angle, mirror, x, y)
        top.insert(pya.DCellInstArray(cell.cell_index(), trans))
        placed.append({'name': name, 'master': master, 'angle': angle, 'mirror': mirror, 'x': x, 'y': y})
        return trans

    def bank(side, along):
        return {'bottom': (0, False, along, 189), 'top': (0, True, along, 1711),
                'right': (90, False, 1711, along), 'left': (270, False, 189, 1900-along)}[side]

    def point(trans, x, y):
        p = trans*pya.DPoint(x, y)
        return [round(p.x, 3), round(p.y, 3)]

    def probe(net, layer, xy, role):
        probes.append({'net': net, 'layer': layer, 'xy': xy, 'role': role})

    def trace(net, layer, width, start, end):
        x, y = start
        xx, yy = end
        if x != xx and y != yy:
            raise ValueError('only orthogonal boundary routing is implemented')
        if start == end:
            return
        half = width/2
        top.shapes(layout.layer(layer, 0)).insert(
            pya.DBox(min(x, xx)-half, min(y, yy)-half, max(x, xx)+half, max(y, yy)+half))
        routes.append({'net': net, 'layer': layer, 'width': width, 'from': start, 'to': end})

    def via(net, x, y):
        for number, half in [(34, 1), (35, 0.4), (36, 1)]:
            top.shapes(layout.layer(number, 0)).insert(pya.DBox(x-half, y-half, x+half, y+half))
        routes.append({'net': net, 'via': 'V23', 'xy': [x, y]})

    for side in ['bottom', 'top', 'left', 'right']:
        for start, end in [(442, 485), *[(605+135*k, 620+135*k) for k in range(6)], (1415, 1458)]:
            x = start
            while x < end:
                width = 10 if end-x >= 10 else 1
                place(f'fill_{side}_{x}', f'IOFILLER{width}', *bank(side, x))
                x += width
    for index, args in enumerate([(0, False, 189, 189), (0, True, 189, 1711),
                                   (90, False, 1711, 189), (180, False, 1711, 1711)]):
        place('corner_'+str(index), 'PCORNER', *args)
    anchors = {'VDD': [], 'VSS': []}
    for line in Path(os.environ['SSC_POWER_ANCHORS']).read_text().splitlines():
        net, *values = line.split()
        anchors[net].append(list(map(float, values)))
    for row in plan['pads']:
        number, side, net, master = row['number'], row['side'], row['net'], row['master']
        px, py = row['pad']
        along = (1900-py if side == 'left' else py) if side in ['left', 'right'] else px
        trans = place(f'pad_{number:02}', master, *bank(side, along-60))
        if point(trans, 60, -49) != [px, py]:
            raise ValueError('package pad position mismatch')
        top.shapes(layout.layer(47, 0)).insert(pya.DText(net, px, py))
        probe(net if net in ['VDD', 'VSS'] else 'PAD_'+net, 36, [px, py], f'pad_{number:02}')
        for power, ys in [('VDD', [150, 219]), ('VSS', [35, 240])]:
            for y in ys:
                probe(power, 36, point(trans, 1, y), f'rail_{number:02}')
        gx, gy = row['gpio']
        probe(net, 34, [gx, gy], f'gpio_{number:02}')
        if master in ['PVDD', 'PVSS']:
            if number not in [24, 25]:
                continue
            box = max(anchors[net], key=lambda b: b[1]+b[3])
            cy = oy+(box[1]+box[3])/2
            if not ox+box[0]+3 <= gx <= ox+box[2]-3:
                raise ValueError('core power landing outside the ring')
            trace(net, 34, 6, [gx, gy], [gx, cy])
            for dx in [-2, 0, 2]:
                via(net, gx+dx, cy)
            probe(net, 36, [gx, cy], 'core_ring')
            continue
        cx, cy = row['core']
        if side in ['left', 'right']:
            vx = gx+8 if side == 'left' else gx-8
            trace(net, 34, 2, [gx, gy], [vx, gy])
            via(net, vx, gy)
            trace(net, 36, 1.2, [vx, gy], [cx, cy])
            probe(net, 36, [cx, cy], 'core_signal')
        else:
            trace(net, 34, 1.0, [gx, gy], [cx, cy])
            probe(net, 34, [cx, cy], 'core_signal')
    options = pya.SaveLayoutOptions()
    options.gds2_write_timestamps = False
    top.write(str(output), options)
    checked = pya.Layout()
    checked.read(str(output))
    saved = checked.cell(top.name)
    openings = pya.Region(saved.begin_shapes_rec(checked.layer(37, 0))).merged()
    centers = sorted([round(p.bbox().center().x*checked.dbu, 3),
                      round(p.bbox().center().y*checked.dbu, 3)] for p in openings.each())
    if centers != sorted(row['pad'] for row in plan['pads']):
        raise ValueError('saved chip does not preserve all 28 pad opening positions')
    original = pya.Layout()
    original.read(str(root/'ETRI_NSPL_GPIO_250610.gds'))
    for name in {item['master'] for item in placed}:
        a, b = original.cell(name), checked.cell(name)
        for li in original.layer_indices():
            info = original.get_info(li)
            before = pya.Region(a.begin_shapes_rec(li))
            after = pya.Region(b.begin_shapes_rec(checked.layer(info)))
            if not (before ^ after).is_empty():
                raise ValueError('changed GPIO master geometry: '+name)
    result = {'top': top.name, 'status': 'experimental-unqualified', 'proposed_pinmap': True,
              'used_pins': plan['used_pins'], 'guide_pin_budget': plan['guide_used_pin_limit'],
              'core_origin': plan['core_origin'], 'original_gpio_geometry_retained': True,
              'pad_openings': len(centers), 'instances': placed, 'routes': routes, 'probes': probes}
    output.with_suffix('.json').write_text(json.dumps(result, indent=2)+'\n')
    view = pya.LayoutView()
    view.show_layout(checked, False)
    view.add_missing_layers()
    view.select_cell(saved.cell_index(), 0)
    view.max_hier()
    view.zoom_fit()
    view.save_image(str(output.with_suffix('.png')), 1200, 1200)
    print('Proposed SOP28 GDS saved; GPIO LVS/timing and pin budget remain unqualified.')


main()
