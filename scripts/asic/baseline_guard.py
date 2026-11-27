"""Require a bypass for PRs that change verification baselines or the guard (SPEC 0019, check `baseline-guard`).

Compares head (`--head REF`, or the working tree at `--root`) with a base ref as DATA: files are read
as bytes (`git show` or the file system) and parsed as JSON; nothing from either tree is imported or
executed. CI cannot tell real Calibre output from a hand-written file, so every change under
`verification/reliability/` (new, edited or deleted file), every rule promoted to verified and every
backward rule move in `verification/asic/drc-rules.json` is a violation; 도재겸 checks the evidence and
bypass-merges the PR (SPEC 0019). Changes that do not touch evidence stay allowed (e.g. unported ->
ported). Messages also say what moved backward: new or widened unverified items, table regressions.

Threat model: the repository is public and the workflow runs on `pull_request_target` (base branch's
workflow file, write-capable event context) for any PR, including fork PRs. So the job must never run
PR code. The workflow runs this file and `reliability.py` from the workflow's own commit
(`git show "$GITHUB_SHA:scripts/asic/baseline_guard.py"` and `reliability.py` into a temp directory)
with `--base BASE_SHA --head HEAD_SHA`. Changes to the guard, its workflows and CODEOWNERS are
violations too, once base has the guard. Base without reliability files (first introduction) yields
no violations.

Fixture checks that need `drc_cases.py` evaluated (a verified rule losing or changing a golden fixture,
a fixture added without golden, only refused fixtures left) run in `reliability.py check` inside the
unprivileged `pull_request` job `reliability-table`. `--run-fixtures` (local use only, never on
untrusted code) also evaluates both refs' `drc_cases.py` here: in a separate `python -I` child process
with a temp working directory, an empty environment and a timeout, behind an AST check (no imports,
escape names, `_`-prefixed or frame attributes, or match statements). Known limit of that local mode:
the AST check is defence in depth, not a sandbox.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

import reliability

HERE = Path(__file__).resolve().parent  # the trusted reliability.py the child imports
ROOT = HERE.parents[1]

RULES = 'verification/asic/drc-rules.json'
CASES = 'scripts/asic/drc_cases.py'
BASELINE = 'verification/reliability'
GOLDEN = BASELINE+'/golden'
UNVERIFIED = BASELINE+'/unverified.json'
TABLE = BASELINE+'/table.json'
GUARD = ('scripts/asic/baseline_guard.py', 'scripts/asic/reliability.py',
         '.github/workflows/baseline.yml', '.github/workflows/asic.yml', '.github/CODEOWNERS')
RANK = {'unported': 0, 'ported': 1, 'verified': 2}
BYPASS = '기준 파일 변경은 도재겸이 근거를 확인한 뒤 PR에서 우회 머지합니다(SPEC 0019).'
# With --run-fixtures drc_cases.py runs inside the guard, so it may only define fixtures.
FORBIDDEN_NAMES = {'__import__', '__builtins__', '__name__', 'exec', 'eval', 'compile', 'open', 'getattr',
                   'globals', 'locals', 'vars', 'SystemExit', 'quit', 'exit', 'breakpoint', 'input'}
# Class patterns read attributes without an ast.Attribute node (`case type(__base__=o)`); fixtures need none.
MATCH_NODES = (ast.Match, ast.MatchValue, ast.MatchSingleton, ast.MatchSequence, ast.MatchMapping,
               ast.MatchClass, ast.MatchStar, ast.MatchAs, ast.MatchOr)
FRAME_ATTRS = {'gi_frame', 'cr_frame', 'ag_frame', 'gi_code', 'f_back', 'f_globals', 'f_locals', 'f_builtins',
               'tb_frame'}
CHILD_TIMEOUT = 60  # seconds; drc_cases.py takes well under one
# Runs in the child: argv = [guard dir, sentinel], stdin = drc_cases.py source.
CHILD = '''
import json, sys
sys.path.insert(0, sys.argv[1])
import reliability
sentinel = sys.argv[2]
source = sys.stdin.read()
namespace = {}
exec(compile(source, 'scripts/asic/drc_cases.py', 'exec'), namespace)
rows = [[reliability.fixture_name(i, c)+'.gds', c['rule'], reliability.case_sha256(c)]
        for i, c in enumerate(namespace['cases']())]
sys.stdout.write(json.dumps(rows)+'\\n'+sentinel+'\\n')
sys.stdout.flush()
'''


def empty():
    """Snapshot of a ref that has no reliability files yet (first introduction).

    `fixtures`/`fixture_rules` stay None unless drc_cases.py was evaluated (--run-fixtures)."""
    return {'rules': {}, 'unverified': None, 'unverified_checks': {}, 'golden': {}, 'fixtures': None,
            'fixture_rules': None, 'golden_fixtures': {}, 'table': None, 'baseline_files': {}, 'guard_files': {}}


def _check_cases_source(source):
    """Fail closed when drc_cases.py does more than define fixtures."""
    try:
        tree = ast.parse(source, CASES)
    except SyntaxError as error:
        raise ValueError(f'`{CASES}`을(를) 읽을 수 없습니다(문법 오류 {error.lineno}번째 줄).') from None
    for node in ast.walk(tree):
        if (isinstance(node, (ast.Import, ast.ImportFrom) + MATCH_NODES)
                or isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES
                or isinstance(node, ast.Attribute) and (node.attr.startswith('_') or node.attr in FRAME_ATTRS)):
            raise ValueError(f'`{CASES}` {node.lineno}번째 줄에 import·match 문이나 내부 기능 호출이 있습니다. '
                             '기준 확인은 이 파일을 그대로 실행하므로 fixture 정의만 둘 수 있습니다.')


def fixtures_from_source(source, rules):
    """{gds: case_sha256} and {gds: rule} for fixtures of verified rules, from drc_cases.py text."""
    _check_cases_source(source)
    fixtures, owners = {}, {}
    for gds, rule, digest in _run_cases(source):
        if rules.get(rule) == 'verified':
            fixtures[gds], owners[gds] = digest, rule
    return fixtures, owners


def _run_cases(source):
    """[[gds, rule, case_sha256], ...] from a `python -I` child; any other outcome is a ValueError."""
    sentinel = 'baseline-guard-done-'+secrets.token_hex(16)
    env = {key: os.environ[key] for key in ('SYSTEMROOT',) if key in os.environ}  # Windows needs SYSTEMROOT
    stopped = f'`{CASES}`을(를) 별도 프로세스에서 실행하다 멈췄습니다'
    tail = 'fixture 정의를 끝까지 읽지 못하면 기준 확인을 통과시키지 않습니다.'
    with tempfile.TemporaryDirectory() as tmp:
        try:
            done = subprocess.run([sys.executable, '-I', '-c', CHILD, str(HERE), sentinel], input=source,
                                  capture_output=True, text=True, encoding='utf-8', errors='replace',
                                  cwd=tmp, env=env, timeout=CHILD_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise ValueError(f'{stopped}({CHILD_TIMEOUT}초 시간 초과). {tail}') from None
    lines = done.stdout.splitlines()
    if done.returncode != 0 or len(lines) < 2 or lines[-1] != sentinel:
        why = (done.stderr.strip().splitlines() or ['출력 없음'])[-1][:300]
        raise ValueError(f'{stopped}(종료 코드 {done.returncode}, {why}). {tail}')
    try:
        rows = json.loads(lines[-2])
        if not all(isinstance(row, list) and len(row) == 3 and all(isinstance(v, str) for v in row)
                   for row in rows):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(f'{stopped}(결과 JSON이 온전하지 않음). {tail}') from None
    return rows


def _digest(data):
    # The same text checked out with CRLF must not read as a hand edit.
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def _build(read, baseline_paths, run_fixtures=False):
    """read(relpath) -> bytes or None; baseline_paths: repo-relative files under BASELINE.

    Only bytes and JSON are read. drc_cases.py is evaluated only when run_fixtures (local use)."""
    result = empty()
    for path in GUARD:
        data = read(path)
        if data is not None:
            result['guard_files'][path] = _digest(data)
    text = read(RULES)
    if text is not None:
        result['rules'] = {rule['id']: reliability.rule_state(rule) for rule in json.loads(text)['rules']}
    text = read(CASES) if run_fixtures else None
    if text is not None:
        result['fixtures'], result['fixture_rules'] = fixtures_from_source(text.decode('utf-8'), result['rules'])
    elif run_fixtures:
        result['fixtures'], result['fixture_rules'] = {}, {}
    for path in sorted(baseline_paths):
        data = read(path)
        result['baseline_files'][path] = _digest(data)
        if not path.startswith(GOLDEN+'/'):
            continue
        result['golden'][path] = result['baseline_files'][path]
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


def snapshot(root, run_fixtures=False):
    """Snapshot of the working tree at root (bytes and JSON only unless run_fixtures)."""
    root = Path(root)

    def read(relpath):
        path = root/relpath
        return path.read_bytes() if path.is_file() else None
    folder = root/BASELINE
    paths = [p.relative_to(root).as_posix() for p in folder.rglob('*') if p.is_file()] if folder.is_dir() else []
    return _build(read, [p for p in paths if '/__pycache__/' not in p], run_fixtures)


def snapshot_at(ref, root=ROOT, run_fixtures=False):
    """Snapshot of a git ref (`git show ref:path` blobs); missing files read as absent."""
    git = ['git', '-C', str(root)]
    found = subprocess.run(git+['rev-parse', '--verify', '--quiet', ref+'^{commit}'], capture_output=True, text=True)
    if found.returncode:
        raise ValueError(f'비교할 기준 `{ref}`을(를) git에서 찾을 수 없습니다. '
                         '먼저 가져와야 합니다(actions/checkout의 fetch-depth: 0).')
    commit = found.stdout.strip()

    def read(relpath):
        shown = subprocess.run(git+['show', f'{commit}:{relpath}'], capture_output=True)
        return shown.stdout if shown.returncode == 0 else None
    listed = subprocess.run(git+['ls-tree', '-r', '-z', '--name-only', commit, '--', BASELINE],
                            check=True, capture_output=True)
    return _build(read, [p.decode('utf-8') for p in listed.stdout.split(b'\0') if p], run_fixtures)


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


def _file_changes(base_files, head_files, kind):
    found = []
    for path in sorted(set(base_files) | set(head_files)):
        golden = path.startswith(GOLDEN+'/')
        if path not in head_files:
            why = ' golden은 지우지 않고 새 기준점 경로를 추가합니다.' if golden else ''
            found.append(f'{kind} `{path}`이(가) 삭제되었습니다.{why}')
        elif path not in base_files:
            found.append(f'{kind} `{path}`이(가) 추가되었습니다. CI는 상용 도구 출력인지 가릴 수 없습니다.')
        elif base_files[path] != head_files[path]:
            why = ' golden은 상용 도구 출력에서 한 번 만들고 고치지 않습니다.' if golden else ''
            found.append(f'{kind} `{path}`이(가) 수정되었습니다.{why}')
    return found


def violations(base, head):
    """Korean reasons why head needs 도재겸's bypass against base; [] when no baseline moved."""
    found = []
    base_files = dict(base['golden'], **base['baseline_files'])
    head_files = dict(head['golden'], **head['baseline_files'])
    introduced = bool(base_files)  # before the first golden, rules reach verified with the baseline itself
    for rule, before in sorted(base['rules'].items()):
        after = head['rules'].get(rule)
        if after is None:
            found.append(f'규칙 `{rule}`이(가) `{RULES}`에서 사라졌습니다(이전 상태 {before}).')
        elif RANK[after] < RANK[before]:
            found.append(f'규칙 `{rule}`의 상태가 {before}에서 {after}(으)로 내려갔습니다.')
        elif introduced and after == 'verified' and before != 'verified':
            found.append(f'규칙 `{rule}`이(가) {before}에서 verified로 올라갔습니다(golden_compared). '
                         'Calibre golden과 맞춰 본 근거를 도재겸이 확인해야 합니다.')
    count = sum(state == 'verified' for state in base['rules'].values())
    if count and not any(state == 'verified' for state in head['rules'].values()):
        found.append(f'verified 규칙이 하나도 남지 않았습니다(이전 {count}개). 게이트가 아무 규칙도 확인하지 않게 됩니다.')
    if base['fixtures'] is not None and head['fixtures'] is not None:  # only with --run-fixtures
        known = _evidence_problems(base)
        found += [text for key, text in _evidence_problems(head).items() if key not in known]
    if introduced:
        found += _file_changes(base_files, head_files, '기준 파일')
    if 'scripts/asic/baseline_guard.py' in base['guard_files']:
        kept = {path: digest for path, digest in head['guard_files'].items() if path in base['guard_files']}
        found += [text+' 게이트가 스스로 약해질 수 있습니다.'
                  for text in _file_changes(base['guard_files'], kept, '검사 코드')]
    if base['unverified'] is not None:
        after = head['unverified'] or set()
        for item in sorted(after-base['unverified']):
            found.append(f'미검증 목록 `{UNVERIFIED}`에 새 항목 `{item}`이(가) 생겼습니다. '
                         '이미 검증된 것을 미검증으로 돌리면 안 됩니다.')
        for item in sorted(base['unverified']-after):
            found.append(f'미검증 항목 `{item}`이(가) 빠졌습니다. 닫는 근거를 도재겸이 확인해야 합니다.')
        for item in sorted(base['unverified'] & after):
            wider = sorted(set(head['unverified_checks'].get(item, ()))-set(base['unverified_checks'].get(item, ())))
            if wider:
                found.append(f'미검증 항목 `{item}`이(가) 허용하는 체크가 늘었습니다: '
                             +', '.join(f'`{c}`' for c in wider)+'.')
    if base['table'] is not None:
        after = head['table'] or {}
        for row, before in sorted(base['table'].items()):
            if row not in after:
                found.append(f'대응표 `{TABLE}`에서 행 `{row}`이(가) 사라졌습니다.')
            elif before == 'match' and after[row] != 'match':
                found.append(f'대응표 행 `{row}`의 판정이 match에서 {after[row]}(으)로 내려갔습니다.')
        for row, verdict in sorted(after.items()):
            if verdict == 'match' and base['table'].get(row) != 'match':
                found.append(f'대응표 행 `{row}`이(가) match가 되었습니다. 일치 근거를 도재겸이 확인해야 합니다.')
    return found


