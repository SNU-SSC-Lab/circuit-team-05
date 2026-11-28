"""Compare each used NSPL master's original GDS with its independent CDL."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_physical import lvs_verdict, executable
from lvs_reduce import reduce_netlist

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mapped', type=Path)
    parser.add_argument('--top')
    parser.add_argument('--all', action='store_true', help='all CDL cells except physical-only FILL cells')
    parser.add_argument('--gds', type=Path, required=True)
    parser.add_argument('--cdl', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if args.all:
        cells = sorted({m[1] for m in re.finditer(r'^\.SUBCKT\s+(\w+)', args.cdl.read_text(), re.M | re.I)
                        if not m[1].startswith('FILL')})
    else:
        if not args.mapped or not args.top:
            parser.error('--mapped and --top required unless --all')
        module = json.loads(args.mapped.read_text())['modules'][args.top]
        cells = sorted({c['type'] for c in module['cells'].values()})
    if any(not re.fullmatch(r'\w+', name) for name in cells):
        raise ValueError('unsupported cell name')
    env = dict(os.environ, SSC_GDS=str(args.gds.resolve()), SSC_TOPS=','.join(cells),
               SSC_SPICE_DIR=str(out), QT_QPA_PLATFORM='offscreen')
    with (out/'extraction.log').open('w') as log:
        subprocess.run(['klayout', '-b', '-r', str(HERE/'extract.py')], env=env,
                       stdout=log, stderr=subprocess.STDOUT, timeout=180, check=True)
    shutil.copyfile(args.cdl, out/'reference.spice')
    # Both sides get the same kit-deck reductions before Netgen (lvs_reduce.py).
    reduce_netlist(out/'reference.spice', out/'reference.reduced.spice')
    results = {}
    for cell in cells:
        reduce_netlist(out/(cell+'.spice'), out/(cell+'.reduced.spice'))
        script = out/(cell+'.tcl')
        script.write_text('lvs [list {'+str(out/(cell+'.reduced.spice'))+'} '+cell+'] '
                          '[list {'+str(out/'reference.reduced.spice')+'} '+cell+'] '
                          '{'+str(ROOT/'verification/asic/netgen_setup.tcl')+'} '+cell+'.lvs.log -json\n')
        with (out/(cell+'.netgen.log')).open('w') as log:
            subprocess.run([executable('netgen'), '-batch', 'source', str(script)], cwd=out,
                           stdout=log, stderr=subprocess.STDOUT, timeout=90, check=True)
        report = (out/(cell+'.lvs.log')).read_text()
        data = json.loads((out/(cell+'.lvs.json')).read_text())
        results[cell] = {'pass': lvs_verdict(report, data, cell),
                         'final': report.rsplit('Final result:', 1)[-1].strip()}
        print(cell, results[cell]['pass'], flush=True)
    (out/'qualification.json').write_text(json.dumps(results, indent=2)+'\n')


if __name__ == '__main__':
    main()
