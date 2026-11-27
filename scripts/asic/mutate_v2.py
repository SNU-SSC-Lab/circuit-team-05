"""Wave-2 mutation corpus: valid single-edit mutations of kit cells and of core windows (2026-11-28 golden).

Ported from the 2026-11-28 wave-2 generator with every random choice in the same order, so seed 20261129 rebuilds
the corpus Calibre judged (`verification/reliability/golden/drc-mutations-20261128b/`). Unlike wave 1
(`mutate.py`, left as is) every edit goes through pya.Region (merge semantics); empty, no-op, off-grid, holey or
non-simple results are rejected and redrawn. Every output GDS has one flat top cell `mut`; variant 0 is the
unmutated cell or window. GDS bytes are written without timestamps; records still carry `geometry_sha256`
(`mutate.geometry_sha256`) because golden matching uses geometry, not bytes.

Sources: the kit standard-cell GDS and GPIO GDS (from `--kit`), then 30x30 um windows of an open-flow core GDS
(`--core-gds`). The kit part uses the random stream first, so it is the same with or without the core GDS. The
core GDS is built from our RTL and is not committed; without it only the kit part is written.

    python scripts/asic/mutate_v2.py generate --kit KIT [--core-gds CORE.gds] --out NEW_DIR
    python scripts/asic/mutate_v2.py selfcheck --gds-dir DIR --out selfcheck.json

Both run KLayout (`klayout -b`); this file is also the KLayout batch script (SSC_MUTATE2_MODE set).
"""
import argparse
import glob
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys

SEED = 20261129
STD_GDS = 'NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T_PnR/GDS/NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T_std.gds'
GPIO_GDS = 'ETRI_NSPL_GPIO_250610.gds'
CORE_TOP = 'v_ternary8_top'

GRID_UM = 0.01            # deck: PRECISION 1000, OFFGRID <layer> 10  -> 0.01 um
# min width (um) per GDS layer, deck rule names in MINW_RULE
MINW = {2: 2.5, 11: 0.7, 12: 0.5, 13: 0.6, 14: 0.75, 15: 0.75, 32: 0.8, 34: 1.0, 36: 1.2}
MINW_RULE = {2: '1.NWL.W', 11: '2.ACT.W3', 12: '3.PL1.W3', 13: '4.PL2.W', 14: '5.NSD.W', 15: '6.PSD.W',
             32: '8.MET1.W', 34: '10.MET2.W', 36: '12.MET3.W'}
# via/contact layers: (exact size um, min space um, deck rules)
VIAS = {31: (0.6, 0.6, '7.CONT.W/7.CONT.S1'), 33: (0.8, 0.8, '9.VIA1.W/9.VIA1.S1'), 35: (0.8, 0.8, '11.VIA2.W/11.VIA2.S1')}
DELTAS = [0.01, 0.05, 0.1, 0.2, 0.4, 0.8]
WIDTH_OFFSETS = [-0.05, -0.01, 0.0, 0.01, 0.05]
GAP_OFFSETS = [-0.05, -0.01, 0.0, 0.01, 0.05, 0.4]
OPS = {'shift': 1.0, 'grow': 0.8, 'shrink': 0.8, 'delete': 0.6, 'narrow_minw': 2.0, 'edge_move': 2.0,
       'dup_via': 1.4, 'del_via': 1.0}
MAX_TRIES = 60
# only drawn layers the kit decks read (LAYER statements 0..60 without the text layers 41..47); others such as
# 235/0 (P&R boundary) or 48/0 (frame) are copied but never mutated
DECK_LAYERS = set(range(0, 61)) - {41, 42, 43, 44, 45, 46, 47}


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def problems(poly, dbu, grid=True):
    """Why a hole-free polygon would be refused/ambiguous as GDS input; [] if fine.
    Simple = merging the polygon alone reproduces it exactly (one piece, no hole, same area, same vertex count,
    no repeated vertex). A self-intersecting (figure-8), self-touching (keyhole) or spiked outline fails."""
    out = []
    if poly.holes():
        out.append('holes')
    n = poly.num_points_hull()
    pts = [(p.x, p.y) for p in poly.each_point_hull()]
    if n < 3:
        out.append('points<3')
    if poly.area() <= 0:
        out.append('zero_area')
    if len(set(pts)) != len(pts):
        out.append('repeated_vertex')
    if not out:
        merged = pya.Region(poly).merged()
        if merged.count() != 1:
            out.append('merge_count=%d' % merged.count())
        else:
            m = next(iter(merged.each()))
            if m.holes() or m.area() != poly.area() or m.num_points_hull() != n:
                out.append('not_simple')
    if grid:
        g = int(round(GRID_UM / dbu))
        if any(x % g or y % g for x, y in pts):
            out.append('offgrid')
    return out


