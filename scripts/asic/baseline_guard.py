"""Block PRs that move verification baselines backward (SPEC 0019, check `baseline-guard`).

Compares the working tree (head) with a base ref. Allowed: rule states moving forward, new golden
files, closing an unverified item or claiming a table match when the same diff adds a golden file.
Everything else that weakens the evidence is a violation; 도재겸 checks it and bypass-merges.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import reliability

ROOT = Path(__file__).resolve().parents[2]

RULES = 'verification/asic/drc-rules.json'
CASES = 'scripts/asic/drc_cases.py'
GOLDEN = 'verification/reliability/golden'
UNVERIFIED = 'verification/reliability/unverified.json'
TABLE = 'verification/reliability/table.json'
RANK = {'unported': 0, 'ported': 1, 'verified': 2}
BYPASS = '기준 파일 변경은 도재겸이 근거를 확인한 뒤 PR에서 우회 머지합니다(SPEC 0019).'


def empty():
    """Snapshot of a ref that has no reliability files yet (first introduction)."""
    return {'rules': {}, 'unverified': None, 'unverified_checks': {}, 'golden': {}, 'fixtures': {},
            'fixture_rules': {}, 'golden_fixtures': {}, 'table': None}


def fixtures_from_source(source, rules):
    """{gds: case_sha256} and {gds: rule} for fixtures of verified rules, from drc_cases.py text."""
    namespace = {'__name__': 'drc_cases_snapshot'}  # drc_cases.py has no imports; keep it out of sys.modules
    exec(compile(source, CASES, 'exec'), namespace)
    fixtures, owners = {}, {}
    for index, case in enumerate(namespace['cases']()):
        if rules.get(case['rule']) != 'verified':
            continue
        gds = reliability.fixture_name(index, case)+'.gds'
        fixtures[gds] = reliability.case_sha256(case)
        owners[gds] = case['rule']
    return fixtures, owners


def _digest(data):
    # The same text checked out with CRLF must not read as a hand edit.
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def _build(read, golden_paths):
    """read(relpath) -> bytes or None; golden_paths: repo-relative files under GOLDEN."""
    result = empty()
    text = read(RULES)
    if text is not None:
        result['rules'] = {rule['id']: reliability.rule_state(rule) for rule in json.loads(text)['rules']}
    text = read(CASES)
    if text is not None:
        result['fixtures'], result['fixture_rules'] = fixtures_from_source(text.decode('utf-8'), result['rules'])
    for path in sorted(golden_paths):
        data = read(path)
        result['golden'][path] = _digest(data)
        if path.endswith('/golden.json'):
            try:
                entries = json.loads(data)['fixtures']
            except (ValueError, KeyError, TypeError):
                continue  # a broken golden backs nothing; editing an old one is reported anyway
            for entry in entries:
                result['golden_fixtures'][entry['case_sha256']] = {
                    'gds': entry['gds'], 'rule': entry['rule'], 'calibre': entry['calibre']}
    text = read(UNVERIFIED)
    if text is not None:
        items = json.loads(text)['items']
        result['unverified'] = {item['id'] for item in items}
        result['unverified_checks'] = {item['id']: tuple(item.get('allows_checks', ())) for item in items}
    text = read(TABLE)
    if text is not None:
        result['table'] = {row['id']: row['verdict'] for row in json.loads(text)['rows']}
    return result


def snapshot(root):
    """Snapshot of the working tree at root."""
    root = Path(root)

    def read(relpath):
        path = root/relpath
        return path.read_bytes() if path.is_file() else None
    golden = root/GOLDEN
    paths = [p.relative_to(root).as_posix() for p in golden.rglob('*') if p.is_file()] if golden.is_dir() else []
    return _build(read, [p for p in paths if '/__pycache__/' not in p])


def snapshot_at(ref, root=ROOT):
    """Snapshot of a git ref (`git show ref:path`); missing files read as absent."""
    git = ['git', '-C', str(root)]
    found = subprocess.run(git+['rev-parse', '--verify', '--quiet', ref+'^{commit}'], capture_output=True, text=True)
    if found.returncode:
        raise ValueError(f'git ref {ref!r} not found; fetch it first (actions/checkout fetch-depth: 0)')
    commit = found.stdout.strip()

    def read(relpath):
        shown = subprocess.run(git+['show', f'{commit}:{relpath}'], capture_output=True)
        return shown.stdout if shown.returncode == 0 else None
    listed = subprocess.run(git+['ls-tree', '-r', '-z', '--name-only', commit, '--', GOLDEN],
                            check=True, capture_output=True)
    return _build(read, [p.decode('utf-8') for p in listed.stdout.split(b'\0') if p])


def _evidence_problems(snap):
    """Problems of verified rules against golden, keyed so the same problem in base is not reported again."""
    problems = {}
    verified = sorted(rule for rule, state in snap['rules'].items() if state == 'verified')
    by_rule = {}
    for gds, digest in snap['fixtures'].items():
        by_rule.setdefault(snap['fixture_rules'][gds], {})[gds] = digest
    for rule in verified:
        mine = by_rule.get(rule, {})
        golden = {digest: entry for digest, entry in snap['golden_fixtures'].items() if entry['rule'] == rule}
        for gds, digest in sorted(mine.items()):
            if digest not in golden:
                problems[('unbacked', rule, gds, digest)] = (
                    f'검증된 규칙 `{rule}`의 fixture `{gds}`에 Calibre golden이 없습니다. '
                    'verified 규칙의 fixture를 추가하거나 고치려면 기준점에서 Calibre golden을 새로 받아야 합니다.')
        present = set(mine.values())
        for digest, entry in sorted(golden.items(), key=lambda item: item[1]['gds']):
            if digest not in present:
                problems[('lost', rule, digest)] = (
                    f'검증된 규칙 `{rule}`의 golden fixture `{entry["gds"]}`(Calibre {entry["calibre"]})이(가) '
                    '`scripts/asic/drc_cases.py`에서 사라졌거나 정의가 바뀌었습니다. 근거가 줄어듭니다.')
        if not any(golden[d]['calibre'] != 'refused' for d in present if d in golden):
            problems[('no_evidence', rule)] = (
                f'검증된 규칙 `{rule}`에 Calibre가 판정한 fixture가 없습니다'
                '(golden이 없거나 Calibre가 거부한 fixture만 남음). 판정 근거가 없으면 verified일 수 없습니다.')
    return problems


def violations(base, head):
    """Korean reasons why head moves a baseline backward from base; [] when it only moves forward."""
    found = []
    for rule, before in sorted(base['rules'].items()):
        after = head['rules'].get(rule)
        if after is None:
            found.append(f'규칙 `{rule}`이(가) `{RULES}`에서 사라졌습니다(이전 상태 {before}).')
        elif RANK[after] < RANK[before]:
            found.append(f'규칙 `{rule}`의 상태가 {before}에서 {after}(으)로 내려갔습니다.')
    count = sum(state == 'verified' for state in base['rules'].values())
    if count and not any(state == 'verified' for state in head['rules'].values()):
        found.append(f'verified 규칙이 하나도 남지 않았습니다(이전 {count}개). 게이트가 아무 규칙도 확인하지 않게 됩니다.')
    known = _evidence_problems(base)
    found += [text for key, text in _evidence_problems(head).items() if key not in known]
    for path, digest in sorted(base['golden'].items()):
        if path not in head['golden']:
            found.append(f'golden 파일 `{path}`이(가) 삭제되었습니다. golden은 지우지 않고 새 기준점 경로를 추가합니다.')
        elif head['golden'][path] != digest:
            found.append(f'golden 파일 `{path}`이(가) 수정되었습니다. golden은 상용 도구 출력에서 한 번 만들고 고치지 않습니다.')
    added = sorted(set(head['golden'])-set(base['golden']))
    if base['unverified'] is not None:
        after = head['unverified'] or set()
        for item in sorted(after-base['unverified']):
            found.append(f'미검증 목록 `{UNVERIFIED}`에 새 항목 `{item}`이(가) 생겼습니다. 이미 검증된 것을 미검증으로 돌리면 안 됩니다.')
        if not added:
            for item in sorted(base['unverified']-after):
                found.append(f'미검증 항목 `{item}`이(가) 빠졌는데 같은 변경에 새 golden 파일이 없습니다.')
        for item in sorted(base['unverified'] & after):
            wider = sorted(set(head['unverified_checks'].get(item, ()))-set(base['unverified_checks'].get(item, ())))
            if wider:
                found.append(f'미검증 항목 `{item}`이(가) 허용하는 체크가 늘었습니다: '+', '.join(f'`{c}`' for c in wider)+'.')
    if base['table'] is not None:
        after = head['table'] or {}
        for row, before in sorted(base['table'].items()):
            if row not in after:
                found.append(f'대응표 `{TABLE}`에서 행 `{row}`이(가) 사라졌습니다.')
            elif before == 'match' and after[row] != 'match':
                found.append(f'대응표 행 `{row}`의 판정이 match에서 {after[row]}(으)로 내려갔습니다.')
        if not added:
            for row, verdict in sorted(after.items()):
                if verdict == 'match' and base['table'].get(row) != 'match':
                    found.append(f'대응표 행 `{row}`을(를) match로 바꿨는데 같은 변경에 새 golden 파일이 없습니다.')
    return found


def report(base_ref, found):
    if not found:
        return f'# 기준 파일 확인\n\n`{base_ref}`와(과) 비교해 검증 기준이 뒤로 물러난 곳이 없습니다.\n'
    lines = ['# 기준 파일 확인: 실패', '', f'`{base_ref}`와(과) 비교해 검증 기준이 뒤로 물러났습니다.', '']
    lines += [f'- {text}' for text in found]
    return '\n'.join(lines+['', BYPASS])+'\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='git ref to compare with, e.g. origin/main')
    args = parser.parse_args(argv)
    found = violations(snapshot_at(args.base), snapshot(ROOT))
    text = report(args.base, found)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
    if hasattr(sys.stdout, 'reconfigure'):  # a non-UTF-8 console must not fail the check
        sys.stdout.reconfigure(errors='replace')
    print(text, end='')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
