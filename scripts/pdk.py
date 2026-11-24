"""Checks that need the 4th-run PDK (verification/pdk/pdk.toml). SPEC 0015.

Ported from SNU-SSC-Lab/circuit-integration harness/pdk.py at 60c7acc. The gate-level step runs this
team's own top-level cocotb tests (scripts/run_rtl.py, tests/rtl/test_top.py), not the integration
tester.

1. synthesis   Yosys maps the RTL onto the kit's standard cells. Fails on anything that would not
               become real gates: unmapped cells, forbidden cells (latch, tri-state), logic loops,
               undriven or multiply driven nets.
2. gate_level  The top-level tests, run on that netlist. Each cell behaves as its Liberty `function`
               says (what synthesis and timing believe), not as the kit's hand-written Verilog
               models. Catches what RTL simulation hides: X from registers without reset,
               simulation-only constructs, synthesis/simulation mismatches.
3. timing      OpenSTA on the netlist at the 10 MHz clock, with the board assumptions and the
               slow-silicon derating of pdk.toml. Fails on negative setup or hold slack,
               combinational loops and unclocked registers.

The team's own netlists in mychip/1-synth and mychip/2-pnr get checks 2 and 3 the same way.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDK = tomllib.loads((ROOT / 'verification' / 'pdk' / 'pdk.toml').read_text(encoding='utf-8'))
DESIGN = json.loads((ROOT / 'verification' / 'designs' / 'ternary8.json').read_text(encoding='utf-8'))
CLOCK_NS = PDK['timing']['clock_period_ns']
YOSYS_PROBLEM = re.compile(r'logic loop|conflicting|multiple drivers|is used but has no driver', re.I)
# Gate-level test groups of scripts/run_rtl.py per tier: every PR runs the top-level integration
# group; the full tier (manual run) adds the regression group.
TIERS = {'pr': ('integration',), 'full': ('integration', 'regression')}


def locate(pdk_root):
    """(liberty path, None) when the kit under pdk_root is the one in pdk.toml, else (None, why)."""
    if not pdk_root:
        return None, 'no PDK given (set SSC_PDK or --pdk; scripts/fetch_pdk.sh downloads it)'
    lib = Path(pdk_root) / PDK['digital']['liberty']
    if not lib.is_file():
        return None, f"{PDK['digital']['liberty']} not found under {pdk_root}"
    digest = hashlib.sha256(lib.read_bytes()).hexdigest()
    if digest != PDK['digital']['liberty_sha256']:
        return None, f"liberty sha256 {digest[:12]}... is not the one of {PDK['name']}"
    return lib, None


def yosys(script, work, name):
    path = work / f'{name}.ys'
    path.write_text('\n'.join(script) + '\n', encoding='utf-8')
    run = subprocess.run(['yosys', '-q', '-l', str(work / f'{name}.log'), '-s', str(path)],
                         capture_output=True, text=True)
    return run.returncode, (run.stderr or run.stdout).strip()


def q(path):
    """A path for a Yosys script, which splits on blanks and keeps quote marks in file names."""
    if any(ch.isspace() for ch in str(path)):
        raise ValueError(f'file names must not contain blanks: {path}')
    return str(path)


def synthesize(files, top, lib, work):
    """RTL -> netlist of kit cells. Returns (check, netlist path or None)."""
    digital = PDK['digital']
    work.mkdir(parents=True, exist_ok=True)
    netlist, stat, check = work / 'netlist.v', work / 'stat.json', work / 'check.txt'
    code, err = yosys([
        f'read_liberty -lib {q(lib)}',
        'read_verilog -sv ' + ' '.join(q(f) for f in files),
        f'hierarchy -check -top {top}',
        f'synth -flatten -top {top}',
        # The kit's only flops: DFFPOSX1, DFFNEGX1 and DFFSRX1 (async clear and preset, active low).
        'dfflegalize -cell $_DFF_P_ 01 -cell $_DFF_N_ 01 -cell $_DFFSR_PNN_ 01 -cell $_DLATCH_P_ 01',
        f'dfflibmap -liberty {q(lib)}',
        f'abc -liberty {q(lib)}',
        'opt_clean -purge',
        f"hilomap -singleton -hicell {' '.join(digital['tie_high'])} -locell {' '.join(digital['tie_low'])}",
        'opt_clean -purge',
        f'tee -q -o {q(stat)} stat -json -liberty {q(lib)}',
        f'tee -q -o {q(check)} check',
        f'write_verilog -noattr -noexpr -nohex -nodec {q(netlist)}',
    ], work, 'synth')
    if code != 0:
        return {'status': 'fail', 'detail': 'Yosys could not synthesize the RTL: ' + err[-400:]}, None
    # Newer Yosys keeps `wire signed` after flattening; OpenSTA's Verilog reader rejects it, and in a
    # netlist of cells and plain connections signedness has no meaning.
    text = netlist.read_text(encoding='utf-8')
    netlist.write_text(re.sub(r'\b(wire|input|output|inout|reg)\s+signed\b', r'\1', text), encoding='utf-8')
    design = json.loads(stat.read_text(encoding='utf-8'))['design']
    cells = design.get('num_cells_by_type', {})
    unmapped = sorted(c for c in cells if c.startswith('$'))
    forbidden = sorted(c for c in cells if c in digital['forbidden_cells'])
    problems = [l.strip() for l in check.read_text(encoding='utf-8').splitlines() if YOSYS_PROBLEM.search(l)]
    problems = [f'not a kit cell: {c} (latch or unsupported construct)' for c in unmapped] + \
               [f'forbidden cell {c} x{cells[c]}' for c in forbidden] + problems
    flops = sum(n for c, n in cells.items() if c.startswith('DFF'))
    result = {'status': 'fail' if problems else 'pass', 'problems': problems[:20],
              'cells': design.get('num_cells'), 'flops': flops, 'area_um2': round(design.get('area', 0), 1),
              'by_type': dict(sorted(cells.items()))}
    return result, netlist


def gate_model(netlist, top, lib, work):
    """The netlist with every kit cell replaced by its Liberty function, as plain Verilog."""
    work.mkdir(parents=True, exist_ok=True)
    model = work / 'gate_model.v'
    code, err = yosys([f'read_liberty {q(lib)}', f'read_verilog {q(netlist)}', f'hierarchy -check -top {top}',
                       'flatten', 'opt_clean', f'write_verilog -noattr {q(model)}'], work, 'gate_model')
    if code != 0:
        raise RuntimeError('netlist uses cells or pins the kit does not have: ' + err[-400:])
    return model


def failures(work):
    """Failure messages of the cocotb JUnit files under work, for the report."""
    found = []
    for xml in sorted(Path(work).rglob('results.xml')):
        try:
            cases = ET.parse(xml).getroot().iter('testcase')
        except ET.ParseError:
            continue
        for case in cases:
            for bad in (case.find('failure'), case.find('error')):
                if bad is not None:
                    found.append(f"{case.get('name')}: {(bad.get('error_msg') or bad.get('message') or bad.text or '').strip()[:200]}")
    return found


def team_tests(sources, work, tier='pr'):
    """This team's top-level cocotb tests (scripts/run_rtl.py groups) on the given Verilog sources."""
    import run_rtl
    config = dict(DESIGN, sources=[str(Path(s).resolve()) for s in sources])
    tests, jobs, start = {}, 0, time.perf_counter()
    try:
        for suite in TIERS[tier]:
            data = run_rtl.simulate(config, suite, work / 'build', work / suite)
            for record in data['tests']:
                tests[record['test']] = 'pass'
                jobs += record['stats'].get('jobs', 0)
    except Exception as exc:
        detail = '; '.join(failures(work)) or f'{type(exc).__name__}: {exc}'
        return {'status': 'fail', 'tests': tests, 'detail': detail[:600],
                'seconds': round(time.perf_counter() - start, 1)}
    return {'status': 'pass', 'tests': tests, 'jobs': jobs, 'groups': list(TIERS[tier]),
            'seconds': round(time.perf_counter() - start, 1)}


