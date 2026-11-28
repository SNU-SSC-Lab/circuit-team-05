"""Measured NSPL comparison. Team01 reference is read from a separate checkout.

This experiment calls the GPL-3.0 Team01 Qflow example's setup/DEF adapters;
it does not copy them or modify that checkout. The reference commit and file
hashes are recorded. Run on Linux with --team01-root pointing to its src/.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from nspl import prepare, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk', type=Path, required=True)
    parser.add_argument('--team01-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--openroad', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error('--out must be a new directory')
    out.mkdir(parents=True)
    reference = args.team01_root.resolve()/'development/experiments/M0-09-qflow'
    sys.path.insert(0, str(reference))
    spec = importlib.util.spec_from_file_location('team01_qflow', reference/'run.py')
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    result = {'scope': 'experimental core comparison; RC unqualified',
              'reference_commit': '4c6542af1a2943dde15cfcaf3e1927151e474f25',
              'reference_files': {p.name: sha(p) for p in reference.glob('*.py')}, 'stages': {}}

    def save():
        (out/'comparison.json').write_text(json.dumps(result, indent=2)+'\n')

    def run(name, argv, cwd, env):
        start = time.perf_counter()
        with (out/(name+'.log')).open('w') as log:
            p = subprocess.run(list(map(str, argv)), cwd=cwd, env=env, stdout=log,
                               stderr=subprocess.STDOUT, timeout=300)
        result['stages'][name] = {'exit_code': p.returncode,
                                 'wall_seconds': round(time.perf_counter()-start, 3)}
        save()
        print(name, result['stages'][name], flush=True)
        if p.returncode:
            raise RuntimeError(name + ' failed; see log')

    qflow = out/'qflow'
    digital = args.pdk.resolve()/(ref.STEM+'_PnR')
    ref.setup(qflow, digital)
    # Replace only setup-created symlinks with our audited, private copies.
    prepared = out/'audited'
    prepare(args.pdk, prepared)
    for name in ['cells.lib', 'cells.lef', 'technology.lef', 'cells.gds', 'cells.cdl']:
        (qflow/'tech'/name).unlink()
        shutil.copyfile(prepared/name, qflow/'tech'/name)
    # This host's Qflow was compiled before Yosys was installed. Supply paths
    # in this experiment only, without changing its shared scripts or links.
    bindir = qflow/'bin'
    bindir.mkdir()
    for executable in Path('/usr/local/share/qflow/bin').iterdir():
        (bindir/executable.name).symlink_to(executable)
    for name in ['yosys', 'yosys-abc']:
        if not (bindir/name).exists():
            (bindir/name).symlink_to(shutil.which(name))
    project = qflow/'project_vars.sh'
    project.write_text(project.read_text()+f'\nset synthesis_tool=yosys\nset bindir={bindir}\n')
    env = dict(os.environ, QFLOW_TECH_DIR=str(qflow/'tech'),
               QT_QPA_PLATFORM='offscreen', M09_OUT=str(qflow))
    try:
        for stage in ['synthesize', 'place', 'route']:
            run('qflow-'+stage, ['qflow', '-T', 'nspl12t', stage, ref.TOP], qflow, env)
            if stage == 'synthesize':
                shutil.copyfile(qflow/'synthesis'/f'{ref.TOP}.rtlnopwr.v', out/'common.v')
        ys = qflow/'route-json.ys'
        ys.write_text(f'''read_liberty -lib {prepared/'cells.lib'}
read_verilog {qflow/'synthesis'/f'{ref.TOP}.rtlnopwr.v'}
hierarchy -check -top {ref.TOP}
check -assert
write_json {qflow/'synthesis/route.json'}
''')
        run('qflow-netlist', ['yosys', '-Q', '-s', ys], qflow, env)
        route_log = (qflow/'log/route.log').read_text()
        if not re.search(r'Final: No failed routes!', route_log):
            raise RuntimeError('QRouter did not report completed routing')
        raw = (qflow/'layout'/f'{ref.TOP}.def').read_text()
        fixed, changes = ref.normalize_def(raw)
        fixed, power_changes = ref.power_pins(fixed)
        (qflow/'layout/handoff.def').write_text(fixed)
        result['qflow_def_changes'] = changes + power_changes
        run('qflow-gds', ['klayout', '-b', '-r', reference/'gds_check.py'], qflow, env)
        result['qflow_geometry'] = json.loads((qflow/'gds-check.json').read_text())
        result['qflow_timing_constraints_applied'] = False
    except Exception as error:
        result['qflow_error'] = str(error)
        save()
    if not (out/'common.v').exists():
        raise RuntimeError('No common mapped netlist for OpenROAD')
    road = out/'openroad'
    road.mkdir()
    for name in ['cells.lib', 'cells.lef', 'technology.lef']:
        shutil.copyfile(prepared/name, road/name)
    clean = road/'canonical.ys'
    clean.write_text(f'''read_liberty -lib cells.lib
read_verilog {out/'common.v'}
hierarchy -check -top {ref.TOP}
opt_clean -purge
write_verilog -noattr -noexpr input.v
''')
    run('common-canonical', ['yosys', '-Q', '-s', clean], road, dict(os.environ))
    (road/'constraints.sdc').write_text('''create_clock -name clk -period 100 [get_ports clk]
set_input_delay 50 -clock clk [get_ports {din rst_n}]
set_output_delay 20 -clock clk [all_outputs]
set_load 0.5 [all_outputs]
''')
    script = Path(__file__).with_name('compare_openroad.tcl')
    env = dict(os.environ)
    base = args.openroad.resolve().parents[2]
    env['LD_LIBRARY_PATH'] = ':'.join([str(base/'usr/lib/x86_64-linux-gnu'),
                                     str(base/'opt/or-tools/lib'), env.get('LD_LIBRARY_PATH', '')])
    try:
        run('openroad', [args.openroad, '-exit', script], road, env)
    except Exception as error:
        result['openroad_error'] = str(error)
    save()


if __name__ == '__main__':
    main()