def shape_poly(s):
    if s.is_box() or s.is_polygon() or s.is_simple_polygon() or s.is_path():
        return s.polygon
    return None


def poly_um(poly, dbu):
    return [[round(p.x * dbu, 4), round(p.y * dbu, 4)] for p in poly.each_point_hull()]


def layer_region(top, li):
    return pya.Region(top.shapes(li)).merged()


class Skip(Exception):
    pass


def pick_shape(rng, top, layers, pred=None):
    """Layer first (uniform over layers that have a candidate), then a shape on it, so that the many small
    contacts do not dominate the corpus."""
    by_layer = {}
    for li in layers:
        for s in top.shapes(li).each():
            p = shape_poly(s)
            if p is not None and (pred is None or pred(li, s, p)):
                by_layer.setdefault(li, []).append((li, s, p))
    if not by_layer:
        raise Skip('no candidate shape')
    return rng.choice(by_layer[rng.choice(sorted(by_layer))])


def edge_strip(poly, edge, d):
    """Box swept from a manhattan edge by d dbu: d>0 outward, d<0 inward. None if the edge is not manhattan."""
    p1, p2 = edge.p1, edge.p2
    if p1.y == p2.y:
        normals = [(0, 1), (0, -1)]
    elif p1.x == p2.x:
        normals = [(1, 0), (-1, 0)]
    else:
        return None, None
    mx, my = (p1.x + p2.x) // 2, (p1.y + p2.y) // 2
    inward = None
    for nx, ny in normals:
        if poly.inside(pya.Point(mx + nx, my + ny)):
            inward = (nx, ny)
    if inward is None:
        return None, None
    nx, ny = inward if d < 0 else (-inward[0], -inward[1])
    a = abs(d)
    q1 = pya.Point(p1.x + nx * a, p1.y + ny * a)
    q2 = pya.Point(p2.x + nx * a, p2.y + ny * a)
    box = pya.Box(min(p1.x, p2.x, q1.x, q2.x), min(p1.y, p2.y, q1.y, q2.y),
                  max(p1.x, p2.x, q1.x, q2.x), max(p1.y, p2.y, q1.y, q2.y))
    side = {(0, 1): 'top', (0, -1): 'bottom', (1, 0): 'right', (-1, 0): 'left'}[(-inward[0], -inward[1])]
    return box, side


