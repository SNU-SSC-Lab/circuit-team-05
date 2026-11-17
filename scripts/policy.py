"""Shared local/CI checks. No network calls or execution of hook-provided commands."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

INDEX = 'docs/specs/index.json'
POLICY_FILES = {'AGENTS.md', 'CLAUDE.md', '.gitignore', '.gitattributes', INDEX, 'requirements-ci.txt'}


class PolicyError(Exception):
    pass


def git(root: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                            encoding='utf-8', errors='replace', timeout=20)
    if result.returncode:
        raise PolicyError(f'Git 조회 실패: {" ".join(args[:2])}: {result.stderr.strip()}')
    return result.stdout.strip()


def root_at(cwd: str | Path) -> Path:
    return Path(git(Path(cwd), 'rev-parse', '--show-toplevel')).resolve()


def local_path(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise PolicyError(f'저장소 밖 경로는 사용할 수 없습니다: {value}')
    return path


def digest(path: Path) -> str:
    # Git checkouts can use CRLF on Windows. The document version must survive clone.
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def read(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError) as error:
        raise PolicyError(f'문서를 읽을 수 없습니다: {path.name}: {error}') from error


def sections(text: str) -> dict[str, str]:
    # Headings inside examples/fences are not document structure.
    cleaned = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    outside, fenced = [], False
    for line in cleaned.splitlines():
        if re.match(r'^\s*(`{3,}|~{3,})', line):
            fenced = not fenced
        elif not fenced:
            outside.append(line)
    cleaned = '\n'.join(outside)
    matches = list(re.finditer(r'^## (.+?)\s*$', cleaned, re.M))
    names = [m[1] for m in matches]
    if len(names) != len(set(names)):
        raise PolicyError('같은 문서 제목이 중복되었습니다.')
    return {m[1]: cleaned[m.end():matches[i+1].start() if i+1 < len(matches) else None]
            for i, m in enumerate(matches)}


def filled(text: str) -> bool:
    if re.search(r'\b(TODO|TBD|PLACEHOLDER)\b|작성해\s*주세요|내용을\s*입력', text, re.I):
        return False
    return bool(re.search(r'[\w가-힣]', re.sub(r'\[[ xX]\]', '', text)))


def required_sections(text: str, titles: tuple[str, ...]) -> None:
    found = sections(text)
    for title in titles:
        if title not in found or not filled(found[title]):
            raise PolicyError(f'문서의 "## {title}" 내용을 구체적으로 작성하세요.')


def registry(root: Path) -> dict[str, dict]:
    try:
        data = json.loads(read(root / INDEX))
        entries = data['specs']
        if data['version'] != 1 or not isinstance(entries, list):
            raise ValueError('version/specs')
        result = {}
        for entry in entries:
            path = entry['path']
            if path in result or not path.startswith('docs/specs/') or not path.endswith('.md'):
                raise ValueError('중복 또는 잘못된 SPEC 경로')
            local_path(root, path)
            if not entry['targets'] or not entry['rfcs']:
                raise ValueError('대상 파일과 RFC가 필요함')
            for target in entry['targets']:
                if not isinstance(target, str) or target.startswith('/') or '..' in Path(target).parts:
                    raise ValueError('잘못된 대상 경로')
            for ref in entry['rfcs']:
                if not ref['path'].startswith('docs/rfcs/') or not re.fullmatch('[0-9a-f]{64}', ref['sha256']):
                    raise ValueError('잘못된 RFC 참조/버전')
                local_path(root, ref['path'])
            result[path] = entry
        return result
    except (ValueError, KeyError, TypeError) as error:
        raise PolicyError(f'{INDEX} 형식을 확인하세요: {error}') from error


def validate_spec(root: Path, entry: dict, *, current: bool = True) -> None:
    text = read(local_path(root, entry['path']))
    required_sections(text, ('What', 'Why', 'How', 'RFC 확인'))
    for ref in entry['rfcs']:
        path = local_path(root, ref['path'])
        contents = read(path)
        if not re.search(r'^## [A-Z]+\d+ ', contents, re.M):
            raise PolicyError(f'{ref["path"]}: 식별할 수 있는 규칙 항목이 없습니다.')
        if current and digest(path) != ref['sha256']:
            raise PolicyError(f'{entry["path"]}: {ref["path"]}의 버전이 바뀌었습니다. '
                              '규칙과 영향을 다시 읽고 SPEC·index.json의 확인 버전을 갱신하세요.')


def covered(entry: dict, file: str) -> bool:
    return any(fnmatch.fnmatchcase(file, pattern) for pattern in entry['targets']) or any(
        file == ref['path'] for ref in entry['rfcs'])


def protected(file: str) -> bool:
    return (file in POLICY_FILES or Path(file).suffix.lower() in
            {'.v', '.sv', '.py', '.sh', '.ps1', '.json', '.toml', '.yml', '.yaml'} or
            file.startswith(('src/', 'scripts/', 'tests/', '.githooks/',
                             '.claude/', '.codex/', 'docs/rfcs/', '.github/')))


def check_docs(root: Path) -> None:
    entries = registry(root)
    for entry in entries.values():
        # Historical SPECs can retain an older RFC version until selected for a change.
        validate_spec(root, entry, current=False)
    for path in (root / 'src').rglob('*'):
        if not path.is_file() or path.suffix.lower() not in ('.v', '.sv'):
            continue
        file = path.relative_to(root).as_posix()
        if not any(covered(e, file) for e in entries.values()):
            raise PolicyError(f'{file}의 관련 SPEC 연결이 없습니다.')


def changed_files(root: Path, base: str, head: str) -> list[str]:
    # --no-renames keeps both the removed and added paths for a rename.
    merge_base = git(root, 'merge-base', base, head)
    return git(root, 'diff', '--name-only', '--no-renames', merge_base, head).splitlines()


def check_pr(root: Path, body: str, base: str | None = None, head: str = 'HEAD') -> None:
    required_sections(body, ('What', 'Why', 'How'))
    entries = registry(root)
    selected = list(dict.fromkeys(p for p in re.findall(r'docs/specs/[\w-]+\.md', body)
                                  if p != 'docs/specs/README.md'))
    for path in selected:
        if path not in entries:
            raise PolicyError(f'등록되지 않은 SPEC입니다: {path}')
        validate_spec(root, entries[path])
    if base:
        files = changed_files(root, base, head)
        for file in files:
            if protected(file) and not any(covered(entries[p], file) for p in selected):
                raise PolicyError(f'{file} 변경을 설명하는 SPEC을 PR에 연결하세요.')
        if any(protected(f) and not f.startswith('docs/rfcs/') for f in files):
            flow = re.search(r'^흐름 변경:\s*(있음|없음)\s*$', body, re.M)
            if not flow:
                raise PolicyError('How에 "흐름 변경: 있음" 또는 "흐름 변경: 없음"을 적으세요.')
            if flow[1] == '있음':
                comparisons = [read(root / p) for p in selected]
                if not any('### 변경 전' in s and '### 변경 후' in s and
                           s.count('```mermaid') >= 2 and '```diff' in s for s in comparisons):
                    raise PolicyError('흐름이 바뀌면 관련 SPEC에 변경 전후 그림과 핵심 코드 diff를 적으세요.')
            elif not re.search(r'^시각화 생략 이유:\s*\S.+', body, re.M):
                raise PolicyError('How에 시각화 생략 이유를 적으세요.')


def receipt_path(root: Path, session: str) -> Path:
    if not session:
        raise PolicyError('세션 ID가 없습니다. 시작 훅의 안내를 확인하세요.')
    key = hashlib.sha256(session.encode()).hexdigest()
    path = Path(git(root, 'rev-parse', '--git-path', f'ssc-policy/{key}.json'))
    return path if path.is_absolute() else root / path


def snapshot(root: Path, paths: list[str]) -> dict[str, str]:
    entries = registry(root)
    files = {INDEX}
    for p in paths:
        if p not in entries:
            raise PolicyError(f'등록되지 않은 SPEC입니다: {p}')
        validate_spec(root, entries[p])
        files.add(p)
        files.update(ref['path'] for ref in entries[p]['rfcs'])
    return {p: digest(local_path(root, p)) for p in sorted(files)}


def review(root: Path, session: str, specs: list[str], summary: str) -> None:
    if not specs or not filled(summary) or len(summary.strip()) < 12:
        raise PolicyError('SPEC과 이번 변경이 관련 규칙에 미치는 영향 요약을 적으세요.')
    hashes = snapshot(root, specs)
    for p in hashes:
        if p != INDEX:
            print(f'\n--- {p} ---\n{read(root / p)}')
    path = receipt_path(root, session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'specs': specs, 'hashes': hashes, 'summary': summary},
                               ensure_ascii=False), encoding='utf-8')
    print('\n확인 기록을 남겼습니다. 내용 이해와 변경 타당성은 PR에서 검토합니다.')


def require_review(root: Path, session: str, files: list[str] | None = None) -> None:
    try:
        data = json.loads(read(receipt_path(root, session)))
        if data['hashes'] != snapshot(root, data['specs']):
            raise PolicyError('확인 후 문서 또는 목록이 바뀌었습니다. 다시 확인하세요.')
        entries = registry(root)
        for file in files or []:
            if protected(file) and not any(covered(entries[p], file) for p in data['specs']):
                raise PolicyError(f'{file}은 확인한 SPEC의 변경 범위에 없습니다.')
    except (KeyError, ValueError, TypeError) as error:
        raise PolicyError('확인 기록이 올바르지 않습니다. review를 다시 실행하세요.') from error


def review_hint(session: str) -> str:
    return ('SPEC·RFC 확인이 필요합니다. '
            f'python scripts/policy.py review --session "{session}" '
            '--spec docs/specs/0001-agent-hooks.md --summary "이번 변경과 규약의 관계를 설명" '
            '형식으로 관련 SPEC을 확인하세요.')


def edit_files(root: Path, tool: str, args: dict, cwd: Path | None = None) -> list[str] | None:
    paths = []
    if tool in ('Edit', 'Write', 'MultiEdit'):
        paths = [args.get('file_path', '')]
    elif tool in ('apply_patch', 'mcp__filesystem__apply_patch'):
        patch = args.get('command', args.get('patch', args.get('input', '')))
        paths = re.findall(r'^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$', patch, re.M)
        if not paths:
            raise PolicyError('편집 대상 경로를 확인할 수 없습니다.')
    else:
        return None
    result = []
    for path in paths:
        if not path:
            raise PolicyError('편집 대상 경로가 없습니다.')
        actual = ((cwd or root) / path).resolve()
        if actual.is_relative_to(root):
            result.append(actual.relative_to(root).as_posix())
    return result


def tokens(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError as error:
        raise PolicyError('명령 인자를 해석할 수 없습니다. 단일 명령으로 실행하세요.') from error


def option(words: list[str], key: str) -> str | None:
    for i, word in enumerate(words):
        if word.startswith(key+'='):
            return word.split('=', 1)[1]
        if word == key:
            if i+1 >= len(words):
                raise PolicyError(f'{key} 값이 없습니다.')
            return words[i+1]
    return None


def shell_check(root: Path, session: str, command: str, cwd: Path | None = None) -> None:
    if re.search(r'--no-verify|core\.hooksPath\s*=', command, re.I):
        raise PolicyError('훅을 우회하지 마세요. 검사 오류는 별도 작업 브랜치에서 수정하세요.')
    compound = bool(re.search(r'[;&|><`\n\r]|\$\(', command))
    words = tokens(command)
    # A review must be callable before any receipt exists. No compound form.
    if (not compound and len(words) >= 3 and Path(words[0]).stem.lower() in
            ('python', 'python3', 'python.exe') and
            ((cwd or root) / words[1]).resolve() == (root / 'scripts/policy.py').resolve()
            and words[2] in ('review', 'check-docs', 'check-pr')):
        return
    if re.search(r'\bgh\s+pr\s+(create|edit)\b', command):
        if compound or words[:2] != ['gh', 'pr']:
            raise PolicyError('PR 본문 검사는 단일 gh pr 명령과 --body-file을 사용하세요.')
        body_file = option(words, '--body-file')
        body = option(words, '--body')
        if words[2] == 'edit' and body_file is None and body is None:
            return  # Reviewers/title-only edits do not change the body.
        if body_file is None and body is None:
            raise PolicyError('What·Why·How를 작성한 --body-file 또는 --body를 지정하세요.')
        base = option(words, '--base')
        if words[2] == 'create' and base is None:
            raise PolicyError('연속 PR의 기준을 명시하도록 --base를 지정하세요.')
        if words[2] == 'create' and option(words, '--head') not in (None, git(root, 'branch', '--show-current')):
            raise PolicyError('현재 체크아웃한 작업 브랜치에서 PR을 작성하세요.')
        check_pr(root, read(((cwd or root) / body_file).resolve()) if body_file else body or '', base)
        return
    if not compound:
        if words[:2] in (['git', 'status'], ['git', 'log'], ['git', 'show'],
                         ['git', 'diff'], ['git', 'rev-parse'], ['git', 'ls-files']):
            if not any(w.startswith(('--output', '--ext-diff', '--textconv')) for w in words):
                return
        if words and words[0].lower() in ('rg', 'cat', 'get-content', 'get-childitem', 'pwd', 'get-location'):
            if not any(w == '--pre' or w.startswith('--pre=') for w in words):
                return
        if words[:3] in (['gh', 'pr', 'view'], ['gh', 'pr', 'list'], ['gh', 'pr', 'diff']):
            return
    try:
        require_review(root, session)
    except PolicyError as error:
        raise PolicyError(f'{error}\n{review_hint(session)}') from error


def hook(event: dict) -> None:
    root = root_at(event.get('cwd', '.'))
    session = event.get('session_id', '')
    if event.get('hook_event_name') == 'SessionStart':
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart',
              'additionalContext': f'RFC 0002와 관련 SPEC을 먼저 확인하세요.\n{review_hint(session)}'}}, ensure_ascii=False))
        return
    if event.get('hook_event_name') != 'PreToolUse':
        return
    tool, args = event.get('tool_name', ''), event.get('tool_input', {})
    if not isinstance(args, dict):
        raise PolicyError('도구 입력은 JSON 객체여야 합니다.')
    cwd = Path(event.get('cwd', str(root))).resolve()
    files = edit_files(root, tool, args, cwd)
    if files is not None:
        files = [f for f in files if protected(f)]
        if files:
            try:
                require_review(root, session, files)
            except PolicyError as error:
                raise PolicyError(f'{error}\n{review_hint(session)}') from error
        return
    if tool in ('Bash', 'PowerShell', 'exec_command', 'shell_command'):
        command = args.get('command', args.get('cmd', ''))
        if not isinstance(command, str) or not command:
            raise PolicyError('검사할 명령이 없습니다.')
        shell_check(root, session, command, cwd)
        return
    if re.search(r'(create_pull_request|update_pull_request)$', tool):
        if 'body' in args:
            check_pr(root, args['body'], args.get('base'))
        elif tool.endswith('create_pull_request'):
            raise PolicyError('PR 생성 시 What·Why·How 본문이 필요합니다.')
        return
    if re.search(r'(create_file|update_file|delete_file|create_commit|create_tree|update_ref)$', tool):
        raise PolicyError('원격 코드·브랜치 쓰기는 로컬 작업 브랜치와 PR로 진행하세요.')


def pre_push(stream: str) -> None:
    for line in stream.splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 4:
            raise PolicyError('Git 전송 ref 입력을 해석할 수 없습니다.')
        if fields[2] == 'refs/heads/main':
            raise PolicyError('main 직접 push·삭제는 금지합니다. 작업 브랜치와 PR을 사용하세요.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.')
    sub = parser.add_subparsers(dest='action', required=True)
    review_parser = sub.add_parser('review')
    review_parser.add_argument('--session', required=True)
    review_parser.add_argument('--spec', action='append', required=True)
    review_parser.add_argument('--summary', required=True)
    sub.add_parser('check-docs')
    pr_parser = sub.add_parser('check-pr')
    pr_parser.add_argument('--body-file', required=True)
    pr_parser.add_argument('--base', required=True)
    pr_parser.add_argument('--head', default='HEAD')
    hook_parser = sub.add_parser('hook')
    hook_parser.add_argument('--agent', choices=['claude', 'codex'], required=True)
    sub.add_parser('pre-push')
    args = parser.parse_args()
    try:
        if args.action == 'pre-push':
            pre_push(sys.stdin.read())
        elif args.action == 'hook':
            event = json.load(sys.stdin)
            if not isinstance(event, dict):
                raise PolicyError('훅 입력은 JSON 객체여야 합니다.')
            hook(event)
        else:
            root = root_at(args.root)
            if args.action == 'review':
                review(root, args.session, args.spec, args.summary)
            elif args.action == 'check-docs':
                check_docs(root)
                print('문서 구조와 RTL별 SPEC 연결 확인 완료.')
            else:
                check_pr(root, read(Path(args.body_file)), args.base, args.head)
                print('PR 형식·SPEC 연결·RFC 버전 확인 완료.')
    except Exception as error:
        # Adapter failures must use the blocking exit code, not an ignored error code.
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