def gate_level(netlist, top, lib, work, tier='pr'):
    try:
        model = gate_model(netlist, top, lib, work)
    except Exception as exc:
        return {'status': 'fail', 'detail': f'{type(exc).__name__}: {exc}'[:500]}
    return team_tests([model], work / 'sim', tier)


STA_SCRIPT = """\
read_liberty {lib}
read_verilog {netlist}
link_design {top}
{spef_line}create_clock -name CLK -period {period} [get_ports CLK]
set data_in [delete_from_list [all_inputs] [get_ports CLK]]
set_input_delay {input_delay} -clock CLK $data_in
set_output_delay {output_delay} -clock CLK [all_outputs]
set_driving_cell -lib_cell {drive_cell} -pin {drive_pin} $data_in
set_load {load} [all_outputs]
set_timing_derate -late {late}
set_timing_derate -early {early}
puts "=== check_setup"
check_setup -verbose
puts "=== setup"
report_checks -path_delay max -digits 2 -fields {{fanout cap slew}}
puts "=== hold"
report_checks -path_delay min -digits 2
puts "=== summary"
report_worst_slack -max -digits 3
report_worst_slack -min -digits 3
exit
"""


def timing(netlist, top, lib, work, period=None, spef=None):
    if not shutil.which('sta'):
        return {'status': 'fail', 'detail': 'OpenSTA (sta) is not installed (scripts/build_opensta.sh)'}
    t = PDK['timing']
    period = period or CLOCK_NS
    work.mkdir(parents=True, exist_ok=True)
    script = work / 'sta.tcl'
    script.write_text(STA_SCRIPT.format(
        lib=lib, netlist=netlist, top=top, period=period, spef_line=f'read_spef {spef}\n' if spef else '',
        input_delay=t['input_delay_ns'], output_delay=t['output_delay_ns'], drive_cell=t['driving_cell'][0],
        drive_pin=t['driving_cell'][1], load=t['output_load_pf'], late=t['late_derate'],
        early=t['early_derate']), encoding='utf-8')
    run = subprocess.run(['sta', '-no_init', '-no_splash', '-exit', str(script)], capture_output=True, text=True)
    log = run.stdout + run.stderr
    (work / 'sta.log').write_text(log, encoding='utf-8')
    slacks = [float(s) for s in re.findall(r'worst slack(?: max| min)?\s+(-?[\d.]+)', log)]
    if run.returncode != 0 or len(slacks) != 2:
        return {'status': 'fail', 'detail': 'OpenSTA did not finish: ' + log.strip()[-400:]}
    setup, hold = slacks
    section = log.split('=== check_setup', 1)[-1].split('=== setup', 1)[0]
    problems = [l.strip() for l in section.splitlines() if re.search(r'loop|no clock|unclocked|unconstrained', l, re.I)]
    if setup < 0:
        problems.append(f"setup slack {setup} ns at {period} ns with delays x{t['late_derate']}")
    if hold < 0:
        problems.append(f"hold slack {hold} ns with delays x{t['early_derate']}")
    return {'status': 'fail' if problems else 'pass', 'problems': problems[:10], 'period_ns': period,
            'parasitics': bool(spef), 'setup_slack_ns': setup, 'hold_slack_ns': hold,
            'derated_path_ns': round(period - setup, 2), 'late_derate': t['late_derate'],
            'early_derate': t['early_derate'], 'critical_path': critical_path(log)}