def mutate(ly, top, rng, op):
    """Apply one op in place. Returns the record fields; raises Skip if this draw is unusable."""
    dbu = ly.dbu
    um = lambda v: int(round(v / dbu))
    poly_layers = [li for li in ly.layer_indexes() if ly.get_info(li).layer in DECK_LAYERS
                   and ly.get_info(li).datatype == 0
                   and any(shape_poly(s) is not None for s in top.shapes(li).each())]
    info = lambda li: ly.get_info(li)
    gds = lambda li: info(li).layer
    rec = {'op': op}
    if op in ('shift', 'grow', 'shrink', 'delete', 'edge_move'):
        pred = None
        if op == 'edge_move':
            pred = lambda li, s, p: p.is_rectilinear()
        li, s, p = pick_shape(rng, top, poly_layers, pred)
        d = rng.choice(DELTAS)
        if op == 'shift':
            axis = rng.choice('xy'); sign = rng.choice([1, -1])
            new = pya.Region(p.moved(um(sign * d), 0) if axis == 'x' else p.moved(0, um(sign * d)))
            rec['params'] = {'axis': axis, 'delta_um': sign * d}
        elif op == 'grow':
            new = pya.Region(p).sized(um(d), um(d), 2)
            rec['params'] = {'size_um': d, 'size_mode': 2}
        elif op == 'shrink':
            new = pya.Region(p).sized(-um(d), -um(d), 2)
            rec['params'] = {'size_um': -d, 'size_mode': 2}
        elif op == 'delete':
            new = pya.Region()
            rec['params'] = {}
        else:
            edges = list(p.each_edge())
            k = rng.randrange(len(edges)); e = edges[k]
            sign = rng.choice([1, -1])
            strip, side = edge_strip(p, e, sign * um(d))
            if strip is None:
                raise Skip('edge not manhattan')
            new = (pya.Region(p) + pya.Region(strip)).merged() if sign > 0 else pya.Region(p) - pya.Region(strip)
            rec['params'] = {'edge_index': k, 'edge_um': [[round(e.p1.x * dbu, 4), round(e.p1.y * dbu, 4)],
                                                          [round(e.p2.x * dbu, 4), round(e.p2.y * dbu, 4)]],
                             'edge_side': side, 'direction': 'outward' if sign > 0 else 'inward',
                             'delta_um': d}
        if op not in ('delete',) and new.is_empty():
            raise Skip('empty result')
        target, before = s, p
    elif op == 'narrow_minw':
        layers = [li for li in poly_layers if gds(li) in MINW and info(li).datatype == 0]

        def ok(li, s, p):           # a wire-like box: narrow side at most 3x the layer minimum
            return p.is_box() and min(p.bbox().width(), p.bbox().height()) <= um(3 * MINW[gds(li)])
        li, s, p = pick_shape(rng, top, layers, ok)
        b = p.bbox(); w, h = b.width(), b.height()
        axis = 'x' if w < h else 'y' if h < w else rng.choice('xy')
        cur = w if axis == 'x' else h
        off = rng.choice(WIDTH_OFFSETS)
        tgt = um(MINW[gds(li)] + off)
        if tgt <= 0 or tgt == cur:
            raise Skip('no-op width')
        keep = rng.choice(['low', 'high'])
        if axis == 'x':
            nb = pya.Box(b.left, b.bottom, b.left + tgt, b.top) if keep == 'low' else pya.Box(b.right - tgt, b.bottom, b.right, b.top)
        else:
            nb = pya.Box(b.left, b.bottom, b.right, b.bottom + tgt) if keep == 'low' else pya.Box(b.left, b.top - tgt, b.right, b.top)
        new = pya.Region(nb)
        rec['params'] = {'axis': axis, 'width_before_um': round(cur * dbu, 4), 'min_width_um': MINW[gds(li)],
                         'offset_um': off, 'width_after_um': round(tgt * dbu, 4), 'kept_edge': keep,
                         'rule': MINW_RULE[gds(li)]}
        target, before = s, p
    elif op in ('dup_via', 'del_via'):
        layers = [li for li in poly_layers if gds(li) in VIAS and info(li).datatype == 0]
        li, s, p = pick_shape(rng, top, layers, lambda li, s, p: p.is_box())
        size, space, rule = VIAS[gds(li)]
        if op == 'del_via':
            new = pya.Region(); rec['params'] = {'rule_context': rule}
            target, before = s, p
        else:
            b = p.bbox()
            direction = rng.choice(['+x', '-x', '+y', '-y'])
            off = rng.choice(GAP_OFFSETS)
            gap = um(space + off)
            step = (b.width() if direction[1] == 'x' else b.height()) + gap
            sx = step if direction == '+x' else -step if direction == '-x' else 0
            sy = step if direction == '+y' else -step if direction == '-y' else 0
            new = pya.Region(p.moved(sx, sy))
            rec['params'] = {'direction': direction, 'min_space_um': space, 'gap_offset_um': off,
                             'gap_um': round(gap * dbu, 4), 'copied_from_um': poly_um(p, dbu), 'rule_context': rule}
            target, before = None, p
    else:
        raise ValueError(op)

    new_polys = list(new.each())
    for q in new_polys:
        why = problems(q, dbu)
        if why:
            raise Skip('invalid result: ' + ','.join(why))
    old = layer_region(top, li)
    shapes = top.shapes(li)
    if target is not None:
        shapes.erase(target)
    for q in new_polys:
        shapes.insert(q)
    xor = old ^ layer_region(top, li)
    if xor.is_empty():
        raise Skip('no geometric effect')
    bb = xor.bbox()
    rec.update(layer='%d/%d' % (info(li).layer, info(li).datatype),
               shape_before_um=poly_um(before, dbu),
               shapes_after_um=[poly_um(q, dbu) for q in new_polys],
               xor_area_um2=round(xor.area() * dbu * dbu, 6),
               near_um=[round(bb.left * dbu, 4), round(bb.bottom * dbu, 4), round(bb.right * dbu, 4), round(bb.top * dbu, 4)])
    return rec


