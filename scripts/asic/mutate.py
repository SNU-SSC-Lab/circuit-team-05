"""Single-shape mutations of public kit cells: the real-geometry DRC corpus behind the mutation golden.

Ported unchanged in its random choices from the 2026-11-28 generator, so seed 20261128 with 6 variants
per cell rebuilds the corpus Calibre judged. Every output GDS has one flattened top cell `mut`;
variant 0 is the unmutated cell. GDS bytes carry timestamps, so each manifest record keeps
`geometry_sha256` (see `geometry_sha256`) and golden matching uses that instead.

    python scripts/asic/mutate.py generate --kit KIT --out NEW_DIR   # KIT = .../NSPL_05CMOS_PDK_260820
    python scripts/asic/mutate.py hash --gds-dir DIR --out geometry.json

Both run KLayout (`klayout -b`); this file is also the KLayout batch script (SSC_MUTATE_MODE set).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys

SEED = 20261128
PER_CELL = 6
# Kit-relative sources, in the order the 2026-11-28 corpus used them.
SOURCES = ('NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T_PnR/GDS/NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T_std.gds',
           'ETRI_NSPL_GPIO_250610.gds')
DELTAS = [0.05, 0.1, 0.2, 0.4, 0.8]
OPS = ['shift_x', 'shift_y', 'grow', 'shrink', 'delete']
TOP = 'mut'


def geometry_sha256(layout, cell):
    """sha256 of dbu and, per layer/datatype, the sorted integer point lists of every polygon under cell.

    Boxes, paths and polygons all count as polygons (hull, then holes); texts do not. Returns
    (digest, polygon count)."""
    import pya
    layers = {}
    count = 0
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        polygons = []
        shapes = cell.begin_shapes_rec(index)
        shapes.shape_flags = pya.Shapes.SBoxes | pya.Shapes.SPaths | pya.Shapes.SPolygons
        while not shapes.at_end():
            polygon = shapes.shape().polygon.transformed(shapes.trans())
            rings = [[[p.x, p.y] for p in polygon.each_point_hull()]]
            rings += [[[p.x, p.y] for p in polygon.each_point_hole(h)] for h in range(polygon.holes())]
            polygons.append(json.dumps(rings, separators=(',', ':')))
            shapes.next()
        if polygons:
            layers[f'{info.layer}/{info.datatype}'] = sorted(polygons)
            count += len(polygons)
    text = json.dumps({'dbu': round(layout.dbu, 9), 'layers': layers}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest(), count


def _file_geometry(path):
    import pya
    layout = pya.Layout()
    layout.read(str(path))
    top = layout.cell(TOP)
    if top is None:
        return None, 0
    return geometry_sha256(layout, top)


def _generate(kit, out, seed, per):
    """The 2026-11-28 generator; keep the order of every rng call or the corpus changes."""
    import pya
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=False)
    manifest = []
    for relative in SOURCES:
        src = kit/relative
        if not src.is_file():
            raise ValueError(f'kit file missing: {relative}')
        lib = pya.Layout()
        lib.read(str(src))
        for name in sorted(c.name for c in lib.each_cell()):
            cell = lib.cell(name)
            if cell is None or cell.bbox().empty():
                continue
            for v in range(per+1):
                ly = pya.Layout()
                ly.dbu = lib.dbu
                top = ly.create_cell(TOP)
                top.copy_tree(cell)
                top.flatten(True)
                rec = {'gds': None, 'source': src.name, 'cell': name, 'variant': v, 'op': 'original'}
                if v:
                    layers = [li for li in ly.layer_indexes() if not top.shapes(li).is_empty()]
                    li = rng.choice(layers)
                    shapes = [s for s in top.shapes(li).each() if s.is_box() or s.is_polygon() or s.is_path()]
                    if not shapes:
                        continue
                    s = rng.choice(shapes)
                    op = rng.choice(OPS)
                    d = rng.choice(DELTAS)
                    info = ly.get_info(li)
                    poly = s.polygon
                    dd = int(round(d/ly.dbu))
                    if op == 'delete':
                        s.delete()
                    else:
                        if op == 'shift_x':
                            new = poly.moved(dd, 0)
                        elif op == 'shift_y':
                            new = poly.moved(0, dd)
                        elif op == 'grow':
                            new = poly.sized(dd)
                        else:
                            new = poly.sized(-dd)
                        s.delete()
                        if new.num_points() >= 3 and new.area() > 0:
                            top.shapes(li).insert(new)
                    bb = poly.bbox()
                    rec.update(op=op, delta_um=d, layer=f'{info.layer}/{info.datatype}',
                               near_um=[bb.left*ly.dbu, bb.bottom*ly.dbu, bb.right*ly.dbu, bb.top*ly.dbu])
                fname = f'{len(manifest):04d}-{name}-v{v}.gds'.replace('/', '_')
                ly.write(str(out/fname))
                rec['gds'] = fname
                # Hash the saved file, the same way `hash` reads any corpus folder.
                rec['geometry_sha256'], rec['polygons'] = _file_geometry(out/fname)
                manifest.append(rec)
    doc = {'seed': seed, 'per_cell': per, 'sources': list(SOURCES), 'records': manifest}
    (out/'manifest.json').write_text(json.dumps(doc, indent=1)+'\n', encoding='utf-8')
    print('wrote', len(manifest))


def _hash(gds_dir, out):
    result = {}
    for path in sorted(gds_dir.glob('*.gds')):
        digest, count = _file_geometry(path)
        result[path.name] = {'geometry_sha256': digest, 'polygons': count}
    out.write_text(json.dumps(result, indent=1)+'\n', encoding='utf-8')
    print('hashed', len(result))


def _batch():
    """Entry inside `klayout -b -r mutate.py`; arguments come from SSC_MUTATE_* variables."""
    mode = os.environ['SSC_MUTATE_MODE']
    if mode == 'generate':
        _generate(Path(os.environ['SSC_MUTATE_KIT']), Path(os.environ['SSC_MUTATE_OUT']),
                  int(os.environ['SSC_MUTATE_SEED']), int(os.environ['SSC_MUTATE_PER_CELL']))
    elif mode == 'hash':
        _hash(Path(os.environ['SSC_MUTATE_GDS_DIR']), Path(os.environ['SSC_MUTATE_OUT']))
    else:
        raise ValueError('unknown SSC_MUTATE_MODE: '+mode)


def run_klayout(mode, timeout=3600, klayout='klayout', **values):
    """Run this file as a KLayout batch; values become SSC_MUTATE_<NAME> variables."""
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', SSC_MUTATE_MODE=mode,
               **{'SSC_MUTATE_'+key.upper(): str(value) for key, value in values.items()})
    done = subprocess.run([klayout, '-b', '-r', str(Path(__file__).resolve())], env=env,
                          capture_output=True, text=True, timeout=timeout)
    if done.returncode:
        raise RuntimeError(f'KLayout mutate {mode} failed ({done.returncode}):\n{done.stdout}{done.stderr}')
    return done.stdout


def generate(kit, out, seed=SEED, per_cell=PER_CELL, klayout='klayout'):
    run_klayout('generate', klayout=klayout, kit=Path(kit).resolve(), out=Path(out).resolve(),
                seed=seed, per_cell=per_cell)
    return json.loads((Path(out)/'manifest.json').read_text(encoding='utf-8'))


def hash_folder(gds_dir, out, klayout='klayout'):
    run_klayout('hash', klayout=klayout, gds_dir=Path(gds_dir).resolve(), out=Path(out).resolve())
    return json.loads(Path(out).read_text(encoding='utf-8'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    gen = commands.add_parser('generate', help='write the mutated GDS files and manifest.json')
    gen.add_argument('--kit', type=Path, required=True, help='unpacked NSPL_05CMOS_PDK_260820 folder')
    gen.add_argument('--out', type=Path, required=True, help='new folder')
    gen.add_argument('--seed', type=int, default=SEED)
    gen.add_argument('--per-cell', type=int, default=PER_CELL)
    hasher = commands.add_parser('hash', help='geometry_sha256 of every GDS in a folder')
    hasher.add_argument('--gds-dir', type=Path, required=True)
    hasher.add_argument('--out', type=Path, required=True)
    for sub in (gen, hasher):
        sub.add_argument('--klayout', default='klayout')
    args = parser.parse_args(argv)
    if args.command == 'generate':
        manifest = generate(args.kit, args.out, args.seed, args.per_cell, args.klayout)
        print(f'{len(manifest["records"])} GDS in {args.out}')
    else:
        print(f'{len(hash_folder(args.gds_dir, args.out, args.klayout))} GDS hashed')
    return 0


if os.environ.get('SSC_MUTATE_MODE'):
    _batch()
elif __name__ == '__main__':
    sys.exit(main())