def critical_path(log):
    """Startpoint and endpoint of the worst setup path, for the report."""
    block = log.split('=== setup', 1)[-1]
    start = re.search(r'Startpoint:\s*(\S+)', block)
    end = re.search(r'Endpoint:\s*(\S+)', block)
    return f'{start.group(1)} -> {end.group(1)}' if start and end else None


def check_pdk(files, top, lib, work, tier='pr'):
    """{synthesis, gate_level, timing} of the RTL."""
    work.mkdir(parents=True, exist_ok=True)
    try:
        synthesis, netlist = synthesize([str(f) for f in files], top, lib, work)
    except ValueError as exc:
        synthesis, netlist = {'status': 'fail', 'detail': str(exc)}, None
    checks = {'synthesis': synthesis}
    if netlist is None or synthesis['status'] != 'pass':
        skipped = {'status': 'missing', 'detail': 'skipped: synthesis did not pass'}
        return {**checks, 'gate_level': skipped, 'timing': dict(skipped)}
    checks['gate_level'] = gate_level(netlist, top, lib, work / 'gate', tier)
    checks['timing'] = timing(netlist, top, lib, work)
    return checks


def netlist_cells(netlist, top, lib, work):
    """Problems with the cells a team netlist instantiates: unknown to the kit, or forbidden."""
    stat = work / 'netlist_stat.json'
    code, err = yosys([f'read_liberty -lib {q(lib)}', f'read_verilog {q(netlist)}', f'hierarchy -check -top {top}',
                       f'tee -q -o {q(stat)} stat -json -liberty {q(lib)}'], work, 'netlist_stat')
    if code != 0:
        return [f"netlist does not elaborate on the kit's cells: {err[-300:]}"], {}
    design = json.loads(stat.read_text(encoding='utf-8'))['design']
    cells = design.get('num_cells_by_type', {})
    problems = [f'forbidden cell {c} x{n}' for c, n in sorted(cells.items()) if c in PDK['digital']['forbidden_cells']]
    problems += [f'not a kit cell: {c}' for c in sorted(cells) if c.startswith('$')]
    return problems, {'cells': design.get('num_cells'), 'area_um2': round(design.get('area', 0), 1)}


