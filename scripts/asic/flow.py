"""Own-chip build driver. Core experiment first; strict readiness stays separate."""
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
from .report import render

import pdk
import run_physical
from .nspl import prepare, sha
from .reference import convert
from .pinplan import make_plan, tcl as pin_tcl

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORE_CHECKS = {'asic-input', 'asic-synth', 'asic-pnr', 'asic-cts', 'asic-route',
               'asic-gds', 'asic-drc-subset', 'asic-extract', 'asic-lvs', 'asic-gate',
               'asic-pex', 'asic-drc', 'asic-estimated-sta'}
CHIP_CHECKS = {'asic-chip-gds', 'asic-chip-connectivity', 'asic-chip-lvs',
               'asic-chip-timing', 'asic-pinmap'}
# --experimental: the fixed set of process-qualification gaps a manual trial may leave unsupported.
UNQUALIFIED_DEFAULT = frozenset({'asic-pex', 'asic-drc', 'asic-chip-lvs', 'asic-chip-timing', 'asic-pinmap'})
# --gate (SPEC 0019): the merge gate reads the same kind of set from the unverified list instead.
UNVERIFIED = ROOT/'verification/reliability/unverified.json'


def outcome(checks, error=None, target='core'):
    required = CORE_CHECKS | (CHIP_CHECKS if target == 'chip' else set())
    if error or any(c.get('status') == 'fail' for c in checks.values()):
        return 'fail'
    if not required.issubset(checks) or any(c.get('status') != 'pass' for c in checks.values()):
        return 'incomplete'
    return 'pass'


def load_allowed(path=UNVERIFIED):
    """Checks the unverified list lets stay `unsupported`: the union of every item's allows_checks."""
    known = CORE_CHECKS | CHIP_CHECKS
    allowed = set()
    for item in json.loads(Path(path).read_text(encoding='utf-8'))['items']:
        names = set(item.get('allows_checks', ()))
        if names - known:  # a misspelt name would silently allow nothing and hide the item's intent
            raise ValueError(f'unverified item {item.get("id")!r} names unknown checks: {sorted(names-known)}')
        allowed |= names
    return frozenset(allowed)


def exit_status(checks, error=None, target='core', allowed=frozenset()):
    """0 on a full pass; otherwise 0 only when every non-pass check is `unsupported` and in `allowed`."""
    status = outcome(checks, error, target)
    if status == 'pass':
        return 0
    required = CORE_CHECKS | (CHIP_CHECKS if target == 'chip' else set())
    if not allowed or status != 'incomplete' or not required.issubset(checks):
        return 1
    return int(any(c.get('status') != 'pass' and
                   not (name in allowed and c.get('status') == 'unsupported')
                   for name, c in checks.items()))


def estimated_sta(log):
    """asic-estimated-sta from the OpenROAD log: setup and hold worst slack must both be >= 0."""
    slacks = [float(s) for s in re.findall(r'worst slack(?: max| min)?\s+(-?[\d.]+)', log)]
    return {'status': 'pass' if len(slacks) == 2 and min(slacks) >= 0 else 'fail',
            'slacks_ns': slacks, 'clock': 'propagated', 'corner': 'TT 5V 25C',
            'derates': 'none; typical trial only',
            'rc': 'uncalibrated global-route estimate; not qualified PEX'}


def tool_environment(executable):
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    base = Path(executable).resolve().parents[2]
    candidates = [base/'usr/lib/x86_64-linux-gnu', base/'opt/or-tools/lib']
    env['LD_LIBRARY_PATH'] = ':'.join([str(p) for p in candidates if p.is_dir()]
                                     + [env.get('LD_LIBRARY_PATH', '')])
    return env