def flat_copy(src_cell, dbu):
    ly = pya.Layout(); ly.dbu = dbu
    top = ly.create_cell('mut')
    top.copy_tree(src_cell); top.flatten(True)
    return ly, top


def window_copy(src_layout, src_top, box):
    """Clip a flat window of src_top into a new layout. Every source shape is clipped on its own (shape
    granularity kept); contacts/vias are kept only when entirely inside (no half vias); hole-free pieces only."""
    ly = pya.Layout(); ly.dbu = src_layout.dbu
    top = ly.create_cell('mut')
    rb = pya.Region(box)
    for li in src_layout.layer_indexes():
        info = src_layout.get_info(li)
        dst = None
        it = src_top.begin_shapes_rec_overlapping(li, box)
        while not it.at_end():
            s = it.shape()
            p = shape_poly(s)
            if p is not None:
                p = p.transformed(it.trans())
                if info.layer in VIAS:
                    pieces = [p] if box.contains(p.bbox().p1) and box.contains(p.bbox().p2) else []
                else:
                    pieces = []
                    for q in (pya.Region(p) & rb).each():
                        pieces.extend([q] if not q.holes() else q.decompose_trapezoids())
                for q in pieces:
                    q = pya.Polygon(q) if not isinstance(q, pya.Polygon) else q
                    if q.area() > 0:
                        if dst is None:
                            dst = ly.layer(info)
                        top.shapes(dst).insert(q)
            it.next()
    return ly, top


def check_file(path, inherited=frozenset()):
    """Strict check of every polygon/box/path in the file. A flagged polygon is tolerated only when it is
    identical to a polygon of the unmutated kit original (`inherited`, e.g. the kit's keyhole rings, which
    Calibre accepted in wave 1: all 105 originals exit 0)."""
    ly = pya.Layout(); ly.read(path)
    tops = [c.name for c in ly.top_cells()]
    res = {'tops': tops, 'polygons': 0, 'bad': [], 'inherited': 0, 'offgrid_vertices': 0, 'instances': 0}
    flagged = set()
    g = int(round(GRID_UM / ly.dbu))
    for c in ly.each_cell():
        res['instances'] += c.child_instances()
        for li in ly.layer_indexes():
            info = ly.get_info(li)
            lay = '%d/%d' % (info.layer, info.datatype)
            for s in c.shapes(li).each():
                p = shape_poly(s)
                if p is None:
                    continue
                res['polygons'] += 1
                res['offgrid_vertices'] += sum(1 for q in p.each_point_hull() if q.x % g or q.y % g)
                why = problems(p, ly.dbu, grid=False)
                if why:
                    key = (lay, p.to_s())
                    flagged.add(key)
                    if key in inherited:
                        res['inherited'] += 1
                        continue
                    bb = p.bbox()
                    res['bad'].append({'cell': c.name, 'layer': lay, 'why': why,
                                       'bbox_um': [bb.left * ly.dbu, bb.bottom * ly.dbu, bb.right * ly.dbu, bb.top * ly.dbu]})
    res['ok'] = tops == ['mut'] and res['instances'] == 0 and not res['bad']
    return res, flagged


def check_dir(d, out):
    """Self-check every GDS in d. Kit originals (manifest kind kit_cell, variant 0) may carry kit polygons that
    the strict test flags; those exact polygons are then tolerated in that cell's mutants. Core windows and all
    mutated shapes must be strictly clean."""
    files = sorted(glob.glob(os.path.join(d, '*.gds')))
    kinds = {}
    mf = os.path.join(d, 'manifest.json')
    if os.path.exists(mf):
        kinds = {r['gds']: r for r in json.load(open(mf))['records']}
    base = lambda name: name.split('-', 1)[1].rsplit('-v', 1)[0]
    result, kit_flags = {}, {}
    for f in files:                      # originals first
        name = os.path.basename(f)
        if name.endswith('-v0.gds'):
            res, flagged = check_file(f)
            kit = kinds.get(name, {}).get('kind', 'kit_cell') == 'kit_cell'
            if kit and res['bad']:
                kit_flags[base(name)] = flagged
                res['kit_original_flags'] = len(res['bad'])
                res['bad'] = []
                res['ok'] = res['tops'] == ['mut'] and res['instances'] == 0
            result[name] = res
    for f in files:
        name = os.path.basename(f)
        if not name.endswith('-v0.gds'):
            result[name] = check_file(f, kit_flags.get(base(name), frozenset()))[0]
    bad = [k for k, v in result.items() if not v['ok']]
    with open(out, 'w') as fh:
        json.dump({'files': len(files), 'failed': bad,
                   'kit_originals_with_tolerated_polygons': sorted(kit_flags), 'results': result}, fh, indent=1)
    print('checked', len(files), 'failed', len(bad))


