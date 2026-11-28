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
PR code. The workflow checks the head out into `$GITHUB_WORKSPACE/head` (never the working directory),
copies this file and `reliability.py` from the workflow's own commit (`git -C head show
"$GITHUB_SHA:scripts/asic/baseline_guard.py"`) into a temp directory and runs
`python -I -E -s baseline_guard.py --base BASE_SHA --head HEAD_SHA --root "$GITHUB_WORKSPACE/head"` there. Changes to the guard, its workflows and CODEOWNERS are
violations too, once base has the guard. Base without reliability files (first introduction) yields
no violations.

Fixture checks that need `drc_cases.py` evaluated (a verified rule losing or changing a golden fixture,
a fixture added without golden, only refused fixtures left) run in `reliability.py check` inside the
unprivileged `pull_request` job `reliability-table`. That job runs PR code by design: drc_fixture_test.py
imports `drc_cases.py`, check-pending imports `drc_cases_pending*.py`, and the DRC harness itself
(drc_fixture_test.py, drc_geometry.py, drc_ports.py, drc.py) comes from the PR. Accepted residual risk: a
PR that edits that harness can fake its own results there; CODEOWNERS asks 도재겸 to review those files.
As defence in depth the guard scans the fixture sources as data (`ast.parse(bytes)` only, never compile
or exec; see `source_problems`) and reports a new or changed source that does more than define fixtures,
and new entries directly under scripts/asic that change what `import` finds there (folders/packages,
symlinks, __pycache__, compiled modules, stdlib or pya names), read with `git ls-tree`. Duplicate rule ids
in drc-rules.json are a violation (the rule state would be ambiguous).

Output: names in messages come from the PR, so `_c()` escapes newlines and control characters and
replaces backticks; the workflow also prints the report between `::stop-commands::` markers.

`--run-fixtures` (local use only, never on untrusted code) also evaluates both refs' `drc_cases.py`
here: in a separate `python -I` child process with a temp working directory, an empty environment and
a timeout, after the same strict scan. The scan is defence in depth, not a sandbox.
"""
import argparse
import ast
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import tokenize

# The workflow runs `python -I` (no script folder on sys.path), so import the trusted copy next to this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reliability  # noqa: E402

HERE = Path(__file__).resolve().parent  # the trusted reliability.py the child imports
ROOT = HERE.parents[1]

RULES = 'verification/asic/drc-rules.json'
CASES = 'scripts/asic/drc_cases.py'
BASELINE = 'verification/reliability'
GOLDEN = BASELINE+'/golden'
UNVERIFIED = BASELINE+'/unverified.json'
TABLE = BASELINE+'/table.json'
# The guard, its library, and the workflows that make the required checks (ci.yml: pr-policy,
# policy-unit, rtl; pdk.yml: pdk (pr); asic.yml: asic-gate, reliability-table; baseline.yml).
GUARD = ('scripts/asic/baseline_guard.py', 'scripts/asic/reliability.py',
         '.github/workflows/baseline.yml', '.github/workflows/asic.yml', '.github/workflows/ci.yml',
         '.github/workflows/pdk.yml', '.github/CODEOWNERS')
RANK = {'unported': 0, 'ported': 1, 'verified': 2}
BYPASS = '기준 파일 변경은 도재겸이 근거를 확인한 뒤 PR에서 우회 머지합니다(SPEC 0019).'
# With --run-fixtures drc_cases.py runs inside the guard, so it may only define fixtures.
FORBIDDEN_NAMES = {'__import__', '__builtins__', '__name__', 'exec', 'eval', 'compile', 'open', 'getattr',
                   'setattr', 'delattr', 'globals', 'locals', 'vars', 'SystemExit', 'quit', 'exit', 'breakpoint',
                   'input'}
# Fixture sources the guard scans as data (ast.parse only; never compiled or run). drc_fixture_test.py
# imports drc_cases.py and check-pending imports drc_cases_pending*.py in the same process as
# reliability.py, so a PR could rebind reliability.case_sha256 there and blind the fixture checks.
PENDING = 'scripts/asic/drc_cases_pending'
MAX_SOURCE_BYTES = 512*1024
MAX_SOURCE_PROBLEMS = 10
SCRIPTS = 'scripts/asic'
# drc_cases_pending*.py may import only these modules plus the pending files of the same tree, and may
# reach them only through these attributes (what the 2026-11-28 files use).
PENDING_MODULES = {'math': {'floor', 'sqrt'}, 'collections': {'Counter'}, 'json': {'loads', 'dumps'},
                   'reliability': {'case_sha256', 'fixture_name'}}
PENDING_NAME = re.compile(r'drc_cases_pending(_[a-z0-9]+)?')  # only when the tree is unknown (unit use)
# Attributes that would lead from a pending module object to another module.
MODULE_ATTRS = {'reliability', 'math', 'collections', 'sys', 'os', 'subprocess', 'builtins', 'modules', 'importlib',
                'json', 'hashlib', 'Path', 'pathlib', 'csv', 're', 'time', 'argparse', 'loader', 'spec'}
REGULAR = {'100644', '100755'}
# Names a fixture source may use without binding them itself: exactly the builtins the 2026-11-28
# drc_cases.py and drc_cases_pending*.py use. Every other builtin (help, getattr, type, object, iter, ...)
# and every name the file does not bind is a violation; binding a builtin name does not make it allowed
# (the scan does not follow scopes). FORBIDDEN_NAMES above stays as the documented worst cases.
ALLOWED_BUILTINS = frozenset({'ValueError', 'all', 'any', 'dict', 'enumerate', 'int', 'isinstance', 'len', 'list',
                              'map', 'max', 'min', 'print', 'range', 'round', 'set', 'sorted', 'str', 'tuple',
                              # pure value builtins, for future fixture code
                              'abs', 'zip', 'sum', 'float', 'bool', 'reversed', 'divmod', 'pow'})
# Added to builtins by the `site` module, so missing from dir(builtins) under `python -S`: always reported.
SITE_NAMES = frozenset({'help', 'exit', 'quit', 'license', 'credits', 'copyright'})
BUILTIN_NAMES = frozenset(dir(builtins))
# The only attributes a pending file may read from another pending module.
PENDING_MODULE_ATTRS = {'cases', 'records', 'cases_with_meta'}
# New files under scripts/asic with these names change what `import` finds for reliability.py and the
# DRC harness (stdlib modules, KLayout's pya).
SHADOWED = set(sys.stdlib_module_names) | {'pya', 'klayout'}
BINARY_SUFFIXES = ('.pyc', '.pyo', '.so', '.pyd')
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
        for i, c in enumerate(json.loads(json.dumps(namespace['cases']())))]
sys.stdout.write(json.dumps(rows)+'\\n'+sentinel+'\\n')
sys.stdout.flush()
'''


def empty():
    """Snapshot of a ref that has no reliability files yet (first introduction).

    `fixtures`/`fixture_rules` stay None unless drc_cases.py was evaluated (--run-fixtures)."""
    return {'rules': {}, 'unverified': None, 'unverified_checks': {}, 'golden': {}, 'fixtures': None,
            'fixture_rules': None, 'golden_fixtures': {}, 'table': None, 'baseline_files': {}, 'guard_files': {},
            'sources': {}, 'duplicate_rules': [], 'entries': {}}


def _node_problem(node, strict, parents, aliases, pending_modules, bound, own):
    """Why one AST node is not allowed in a fixture source, or None. strict: drc_cases.py rules.

    aliases: imported module names; bound: every name the file binds; own: the file's module name."""
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        if strict:
            return 'import 문'
        if isinstance(node, ast.ImportFrom):
            return 'from … import 문'
        if any(alias.name == own for alias in node.names):
            return f'자기 자신 import {own}'
        renamed = [f'{alias.name} as {alias.asname}' for alias in node.names if alias.asname]
        if renamed:
            return f'import … as 별칭 {", ".join(renamed)}'
        bad = [alias.name for alias in node.names
               if alias.name not in PENDING_MODULES and not (
                   PENDING_NAME.fullmatch(alias.name) if pending_modules is None else alias.name in pending_modules)]
        return f'허용하지 않는 import {", ".join(bad)}' if bad else None
    if isinstance(node, MATCH_NODES):
        return 'match 문'
    if strict and isinstance(node, (ast.ClassDef, ast.Lambda, ast.Global, ast.Nonlocal)):
        return {'ClassDef': 'class 정의', 'Lambda': 'lambda', 'Global': 'global 문', 'Nonlocal': 'nonlocal 문'}[
            type(node).__name__]
    if strict and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('_'):
        return f'밑줄로 시작하는 함수 이름 {node.name}'
    if isinstance(node, ast.Name):
        if strict and node.id.startswith('_') or not strict and node.id.startswith('__') and node.id != '__name__':
            return f'밑줄로 시작하는 이름 {node.id}'
        if node.id == '__name__' and not strict:
            return None
        if (node.id in BUILTIN_NAMES or node.id in SITE_NAMES) and node.id not in ALLOWED_BUILTINS:
            return f'허용 목록 밖의 이름 {node.id}'
        if node.id not in bound and node.id not in ALLOWED_BUILTINS:
            return f'파일 안에서 정의하지 않은 이름 {node.id}'
        module = aliases.get(node.id)
        if module is not None and module not in PENDING_MODULES:  # another pending file
            parent = parents.get(node)
            if not (isinstance(parent, ast.Attribute) and parent.value is node and isinstance(parent.ctx, ast.Load)
                    and parent.attr in PENDING_MODULE_ATTRS):
                attr = f'.{parent.attr}' if isinstance(parent, ast.Attribute) and parent.value is node else ''
                return (f'모듈 {module}{attr}은(는) 허용한 속성({", ".join(sorted(PENDING_MODULE_ATTRS))})으로만 '
                        '씁니다')
        if module in PENDING_MODULES:
            parent = parents.get(node)
            if not (isinstance(parent, ast.Attribute) and parent.value is node and isinstance(parent.ctx, ast.Load)
                    and parent.attr in PENDING_MODULES[module]):
                attr = f'.{parent.attr}' if isinstance(parent, ast.Attribute) and parent.value is node else ''
                return f'모듈 {module}{attr}은(는) 허용한 속성({", ".join(sorted(PENDING_MODULES[module]))})으로만 씁니다'
    if isinstance(node, ast.Attribute):
        if node.attr.startswith('_') or node.attr in FRAME_ATTRS or node.attr in FORBIDDEN_NAMES:
            return f'내부 속성 .{node.attr}'
        if not isinstance(node.ctx, ast.Load):
            return f'속성 대입·삭제 .{node.attr}'
        if not strict and (node.attr in MODULE_ATTRS or node.attr.startswith('drc_cases')):
            return f'모듈로 이어지는 속성 .{node.attr}'
    return None


def source_problems(relpath, data, pending_modules=None):
    """Korean problems of a fixture source given as bytes. Parsed with ast only: never compiled or run.

    The bytes are parsed as Python reads them (a coding cookie other than UTF-8 is rejected: UTF-7 or
    unicode_escape can hide code from a reader of the text). Names are allow-listed in both modes: a
    name must be bound in the file or be one of ALLOWED_BUILTINS; any other builtin (help, getattr, type,
    ...) is reported even when the file binds it. drc_cases.py (strict): also no import, match, class,
    lambda, global/nonlocal, names or function names starting with `_`, `_`/frame/forbidden attributes
    or attribute assignment. drc_cases_pending*.py: imports only of PENDING_MODULES and the pending files
    of the same tree (`pending_modules`), without `as` and never itself; PENDING_MODULES only through the
    listed attributes, other pending modules only through PENDING_MODULE_ATTRS, no attribute leading to
    a module; `_name` locals and reading `__name__` allowed.
    Anything that cannot be read fails closed."""
    if len(data) > MAX_SOURCE_BYTES:
        return [f'파일이 너무 큽니다({len(data)}바이트, 한도 {MAX_SOURCE_BYTES}).']
    try:
        data.decode('utf-8')
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    except (UnicodeDecodeError, SyntaxError, LookupError):
        return ['UTF-8로 읽을 수 없습니다.']
    if encoding not in ('utf-8', 'utf-8-sig'):
        return [f'파일이 {encoding} 인코딩을 선언합니다. UTF-8만 받습니다.']
    try:
        tree = ast.parse(data, relpath)
    except SyntaxError as error:
        return [f'문법을 읽을 수 없습니다({error.lineno}번째 줄: {error.msg}).']
    except (ValueError, RecursionError, MemoryError) as error:
        return [f'문법을 읽을 수 없습니다({type(error).__name__}).']
    strict = relpath == CASES
    problems = []
    try:
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        aliases = {alias.asname or alias.name: alias.name for node in ast.walk(tree)
                   if isinstance(node, ast.Import) for alias in node.names}
        bound = set(aliases)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
                bound.add(node.id)
            elif isinstance(node, ast.arg):
                bound.add(node.arg)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                bound.add(node.name)
        own = relpath.rsplit('/', 1)[-1].removesuffix('.py')
        for node in ast.walk(tree):
            # A bound builtin name (`def f(help)`) is still reported: the scan does not follow scopes.
            if isinstance(node, ast.arg) and node.arg in (BUILTIN_NAMES | SITE_NAMES) - ALLOWED_BUILTINS:
                problems.append(f'{node.lineno}번째 줄: 허용 목록 밖의 이름 {node.arg}')
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                    and node.name in (BUILTIN_NAMES | SITE_NAMES) - ALLOWED_BUILTINS:
                problems.append(f'{node.lineno}번째 줄: 허용 목록 밖의 이름 {node.name}')
            why = _node_problem(node, strict, parents, aliases, pending_modules, bound, own)
            if why:
                problems.append(f'{getattr(node, "lineno", 0)}번째 줄: {why}')
    except RecursionError:
        return ['구조가 너무 깊어 끝까지 읽을 수 없습니다.']
    problems = sorted(set(problems), key=lambda text: (int(text.split('번째')[0]), text))
    if len(problems) > MAX_SOURCE_PROBLEMS:
        problems = problems[:MAX_SOURCE_PROBLEMS]+[f'외 {len(problems)-MAX_SOURCE_PROBLEMS}건']
    return problems


def _check_cases_source(source):
    """Fail closed when drc_cases.py does more than define fixtures (before --run-fixtures runs it)."""
    problems = source_problems(CASES, source.encode('utf-8'))
    if problems:
        raise ValueError(f'`{CASES}`에 fixture 정의 밖의 코드가 있습니다({problems[0]}). '
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
            done = subprocess.run([sys.executable, '-X', 'utf8', '-I', '-c', CHILD, str(HERE), sentinel], input=source,
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


def _build(read, baseline_paths, run_fixtures=False, entries=None):
    """read(relpath) -> bytes or None; baseline_paths: repo-relative files under BASELINE;
    entries: {name: git mode} of the direct children of scripts/asic (None: only drc_cases.py, as a file).

    Only bytes and JSON are read. drc_cases.py is evaluated only when run_fixtures (local use)."""
    result = empty()
    for path in GUARD:
        data = read(path)
        if data is not None:
            result['guard_files'][path] = _digest(data)
    text = read(RULES)
    if text is not None:
        ids = []
        catalog = json.loads(text)
        for rule in catalog['rules']+catalog.get('antenna_rules', []):  # DRC deck and ANT deck checks
            ids.append(rule['id'])
            result['rules'][rule['id']] = reliability.rule_state(rule)
        result['duplicate_rules'] = sorted({rule for rule in ids if ids.count(rule) > 1})
    if entries is None:
        entries = {CASES.rsplit('/', 1)[1]: '100644'}
    else:
        result['entries'] = dict(entries)
    names = [name for name in entries if name == 'drc_cases.py'
             or name.startswith('drc_cases_pending') and name.endswith('.py')]
    pending = {name[:-3] for name in names if name != 'drc_cases.py' and entries[name] in REGULAR}
    for name in sorted(names):
        path = f'{SCRIPTS}/{name}'
        if entries[name] not in REGULAR:  # a symlink blob holds a path, a tree is a package: both hide code
            result['sources'][path] = (f'mode:{entries[name]}', [f'일반 파일이 아닙니다(git 모드 {entries[name]}).'])
            continue
        data = read(path)
        if data is not None:
            result['sources'][path] = (_digest(data), source_problems(path, data, pending))
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
    entries = {}
    if (root/SCRIPTS).is_dir():  # local use; untracked __pycache__ folders are skipped
        for child in (root/SCRIPTS).iterdir():
            if child.name != '__pycache__':
                entries[child.name] = '120000' if child.is_symlink() else '040000' if child.is_dir() else '100644'
    return _build(read, [p for p in paths if '/__pycache__/' not in p], run_fixtures, entries)


def _show(git, commit, relpath, present):
    """Bytes of relpath at commit; None only when the tree has no such file. A git error fails closed."""
    if not present:
        return None
    shown = subprocess.run(git+['show', f'{commit}:{relpath}'], capture_output=True)
    if shown.returncode:
        why = shown.stderr.decode('utf-8', 'replace').strip().splitlines()[-1:] or ['출력 없음']
        raise ValueError(f'git이 `{commit}:{relpath}`을(를) 읽지 못했습니다({why[0][:200]}). '
                         '읽지 못한 기준으로는 통과시키지 않습니다.')
    return shown.stdout


def snapshot_at(ref, root=ROOT, run_fixtures=False):
    """Snapshot of a git ref (`git show ref:path` blobs); missing files read as absent."""
    git = ['git', '-C', str(root)]
    found = subprocess.run(git+['rev-parse', '--verify', '--quiet', ref+'^{commit}'], capture_output=True, text=True)
    if found.returncode:
        raise ValueError(f'비교할 기준 `{ref}`을(를) git에서 찾을 수 없습니다. '
                         '먼저 가져와야 합니다(actions/checkout의 fetch-depth: 0).')
    commit = found.stdout.strip()

    tree = subprocess.run(git+['ls-tree', '-r', '-z', '--name-only', commit], check=True, capture_output=True)
    present = {p.decode('utf-8', 'replace') for p in tree.stdout.split(b'\0') if p}

    def read(relpath):
        return _show(git, commit, relpath, relpath in present)
    listed = subprocess.run(git+['ls-tree', '-r', '-z', '--name-only', commit, '--', BASELINE],
                            check=True, capture_output=True)
    scripts = subprocess.run(git+['ls-tree', '-z', commit, '--', SCRIPTS+'/'], check=True, capture_output=True)
    entries = {}
    for line in scripts.stdout.split(b'\0'):
        if line:
            meta, path = line.split(b'\t', 1)
            entries[path.decode('utf-8', 'replace').rsplit('/', 1)[-1]] = meta.split(b' ')[0].decode('ascii')
    return _build(read, [p.decode('utf-8') for p in listed.stdout.split(b'\0') if p], run_fixtures, entries)


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
                    f'검증된 규칙 `{_c(rule)}`의 fixture `{_c(gds)}`에 Calibre golden이 없습니다. '
                    'verified 규칙의 fixture를 추가하거나 고치려면 기준점에서 Calibre golden을 새로 받아야 합니다.')
        present = set(mine.values())
        for digest, entry in sorted(golden.items(), key=lambda item: item[1]['gds']):
            if digest not in present:
                problems[('lost', rule, digest)] = (
                    f'검증된 규칙 `{_c(rule)}`의 golden fixture `{_c(entry["gds"])}`(Calibre {_c(entry["calibre"])})이(가) '
                    '`scripts/asic/drc_cases.py`에서 사라졌거나 정의가 바뀌었습니다. 근거가 줄어듭니다.')
        if not any(golden[d]['calibre'] != 'refused' for d in present if d in golden):
            problems[('no_evidence', rule)] = (
                f'검증된 규칙 `{_c(rule)}`에 Calibre가 판정한 fixture가 없습니다'
                '(golden이 없거나 Calibre가 거부한 fixture만 남음). 판정 근거가 없으면 verified일 수 없습니다.')
    return problems


def _file_changes(base_files, head_files, kind):
    found = []
    for path in sorted(set(base_files) | set(head_files)):
        golden = path.startswith(GOLDEN+'/')
        if path not in head_files:
            why = ' golden은 지우지 않고 새 기준점 경로를 추가합니다.' if golden else ''
            found.append(f'{_c(kind)} `{_c(path)}`이(가) 삭제되었습니다.{_c(why)}')
        elif path not in base_files:
            found.append(f'{_c(kind)} `{_c(path)}`이(가) 추가되었습니다. CI는 상용 도구 출력인지 가릴 수 없습니다.')
        elif base_files[path] != head_files[path]:
            why = ' golden은 상용 도구 출력에서 한 번 만들고 고치지 않습니다.' if golden else ''
            found.append(f'{_c(kind)} `{_c(path)}`이(가) 수정되었습니다.{_c(why)}')
    return found


def violations(base, head):
    """Korean reasons why head needs 도재겸's bypass against base; [] when no baseline moved."""
    found = []
    for rule in head.get('duplicate_rules', []):
        found.append(f'규칙 `{_c(rule)}`이(가) `{RULES}`에 두 번 이상 있습니다. 어느 상태가 맞는지 정할 수 없어 통과시키지 않습니다.')
    base_entries, head_entries = base.get('entries', {}), head.get('entries', {})
    if base_entries:  # first introduction (no tree known for base) has nothing to compare
        for name, mode in sorted(head_entries.items()):
            if base_entries.get(name) == mode:
                continue
            stem, dot, suffix = name.rpartition('.')
            why = ('폴더(패키지)' if mode in ('040000', '160000') else '심볼릭 링크' if mode == '120000'
                   else '캐시 폴더' if name == '__pycache__'
                   else '컴파일된 모듈' if name.endswith(BINARY_SUFFIXES)
                   else '표준 라이브러리·KLayout 모듈과 같은 이름' if dot and suffix == 'py' and stem in SHADOWED
                   else None)
            if why:
                found.append(f'`{SCRIPTS}/{_c(name)}`에 새 {why}이(가) 생겼습니다. 같은 폴더의 `import`가 '
                             '다른 코드를 읽게 될 수 있어 통과시키지 않습니다.')
    base_sources = base.get('sources', {})
    for path, (digest, problems) in sorted(head.get('sources', {}).items()):
        if problems and base_sources.get(path, (None,))[0] != digest:
            found.append(f'fixture 정의 파일 `{_c(path)}`에 정의 밖의 코드가 있습니다: '+'; '.join(_c(p).rstrip('.') for p in problems)
                         +'. 이 파일은 시험 과정에서 reliability.py와 같은 프로세스로 실행되므로 fixture 정의만 둘 수 있습니다.')
    base_files = dict(base['golden'], **base['baseline_files'])
    head_files = dict(head['golden'], **head['baseline_files'])
    introduced = bool(base_files)  # before the first golden, rules reach verified with the baseline itself
    for rule, before in sorted(base['rules'].items()):
        after = head['rules'].get(rule)
        if after is None:
            found.append(f'규칙 `{_c(rule)}`이(가) `{_c(RULES)}`에서 사라졌습니다(이전 상태 {_c(before)}).')
        elif RANK[after] < RANK[before]:
            found.append(f'규칙 `{_c(rule)}`의 상태가 {_c(before)}에서 {_c(after)}(으)로 내려갔습니다.')
        elif introduced and after == 'verified' and before != 'verified':
            found.append(f'규칙 `{_c(rule)}`이(가) {_c(before)}에서 verified로 올라갔습니다(golden_compared). '
                         'Calibre golden과 맞춰 본 근거를 도재겸이 확인해야 합니다.')
    for rule, after in sorted(head['rules'].items()):
        if introduced and rule not in base['rules'] and after == 'verified':
            found.append(f'새 규칙 `{_c(rule)}`이(가) 처음부터 verified로 들어왔습니다(golden_compared). '
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
            found.append(f'미검증 목록 `{_c(UNVERIFIED)}`에 새 항목 `{_c(item)}`이(가) 생겼습니다. '
                         '이미 검증된 것을 미검증으로 돌리면 안 됩니다.')
        for item in sorted(base['unverified']-after):
            found.append(f'미검증 항목 `{_c(item)}`이(가) 빠졌습니다. 닫는 근거를 도재겸이 확인해야 합니다.')
        for item in sorted(base['unverified'] & after):
            wider = sorted(set(head['unverified_checks'].get(item, ()))-set(base['unverified_checks'].get(item, ())))
            if wider:
                found.append(f'미검증 항목 `{_c(item)}`이(가) 허용하는 체크가 늘었습니다: '
                             +', '.join(f'`{_c(c)}`' for c in wider)+'.')
    if base['table'] is not None:
        after = head['table'] or {}
        for row, before in sorted(base['table'].items()):
            if row not in after:
                found.append(f'대응표 `{_c(TABLE)}`에서 행 `{_c(row)}`이(가) 사라졌습니다.')
            elif before == 'match' and after[row] != 'match':
                found.append(f'대응표 행 `{_c(row)}`의 판정이 match에서 {_c(after[row])}(으)로 내려갔습니다.')
        for row, verdict in sorted(after.items()):
            if verdict == 'match' and base['table'].get(row) != 'match':
                found.append(f'대응표 행 `{_c(row)}`이(가) match가 되었습니다. 일치 근거를 도재겸이 확인해야 합니다.')
    return found


def _c(value):
    """A value from the PR shown in a message: newlines and control characters escaped, no backticks."""
    return json.dumps(str(value), ensure_ascii=False)[1:-1].replace('`', "'")


def report(base_ref, found):
    if not found:
        return (f'# 기준 파일 확인\n\n`{base_ref}`와(과) 비교해 기준 파일·검사 코드에 '
                '우회 머지가 필요한 변경이 없습니다.\n')
    lines = ['# 기준 파일 확인: 실패', '', f'`{base_ref}`와(과) 비교해 아래 변경은 우회 머지가 필요합니다.', '']
    lines += ['- '+text.replace('\r', '\\r').replace('\n', '\\n') for text in found]
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
