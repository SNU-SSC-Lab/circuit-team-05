"""Self-test of the PDK checks: plant known bugs and require each to be caught. SPEC 0015.

Ported from SNU-SSC-Lab/circuit-integration harness/mutants.py at 60c7acc (gate_only and
timing_sanity, with this team's two mutants). A check that passes broken hardware is worse than none.

gate-only  Each mutant is hidden behind `ifdef SYNTHESIS: RTL simulation (Icarus, no SYNTHESIS
           macro) sees the correct code, Yosys (defines SYNTHESIS) builds the bug. The team's
           top-level tests must pass on the RTL and the PDK checks (synthesis or gate level) must fail.
timing-2ns Timing at an impossible 2 ns clock must fail; otherwise the timing check is blind.

When the RTL text changes so that a mutant no longer applies, it is reported "not applicable".
At least one gate-only mutant must apply; update MUTANTS together with such an RTL change.
"""
import shutil
import tempfile
from pathlib import Path

from pdk import DESIGN, ROOT, check_pdk, sources, synthesize, team_tests, timing

MUTANTS = {
    # name: (file, old text, new text) - the first occurrence; the same entries as the integration
    # repository's mutants.py for this chip.
    'illegal-not-sticky': ('src/v_ternary8_top.v', 'illegal_next = illegal_weight | illegal_code',
                           'illegal_next = illegal_code'),
    'sum-11-bit': ('src/adder12.v', 'output wire signed [11:0] SUM', 'output wire signed [10:0] SUM'),
}


def copy_sources(dest):
    files = []
    for rel in DESIGN['sources']:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
        files.append(target)
    return files


def gate_only(lib, work):
    report = {}
    for name, (rel, old, new) in MUTANTS.items():
        with tempfile.TemporaryDirectory(prefix='ssc-pdk-mutant-') as tmp:
            tmp = Path(tmp)
            files = copy_sources(tmp / 'team')
            path = tmp / 'team' / rel
            text = path.read_text(encoding='utf-8')
            if old not in text:
                report[f'gate-only:{name}'] = 'not applicable (text not found)'
                continue
            hidden = f'\n`ifdef SYNTHESIS\n{new}\n`else\n{old}\n`endif\n'
            path.write_text(text.replace(old, hidden, 1), encoding='utf-8')
            rtl = team_tests(files, tmp / 'rtl', 'pr')
            if rtl['status'] != 'pass':          # visible to RTL simulation: proves nothing here
                report[f'gate-only:{name}'] = 'not applicable (RTL tests already fail)'
                continue
            checks = check_pdk(files, DESIGN['top'], lib, work / name, 'pr')
            by = [c for c in ('synthesis', 'gate_level') if checks[c].get('status') == 'fail']
            report[f'gate-only:{name}'] = f"caught ({', '.join(by)})" if by else 'MISSED'
    return report


def timing_sanity(lib, work):
    synthesis, netlist = synthesize([str(f) for f in sources()], DESIGN['top'], lib, work / 'timing-2ns')
    if netlist is None or synthesis['status'] != 'pass':
        return {'timing-2ns': 'not applicable (synthesis did not pass)'}
    result = timing(netlist, DESIGN['top'], lib, work / 'timing-2ns', period=2)
    # Caught only by a negative setup slack: an OpenSTA error would also "fail" and prove nothing.
    setup = result.get('setup_slack_ns')
    if setup is None:
        return {'timing-2ns': 'MISSED (OpenSTA did not report a slack)'}
    return {'timing-2ns': f'caught (setup slack {setup} ns)' if setup < 0 else 'MISSED'}


def run(lib, work):
    report = {**gate_only(lib, work), **timing_sanity(lib, work)}
    caught_gate = any(k.startswith('gate-only:') and v.startswith('caught') for k, v in report.items())
    missed = any(v.startswith('MISSED') for v in report.values())
    ok = not missed and caught_gate and report['timing-2ns'].startswith('caught')
    detail = None if caught_gate else 'no gate-only mutant applied; update MUTANTS in scripts/pdk_selftest.py'
    return {'status': 'pass' if ok else 'fail', 'mutants': report, **({'detail': detail} if detail else {})}
