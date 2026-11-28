"""KLayout batch: actual pad/core/PG metal connectivity and no new core shorts.

This does not replace transistor-level GPIO LVS or process DRC.
"""
import json
import os
from pathlib import Path

import pya


def conductors(path, topname):
    original = pya.Layout()
    original.read(str(path))
    original_top = original.cell(topname)
    if original_top is None:
        raise ValueError('missing conductor top')
    flat = pya.Layout()
    flat.dbu = original.dbu
    cell = flat.create_cell(topname)
    for number in [32, 33, 34, 35, 36]:
        index = original.find_layer(number, 0)
        if index is not None:
            cell.shapes(flat.layer(number, 0)).insert(pya.Region(original_top.begin_shapes_rec(index)))
    l2n = pya.LayoutToNetlist(pya.RecursiveShapeIterator(flat, cell, []))
    layers = {n: l2n.make_polygon_layer(flat.layer(n, 0), 'L'+str(n)) for n in [32, 33, 34, 35, 36]}
    for layer in layers.values():
        l2n.connect(layer)
    for first, second in [(32, 33), (33, 34), (34, 35), (35, 36)]:
        l2n.connect(layers[first], layers[second])
    l2n.extract_netlist()
    return flat, cell, l2n, layers


def cluster(extraction, layers, layer, point):
    net = extraction.probe_net(layers[layer], pya.DPoint(*point))
    if net is None:
        return None
    value = net.cluster_id
    return value() if callable(value) else value


def inside(poly):
    for edge in poly.each_edge():
        x, y = (edge.p1.x+edge.p2.x)//2, (edge.p1.y+edge.p2.y)//2
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)]:
            point = pya.Point(x+dx, y+dy)
            if poly.inside(point):
                return point
    raise ValueError('cannot find a point inside a conductor polygon')


def main():
    assembly = json.loads(Path(os.environ['SSC_CHIP_ASSEMBLY']).read_text())
    core = conductors(os.environ['SSC_CORE_GDS'], os.environ['SSC_CORE_TOP'])
    chip = conductors(os.environ['SSC_CHIP_GDS'], assembly['top'])
    _, _, cl2n, clayers = chip
    groups, missing = {}, []
    for p in assembly['probes']:
        found = cluster(cl2n, clayers, p['layer'], p['xy'])
        if found is None:
            missing.append(p)
        groups.setdefault(p['net'], set()).add(found)
    opens = {name: sorted(v for v in ids if v is not None) for name, ids in groups.items() if len(ids) != 1 or None in ids}
    owners = {}
    for name, ids in groups.items():
        for value in ids:
            if value is not None:
                owners.setdefault(value, []).append(name)
    shorts = [names for names in owners.values() if len(names) > 1]
    # Every original core metal component must retain a unique image in the
    # chip. Checking just the package pins would miss a strap shorting an
    # internal, otherwise unobserved core net.
    flat, cell, bl2n, blayers = core
    ox, oy = assembly['core_origin']
    forward, reverse = {}, {}
    for number in [32, 34, 36]:
        for poly in pya.Region(cell.begin_shapes_rec(flat.layer(number, 0))).merged().each():
            p = inside(poly)
            xy = [p.x*flat.dbu, p.y*flat.dbu]
            before = cluster(bl2n, blayers, number, xy)
            after = cluster(cl2n, clayers, number, [xy[0]+ox, xy[1]+oy])
            if before is None or after is None:
                raise ValueError('lost core conductor during assembly')
            forward.setdefault(before, set()).add(after)
            reverse.setdefault(after, set()).add(before)
    split = [key for key, ids in forward.items() if len(ids) != 1]
    merged = [sorted(ids) for ids in reverse.values() if len(ids) != 1]
    result = {'status': 'pass' if not (opens or shorts or missing or split or merged) else 'fail',
              'scope': 'metal connectivity; GPIO transistor LVS and physical rules remain separate',
              'probe_count': len(assembly['probes']), 'opens': opens, 'shorts': shorts, 'missing': missing,
              'core_metal_components': len(forward), 'split_core_components': split, 'merged_core_components': merged}
    Path(os.environ['SSC_CHIP_CHECK_OUT']).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
    if result['status'] != 'pass':
        raise ValueError('chip metal connectivity check failed')


main()
