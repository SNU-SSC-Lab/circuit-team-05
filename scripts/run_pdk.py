"""MyChip PDK checks of this repository (SPEC 0015). Linux with yosys, iverilog, sta and the PDK.

    bash scripts/fetch_pdk.sh /path/pdk          # once; then SSC_PDK=/path/pdk
    python scripts/run_pdk.py check [--tier pr|full]
    python scripts/run_pdk.py selftest
    python scripts/run_pdk.py report             # Korean summary; exit 1 when anything failed

Results go to .policy-tmp/results/pdk/. Statuses: pass, fail, missing (nothing to check yet).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdk  # noqa: E402
from mychip_flow import check_files, check_signoff  # noqa: E402

ROOT = pdk.ROOT
OUT = ROOT / '.policy-tmp' / 'results' / 'pdk'


def write(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def head():
    run = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    return run.stdout.strip() or None


def check(args):
    start = time.perf_counter()
    top = pdk.DESIGN['top']
    work = OUT / 'work'
    result = {'top': top, 'commit': head(), 'tier': args.tier, 'pdk': pdk.PDK['name'],
              'clock_period_ns': pdk.CLOCK_NS, 'checks': {}}
    checks = result['checks']
    checks['files'] = check_files(ROOT)
    lib, why = pdk.locate(args.pdk)
    if lib is None:
        failed = {'status': 'fail', 'detail': why}
        checks.update(synthesis=failed, gate_level=dict(failed), timing=dict(failed),
                      netlist_synth=dict(failed), netlist_pnr=dict(failed))
    else:
        checks.update(pdk.check_pdk(pdk.sources(), top, lib, work, args.tier))
        stages = pdk.check_netlists(ROOT, top, lib, work, args.tier)
        checks['netlist_synth'], checks['netlist_pnr'] = stages['synth'], stages['pnr']
    checks['signoff'] = check_signoff(ROOT, top)
    result['wall_seconds'] = round(time.perf_counter() - start, 1)
    write('pdk.json', result)
    print(json.dumps({k: v.get('status') for k, v in checks.items()}, ensure_ascii=False))
    return int(any(c.get('status') == 'fail' for c in checks.values()))


def selftest(args):
    from pdk_selftest import run
    start = time.perf_counter()
    lib, why = pdk.locate(args.pdk)
    result = {'status': 'fail', 'detail': why} if lib is None else run(lib, OUT / 'selftest')
    result['wall_seconds'] = round(time.perf_counter() - start, 1)
    write('selftest.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result['status'] != 'pass')


MARK = {'pass': '✅ 통과', 'fail': '❌ 실패', 'missing': '⬜ 없음'}
MUTANT = (('caught', '검출'), ('MISSED', '**놓침**'), ('not applicable', '적용 안 됨'))


def mutant_text(value):
    for english, korean in MUTANT:
        value = value.replace(english, korean)
    return value


def mark(check):
    return MARK.get((check or {}).get('status'), '❌ 실행 안 됨')


def slack(value):
    return f'{value:.3f} ns' if isinstance(value, (int, float)) else '-'


def gate_text(gate):
    if not gate or gate.get('status') == 'missing':
        return (gate or {}).get('detail', '')
    tests = gate.get('tests', {})
    text = f"`run_rtl.py` {'·'.join(gate.get('groups', []))} 그룹 시험 {len(tests)}개"
    if 'jobs' in gate:
        text += f", 결과 확인 {gate['jobs']:,}작업"
    if 'seconds' in gate:
        text += f", {gate['seconds']}초"
    return text + (f". {gate['detail']}" if gate.get('detail') else '')


def timing_text(sta):
    if not sta or 'setup_slack_ns' not in sta:
        return (sta or {}).get('detail', '')
    text = (f"{sta['period_ns']} ns 클록에서 setup 여유 {slack(sta['setup_slack_ns'])} · "
            f"hold 여유 {slack(sta['hold_slack_ns'])}")
    if sta.get('critical_path'):
        text += f" · 가장 느린 경로 `{sta['critical_path']}`"
    if sta.get('parasitics'):
        text += ' · SPEF 배선 지연 반영'
    return text


def netlist_text(entry):
    if entry.get('status') == 'missing' or 'file' not in entry:
        return entry.get('detail', '')
    parts = [f"`{entry['file']}`"]
    if 'cells' in entry:
        parts.append(f"셀 {entry['cells']}개 · 면적 {entry['area_um2'] / 1e6:.3f} mm²")
    if 'gate_level' in entry:
        parts.append(f"게이트 수준 {MARK.get(entry['gate_level']['status'])}")
        parts.append(f"타이밍 {MARK.get(entry['timing']['status'])}: {timing_text(entry['timing'])}")
    return ' · '.join(parts)


def report(_args):
    lines = ['## MyChip PDK 검사 결과', '']
    path, selfpath = OUT / 'pdk.json', OUT / 'selftest.json'
    data = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'checks': {}}
    own = json.loads(selfpath.read_text(encoding='utf-8')) if selfpath.is_file() else None
    checks = data['checks']
    tier = data.get('tier', 'pr')
    lines += [f"검사한 커밋 `{data.get('commit')}` · 단계 `{tier}` · PDK `{data.get('pdk', pdk.PDK['name'])}` · "
              f"클록 {data.get('clock_period_ns', pdk.CLOCK_NS)} ns (10 MHz) · 검사 시간 {data.get('wall_seconds', '-')}초", '']
    lines += ['| 검사 | 결과 | 내용 |', '| --- | --- | --- |']
    synth = checks.get('synthesis', {})
    synth_text = synth.get('detail', '')
    if 'cells' in synth:
        synth_text = (f"표준셀 {synth['cells']}개 · 플립플롭 {synth['flops']}개 · "
                      f"면적 {synth['area_um2'] / 1e6:.3f} mm² ({synth['area_um2']:,} µm²)")
    files = checks.get('files', {})
    files_text = files.get('detail', '')
    if 'files' in files:
        files_text = f"저장소 파일 {files['files']}개, mychip/에 올라온 단계: {', '.join(files['mychip']) or '없음'}"
        if files.get('pdk_copies'):
            files_text += f" · PDK 사본 {len(files['pdk_copies'])}개 (공개 PDK라 실패 아님)"
    signoff = checks.get('signoff', {})
    found = [f"DRC 결과 {signoff['drc_results']}건"] if 'drc_results' in signoff else []
    found += [f"GDS SHA-256 `{signoff['gds_sha256'][:12]}…`"] if 'gds_sha256' in signoff else []
    signoff_text = ', '.join(found) or signoff.get('detail', '')
    rows = [
        ('합성 (Yosys → 4차 PDK 표준셀)', synth, synth_text),
        ('게이트 수준 (팀 top 시험)', checks.get('gate_level'), gate_text(checks.get('gate_level'))),
        ('타이밍 (OpenSTA)', checks.get('timing'), timing_text(checks.get('timing'))),
        ('mychip/1-synth netlist', checks.get('netlist_synth'), netlist_text(checks.get('netlist_synth', {}))),
        ('mychip/2-pnr netlist', checks.get('netlist_pnr'), netlist_text(checks.get('netlist_pnr', {}))),
        ('mychip/3-signoff (DRC·LVS·GDS 해시)', signoff, signoff_text),
        ('mychip/ 파일 종류', files, files_text),
    ]
    if own is not None:
        found = ', '.join(f"{name.replace('gate-only:', 'SYNTHESIS 뒤에 숨긴 버그 ').replace('timing-2ns', '2 ns 클록 타이밍')} "
                          f"{mutant_text(v)}" for name, v in own.get('mutants', {}).items())
        rows.append(('자체 검사 (심은 버그를 잡는지)', own, found or own.get('detail', '')))
    else:
        rows.append(('자체 검사 (심은 버그를 잡는지)', None, '실행 결과 없음'))
    for name, check, text in rows:
        lines.append(f"| {name} | {mark(check)} | {str(text).replace('|', '/')} |")
    problems = [(name, p) for name, check, _ in rows for p in (check or {}).get('problems', [])]
    problems += [(name, check['detail']) for name, check, _ in rows
                 if check and check.get('status') == 'fail' and check.get('detail') and not check.get('problems')]
    if problems:
        lines += ['', '### 실패 내용', '']
        lines += [f'- {name}: {p}' for name, p in problems[:30]]
    timing = pdk.PDK['timing']
    lines += ['', f"타이밍은 PDK에 있는 typical 라이브러리(5 V, 25 °C) 하나로 계산했습니다. setup은 모든 지연을 "
              f"×{timing['late_derate']}, hold는 ×{timing['early_derate']}로 바꿔 느린 칩·빠른 칩을 흉내 낸 값입니다. "
              "공정 코너별 사인오프(signoff corner) 분석이 아니며, 제작 가능 판정도 아닙니다. "
              f"입력 지연 {timing['input_delay_ns']} ns · 출력 지연 {timing['output_delay_ns']} ns · "
              f"출력 부하 {timing['output_load_pf']} pF는 `verification/pdk/pdk.toml`의 가정입니다.", '']
    lines += ['게이트 수준 시험은 셀마다 PDK Liberty의 function대로 동작하는 모델로 '
              f"`tests/rtl/test_top.py`를 돌립니다 (`{tier}` 단계: {', '.join(pdk.TIERS.get(tier, ()))} 그룹).", '']
    text = '\n'.join(lines)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'report.md').write_text(text, encoding='utf-8')
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(text)
    print(text)
    statuses = [(check or {}).get('status') for _, check, _ in rows]
    return int(any(s not in ('pass', 'missing') for s in statuses) or own is None or not path.is_file())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=['check', 'selftest', 'report'])
    parser.add_argument('--tier', choices=sorted(pdk.TIERS), default='pr')
    parser.add_argument('--pdk', default=pdk.env_pdk(), help='PDK directory (default: $SSC_PDK)')
    args = parser.parse_args()
    return {'check': check, 'selftest': selftest, 'report': report}[args.action](args)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