def sdc_period(path):
    """The create_clock period of a team SDC, in ns, or None when there is none."""
    text = re.sub(r'#[^\n]*', '', Path(path).read_text(encoding='utf-8', errors='replace'))
    match = re.search(r'create_clock\b[^\n]*?-period\s+([\d.]+)', text)
    return float(match.group(1)) if match else None


def check_netlists(repo, top, lib, work, tier='pr'):
    """{stage: result} for the team's own netlists in mychip/1-synth and mychip/2-pnr, each through
    the same gate-level tests and timing as the RTL. A stage without a netlist is "missing"."""
    from mychip_flow import stage_netlists, team_sdc
    found = stage_netlists(repo, top)
    sdc = team_sdc(repo, top)
    sdc_problem = None
    if sdc and (period := sdc_period(sdc)) and period > CLOCK_NS:
        sdc_problem = f'team SDC clock period {period} ns is slower than {CLOCK_NS} ns (10 MHz)'
    results = {}
    for stage in ('synth', 'pnr'):
        if stage not in found:
            results[stage] = {'status': 'missing', 'detail': f'no netlist in mychip/ for {stage} yet'}
            continue
        netlist, spef = found[stage]
        stage_work = work / 'netlist' / stage
        stage_work.mkdir(parents=True, exist_ok=True)
        try:
            problems, size = netlist_cells(netlist, top, lib, stage_work)
        except ValueError as exc:
            problems, size = [str(exc)], {}
        entry = {'file': Path(netlist).relative_to(repo).as_posix(), **size, 'parasitics': bool(spef)}
        if sdc_problem:
            problems.append(sdc_problem)
        if not any(p.startswith(('forbidden', 'not a kit', 'netlist does not', 'file names')) for p in problems):
            gate = gate_level(netlist, top, lib, stage_work / 'gate', tier)
            sta = timing(netlist, top, lib, stage_work, spef=spef)
            entry.update(gate_level=gate, timing=sta)
            if gate['status'] != 'pass':
                problems.append('gate-level tests failed: ' + gate.get('detail', '')[:300])
            if sta['status'] != 'pass':
                problems += sta.get('problems') or [sta.get('detail', 'timing failed')]
        entry.update(status='fail' if problems else 'pass', problems=problems[:20])
        results[stage] = entry
    return results


def sources():
    return [ROOT / p for p in DESIGN['sources']]


def env_pdk():
    return os.environ.get('SSC_PDK')