def run_core(args):
    out = args.out.resolve()
    if out.exists():
        raise ValueError('result directory already exists; choose a new path')
    out.mkdir(parents=True)
    start = time.perf_counter()
    checks = {}
    result = {'target': args.target, 'top': pdk.DESIGN['top'], 'scope': 'experimental',
              'mode': args.mode, 'allowed_unsupported': sorted(args.allowed),
              'commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
              'dirty_checkout': bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True).strip()),
              'status': 'running', 'checks': checks, 'ready_for_submission': False}
    source_files = set(pdk.sources()) | set(HERE.glob('*.py')) | set(HERE.glob('*.tcl'))
    source_files |= set((ROOT/'verification/asic').glob('*')) | {ROOT/'scripts/pdk.py', ROOT/'scripts/run_physical.py'}
    source_files |= set((ROOT/'tests/rtl').glob('*.py'))
    source_files |= {ROOT/name for name in ['scripts/run_asic.py', 'scripts/run_rtl.py',
                     'requirements-ci.txt', 'verification/designs/ternary8.json',
                     'verification/scenarios.json', 'verification/pdk/pdk.toml',
                     'verification/reliability/unverified.json', '.github/workflows/asic.yml']}
    result['source_hashes'] = {str(p.relative_to(ROOT)): sha(p) for p in sorted(source_files) if p.is_file()}

    def write():
        result['wall_seconds'] = round(time.perf_counter()-start, 3)
        (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')

    def command(stage, argv, cwd=out, env=None, timeout=600):
        before = time.perf_counter()
        log = out/(stage+'.log')
        resource_file = out/(stage+'.resources')
        invocation = list(map(str, argv))
        if Path('/usr/bin/time').is_file():
            invocation = ['/usr/bin/time', '-f', '%M %U %S %e', '-o', str(resource_file), *invocation]
        try:
            with log.open('w') as stream:
                execution = subprocess.Popen(invocation, cwd=cwd, env=env, stdout=stream,
                                             stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = execution.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(execution.pid, signal.SIGKILL)
                    execution.wait()
                    code = 124
        except OSError as error:
            log.write_text(str(error)+'\n')
            code = 127
        checks[stage] = {'status': 'pass' if code == 0 else 'fail',
                         'wall_seconds': round(time.perf_counter()-before, 3),
                         'exit_code': code, 'log': log.name}
        if resource_file.is_file():
            values = resource_file.read_text().splitlines()[-1].split()
            if len(values) == 4:
                checks[stage].update(peak_rss_kib=int(values[0]), user_seconds=float(values[1]),
                                     system_seconds=float(values[2]))
        write()
        print(stage, checks[stage]['status'], checks[stage]['wall_seconds'], flush=True)
        if code:
            raise RuntimeError(stage+' failed; see '+str(log))

    try:
        result['tools'] = {}
        for name, argv in {'openroad': [args.openroad, '-version'], 'yosys': ['yosys', '-V'],
                           'klayout': ['klayout', '-v'], 'iverilog': ['iverilog', '-V']}.items():
            version = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            if version.returncode:
                raise RuntimeError(name+' version check failed')
            result['tools'][name] = (version.stdout or version.stderr).splitlines()[0]
        lock = json.loads((ROOT/'verification/asic/tools.json').read_text())
        if result['tools']['openroad'].strip() != lock['openroad_version']:
            raise RuntimeError('OpenROAD differs from reviewed tools.json')
        netgen = subprocess.run([run_physical.executable('netgen'), '-batch'],
                                capture_output=True, text=True, timeout=30)
        version = re.search(r'Netgen\s+1\.5\.\d+', netgen.stdout+netgen.stderr)
        if netgen.returncode or not version:
            raise RuntimeError('Netgen VLSI comparator version check failed')
        result['tools']['netgen'] = version[0]
        result['tools']['python'] = sys.version.split()[0]
        result['tool_lock_sha256'] = sha(ROOT/'verification/asic/tools.json')
        prepare(args.pdk.resolve(), out/'technology')
        checks['asic-input'] = {'status': 'pass', 'adapter': 'technology/adapter.json'}
        top = result['top']
        lib = out/'technology/cells.lib'
        restrictions = tomllib.loads((ROOT/'verification/asic/cells.toml').read_text())
        checks['asic-synth'], netlist = pdk.synthesize(pdk.sources(), top, lib, out/'synth',
                                                     dont_use=restrictions['dont_use'])
        checks['asic-synth']['excluded_cells'] = restrictions['dont_use']
        write()
        if checks['asic-synth']['status'] != 'pass':
            raise RuntimeError('mapped synthesis failed')
        area = checks['asic-synth']['area_um2']
        width = math.ceil(math.sqrt(area/0.30)/3.2)*3.2
        height = math.ceil(math.sqrt(area/0.30)/36)*36
        road = out/'pnr'
        road.mkdir()
        for name in ['cells.lib', 'cells.lef', 'technology.lef']:
            shutil.copyfile(out/'technology'/name, road/name)
        shutil.copyfile(netlist, road/'input.v')
        (road/'settings.tcl').write_text(f'set top {top}\nset dont_use {{{" ".join(restrictions["dont_use"])}}}\nset die {{0 0 {width+32} {height+72}}}\n'
                                        f'set core {{16 36 {width+16} {height+36}}}\n')
        if args.target == 'chip':
            plan = make_plan(ROOT/'verification/asic/pinmap.toml', width+32, height+72)
            (out/'chip-plan.json').write_text(json.dumps(plan, indent=2)+'\n')
            (road/'io.tcl').write_text(pin_tcl(plan))
        (road/'constraints.sdc').write_text('''create_clock -name CLK -period 100 [get_ports CLK]
set data_in [delete_from_list [all_inputs] [get_ports CLK]]
set_input_delay 50 -clock CLK $data_in
set_output_delay 20 -clock CLK [all_outputs]
set_driving_cell -lib_cell BUFX2 -pin Y $data_in
set_load 0.5 [all_outputs]
''')
        env = tool_environment(args.openroad)
        command('asic-pnr', [args.openroad, '-exit', HERE/'core_flow.tcl'], road, env)
        drc = road/'route.drc'
        if not drc.is_file() or drc.read_text().strip():
            checks['asic-route'] = {'status': 'fail', 'detail': 'missing or nonzero router DRC'}
        else:
            checks['asic-route'] = {'status': 'pass', 'router_drc': 0}
        timing = (out/'asic-pnr.log').read_text()
        checks['asic-estimated-sta'] = estimated_sta(timing)
        sink_counts = re.findall(r'Total number of Sinks:\s*(\d+)', timing)
        sinks = int(sink_counts[-1]) if sink_counts else None
        checks['asic-cts'] = {'status': 'pass' if sinks == checks['asic-synth']['flops'] else 'fail',
                              'clock_sinks': sinks, 'expected_flops': checks['asic-synth']['flops']}
        env.update(SSC_DEF=str(road/'final.def'), SSC_TECH_LEF=str(road/'technology.lef'),
                   SSC_CELL_LEF=str(road/'cells.lef'), SSC_CELL_GDS=str(out/'technology/cells.gds'),
                   SSC_TOP=top, SSC_GDS_OUT=str(out/(top+'.gds')))
        command('asic-gds', ['klayout', '-b', '-r', HERE/'stream.py'], env=env)
        env.update(SSC_GDS=str(out/(top+'.gds')), SSC_DRC_OUT=str(out/'drc-subset.json'))
        # Run independent checks even when a routing subset violation exists.
        try:
            command('asic-drc-subset', ['klayout', '-b', '-r', HERE/'drc.py'], env=env)
        except RuntimeError:
            if not (out/'drc-subset.json').is_file():
                raise
        checks['asic-drc-subset']['errors'] = json.loads((out/'drc-subset.json').read_text())['errors']
        if args.target == 'chip':
            try:
                env.update(SSC_PAD_ROOT=str(args.pdk.resolve()), SSC_CORE_GDS=str(out/(top+'.gds')),
                           SSC_CORE_TOP=top, SSC_CHIP_PLAN=str(out/'chip-plan.json'),
                           SSC_POWER_ANCHORS=str(road/'power-anchors.txt'), SSC_CHIP_OUT=str(out/'ternary8_sop28.gds'))
                command('asic-chip-gds', ['klayout', '-b', '-r', HERE/'chip.py'], env=env)
                env.update(SSC_CHIP_GDS=str(out/'ternary8_sop28.gds'), SSC_CHIP_ASSEMBLY=str(out/'ternary8_sop28.json'),
                           SSC_CHIP_CHECK_OUT=str(out/'chip-connectivity.json'))
                command('asic-chip-connectivity', ['klayout', '-b', '-r', HERE/'chip_check.py'], env=env)
            except Exception as error:
                result['chip_error'] = str(error)
                if not any(checks.get(name, {}).get('status') == 'fail' for name in CHIP_CHECKS):
                    checks['asic-chip-connectivity'] = {'status': 'fail', 'detail': str(error)}
                write()
            checks['asic-chip-lvs'] = {'status': 'unsupported', 'detail': 'core LVS is separate; GPIO/ESD extraction and independent GPIO reference not qualified'}
            checks['asic-chip-timing'] = {'status': 'unsupported', 'detail': 'qualified GPIO and package timing/RC unavailable'}
            checks['asic-pinmap'] = {'status': 'unsupported', 'detail': 'proposed 28 connected pads vs guide <=25 used pins; team review required'}
        lvs = out/'lvs'
        lvs.mkdir()
        env.update(SSC_GDS=str(out/(top+'.gds')), SSC_SPICE=str(lvs/'layout.spice'))
        command('asic-extract', ['klayout', '-b', '-r', HERE/'extract.py'], env=env)
        code, message = pdk.yosys([f'read_liberty -lib {lib}', f'read_verilog {road/"final.v"}',
                                  f'hierarchy -check -top {top}', f'write_json {lvs/"mapped.json"}'], lvs, 'mapped')
        if code:
            raise RuntimeError('final mapped netlist invalid: '+message)
        cdl = out/'technology/cells.cdl'
        (lvs/'schematic.spice').write_text(convert(json.loads((lvs/'mapped.json').read_text()), cdl.read_text(), top))
        shutil.copyfile(cdl, lvs/'cells.spice')
        (lvs/'run.tcl').write_text(run_physical.NETGEN_SCRIPT)
        env.update(SSC_EXTRACTED=str(lvs/'layout.spice'), SSC_SCHEMATIC=str(lvs/'schematic.spice'),
                   SSC_SETUP=str(ROOT/'verification/asic/netgen_setup.tcl'))
        command('asic-netgen', [run_physical.executable('netgen'), '-batch', 'source', lvs/'run.tcl'], lvs, env)
        report = (lvs/'lvs.log').read_text()
        cells = json.loads((lvs/'lvs.json').read_text())
        match = (lvs/'netgen-complete.txt').is_file() and run_physical.lvs_verdict(report, cells, top)
        checks['asic-lvs'] = {'status': 'pass' if match else 'fail', 'report': 'lvs/lvs.log'}
        checks['asic-lvs']['devices'] = json.loads((lvs/'layout.json').read_text())['devices']
        write()
        print('asic-lvs', checks['asic-lvs']['status'], flush=True)
        checks['asic-gate'] = pdk.gate_level(road/'final.v', top, lib, out/'gate', 'pr')
        checks['asic-gate']['wall_seconds'] = checks['asic-gate'].get('seconds')
        checks['asic-pex'] = {'status': 'unsupported', 'detail': 'NSPL calibrated RC rules unavailable; estimated.spef is a global-route estimate'}
        checks['asic-drc'] = {'status': 'unsupported', 'detail': 'full NSPL rule coverage not yet qualified; router DRC is separate'}
        result['artifacts'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*')
                               if p.is_file() and p.suffix in {'.gds', '.spice', '.spef', '.sdc', '.def', '.v', '.odb'}}
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    changed = [name for name, digest in result['source_hashes'].items()
               if not (ROOT/name).is_file() or sha(ROOT/name) != digest]
    if changed:
        result['error'] = 'Inputs changed during this run: '+', '.join(changed)
    for name in sorted(CORE_CHECKS | (CHIP_CHECKS if args.target == 'chip' else set())):
        checks.setdefault(name, {'status': 'not_run', 'detail': 'earlier execution failed; see error and logs'})
    status = outcome(checks, result.get('error'), args.target)
    actual_failure = status == 'fail'
    result['execution_status'] = 'fail' if actual_failure else 'pass'
    result['status'] = status
    write()
    render(result, out)
    return exit_status(checks, result.get('error'), args.target, args.allowed)