def generate(out, seed, std_gds, gpio_gds, core_gds=None, core_top=CORE_TOP, std_per=8, gpio_per=3, windows=28,
             win_per=6, win_um=30.0):
    """The 2026-11-28 wave-2 generator; keep the order of every rng call or the corpus changes."""
    from mutate import _file_geometry
    rng = random.Random(seed)
    n_win = windows
    os.makedirs(out, exist_ok=False)
    names, weights = list(OPS), list(OPS.values())
    records, skips = [], {}
    sources = {}

    def emit(ly, base, rec):
        fname = '%04d-%s-v%d.gds' % (len(records), base.replace('/', '_'), rec['variant'])
        opts = pya.SaveLayoutOptions(); opts.gds2_write_timestamps = False
        ly.write(os.path.join(out, fname), opts)
        rec['gds'] = fname
        rec['geometry_sha256'], rec['polygons'] = _file_geometry(os.path.join(out, fname))
        records.append(rec)

    def mutants(make, base, rec0, count):
        v = 1
        while v <= count:
            for attempt in range(1, MAX_TRIES + 1):
                op = rng.choices(names, weights)[0]
                ly, top = make()
                try:
                    rec = mutate(ly, top, rng, op)
                except Skip as e:
                    skips[str(e).split(':')[0]] = skips.get(str(e).split(':')[0], 0) + 1
                    continue
                rec = dict(rec0, variant=v, draws=attempt, **rec)
                emit(ly, base, rec)
                break
            else:
                raise RuntimeError('no valid mutation for ' + base)
            v += 1

    for src, per in [(std_gds, std_per), (gpio_gds, gpio_per)]:
        sources[os.path.basename(src)] = sha256(src)
        lib = pya.Layout(); lib.read(src)
        libtops = {c.name for c in lib.top_cells()}
        for name in sorted(c.name for c in lib.each_cell()):
            cell = lib.cell(name)
            if cell.bbox().empty():
                continue
            make = lambda cell=cell: flat_copy(cell, lib.dbu)
            rec0 = {'source': os.path.basename(src), 'cell': name, 'kind': 'kit_cell'}
            ly, top = make()
            emit(ly, name, dict(rec0, variant=0, op='original'))
            if name not in libtops:          # whole-library tops: baseline only
                mutants(make, name, rec0, per)

    if core_gds:
        core = core_gds; sources[os.path.basename(core)] = sha256(core)
        clay = pya.Layout(); clay.read(core); ctop = clay.cell(core_top)
        cb = ctop.bbox(); w = int(round(win_um / clay.dbu)); snap = int(round(0.05 / clay.dbu))
        k = 0
        while k < n_win:
            x = rng.randrange(cb.left, cb.right - w) // snap * snap
            y = rng.randrange(cb.bottom, cb.top - w) // snap * snap
            box = pya.Box(x, y, x + w, y + w)
            make = lambda box=box: window_copy(clay, ctop, box)
            ly, top = make()
            n_shapes = sum(top.shapes(li).size() for li in ly.layer_indexes())
            if n_shapes < 20:
                skips['sparse window'] = skips.get('sparse window', 0) + 1
                continue
            base = 'core_w%02d' % k
            rec0 = {'source': os.path.basename(core), 'cell': ctop.name, 'kind': 'core_window', 'window': base,
                    'window_um': [round(v * clay.dbu, 4) for v in (x, y, x + w, y + w)]}
            emit(ly, base, dict(rec0, variant=0, op='original', shapes=n_shapes))
            mutants(make, base, rec0, win_per)
            k += 1

    with open(os.path.join(out, 'manifest.json'), 'w') as f:
        json.dump({'seed': seed, 'generator': 'scripts/asic/mutate_v2.py',
                   'generator_sha256': sha256(__file__),
                   'sources': sources, 'core_windows': bool(core_gds),
                   'params': {'std_per_cell': std_per, 'gpio_per_cell': gpio_per, 'windows': n_win,
                              'window_mutations': win_per, 'window_um': win_um, 'grid_um': GRID_UM,
                              'op_weights': OPS, 'deltas_um': DELTAS, 'width_offsets_um': WIDTH_OFFSETS,
                              'gap_offsets_um': GAP_OFFSETS, 'min_width_um': MINW, 'vias': VIAS},
                   'redraw_reasons': skips, 'records': records}, f, indent=1)
    print('wrote', len(records), 'redraws', skips)