def report(base_ref, found):
    if not found:
        return (f'# 기준 파일 확인\n\n`{base_ref}`와(과) 비교해 기준 파일·검사 코드에 '
                '우회 머지가 필요한 변경이 없습니다.\n')
    lines = ['# 기준 파일 확인: 실패', '', f'`{base_ref}`와(과) 비교해 아래 변경은 우회 머지가 필요합니다.', '']
    lines += [f'- {text}' for text in found]
    return '\n'.join(lines+['', BYPASS])+'\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, help='git ref to compare with, e.g. origin/main')
    parser.add_argument('--root', type=Path, default=ROOT, help='git repository / checkout (default: this repository)')
    parser.add_argument('--head', help='git ref of the PR head, read with git show (default: the working tree at --root)')
    parser.add_argument('--run-fixtures', action='store_true',
                        help='local only: also evaluate both drc_cases.py files; never use on untrusted code')
    args = parser.parse_args(argv)
    try:
        head = (snapshot_at(args.head, args.root, args.run_fixtures) if args.head
                else snapshot(args.root, args.run_fixtures))
        found = violations(snapshot_at(args.base, args.root, args.run_fixtures), head)
    except BaseException as error:  # fail closed: a guard that cannot read the baseline must not pass
        found = None
        why = str(error) if isinstance(error, ValueError) else (
            f'기준 확인 중 예상하지 못한 오류가 났습니다({type(error).__name__}: {error}). '
            '확인하지 못한 변경은 통과시키지 않습니다.')
        text = f'# 기준 파일 확인: 실행 실패\n\n{why}\n'
    else:
        text = report(args.base, found)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
    if hasattr(sys.stdout, 'reconfigure'):  # a non-UTF-8 console must not fail the check
        sys.stdout.reconfigure(errors='replace')
    print(text, end='')
    return 1 if found is None or found else 0


if __name__ == '__main__':
    sys.exit(main())