def _batch():
    """Entry inside `klayout -b -r mutate_v2.py`; arguments come from SSC_MUTATE2_* variables."""
    global pya
    import pya
    env = os.environ
    if env['SSC_MUTATE2_MODE'] == 'generate':
        kit = Path(env['SSC_MUTATE2_KIT'])
        generate(env['SSC_MUTATE2_OUT'], int(env['SSC_MUTATE2_SEED']), str(kit/STD_GDS), str(kit/GPIO_GDS),
                 env.get('SSC_MUTATE2_CORE_GDS') or None, env.get('SSC_MUTATE2_CORE_TOP', CORE_TOP))
    elif env['SSC_MUTATE2_MODE'] == 'selfcheck':
        check_dir(env['SSC_MUTATE2_GDS_DIR'], env['SSC_MUTATE2_OUT'])
    else:
        raise ValueError('unknown SSC_MUTATE2_MODE: '+env['SSC_MUTATE2_MODE'])


def run_klayout(mode, timeout=3600, klayout='klayout', **values):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('SSC_MUTATE_', 'SSC_MUTATE2_'))}
    env.update(QT_QPA_PLATFORM='offscreen', SSC_MUTATE2_MODE=mode,
               **{'SSC_MUTATE2_'+key.upper(): str(value) for key, value in values.items() if value is not None})
    done = subprocess.run([klayout, '-b', '-r', str(Path(__file__).resolve())], env=env,
                          capture_output=True, text=True, timeout=timeout)
    if done.returncode:
        raise RuntimeError(f'KLayout mutate_v2 {mode} failed ({done.returncode}):\n{done.stdout}{done.stderr}')
    return done.stdout


def run_generate(kit, out, seed=SEED, core_gds=None, core_top=CORE_TOP, klayout='klayout'):
    """Write the corpus with KLayout; returns manifest.json. Without core_gds only the kit part exists."""
    run_klayout('generate', klayout=klayout, kit=Path(kit).resolve(), out=Path(out).resolve(), seed=seed,
                core_gds=Path(core_gds).resolve() if core_gds else None, core_top=core_top)
    return json.loads((Path(out)/'manifest.json').read_text(encoding='utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    gen = commands.add_parser('generate', help='write the mutated GDS files and manifest.json')
    gen.add_argument('--kit', type=Path, required=True, help='unpacked NSPL_05CMOS_PDK_260820 folder')
    gen.add_argument('--core-gds', type=Path, help='open-flow core GDS for the window part (optional)')
    gen.add_argument('--core-top', default=CORE_TOP)
    gen.add_argument('--out', type=Path, required=True, help='new folder')
    gen.add_argument('--seed', type=int, default=SEED)
    check = commands.add_parser('selfcheck', help='strict polygon check of every GDS in a folder')
    check.add_argument('--gds-dir', type=Path, required=True)
    check.add_argument('--out', type=Path, required=True)
    for sub in (gen, check):
        sub.add_argument('--klayout', default='klayout')
    args = parser.parse_args(argv)
    if args.command == 'generate':
        manifest = run_generate(args.kit, args.out, args.seed, args.core_gds, args.core_top, args.klayout)
        print(f'{len(manifest["records"])} GDS in {args.out}')
    else:
        print(run_klayout('selfcheck', klayout=args.klayout, gds_dir=args.gds_dir.resolve(), out=args.out.resolve()))
    return 0


if os.environ.get('SSC_MUTATE2_MODE'):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    _batch()
elif __name__ == '__main__':
    sys.exit(main())
