import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE / 'scripts'))
import policy
from install_hooks import install

S1 = 'docs/specs/0001-agent-hooks.md'
S2 = 'docs/specs/0002-ternary-decoder.md'


def run(cwd, *args, input=None):
    return subprocess.run(args, cwd=cwd, input=input, capture_output=True,
                          encoding='utf-8', errors='replace', timeout=30)


class RepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ssc-policy-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        for directory in ('docs', 'src', 'scripts', '.githooks', '.claude', '.codex'):
            shutil.copytree(SOURCE / directory, self.root / directory,
                            ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(SOURCE / '.gitattributes', self.root / '.gitattributes')
        self.g('init', '-b', 'feature')
        self.g('config', 'user.email', 'policy-test@example.invalid')
        self.g('config', 'user.name', 'Policy fixture')
        self.g('config', 'core.autocrlf', 'false')
        self.g('add', '.')
        self.g('commit', '-m', 'fixture')
        self.base = self.g('rev-parse', 'HEAD')

    def g(self, *args):
        result = run(self.root, 'git', *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def review(self, *specs, session='session-a'):
        with contextlib.redirect_stdout(io.StringIO()):
            policy.review(self.root, session, list(specs or [S1]),
                          '대상 모듈의 규약과 변경 범위를 읽고 영향을 확인한다.')

    def event(self, tool='Edit', args=None, session='session-a', cwd=None):
        return {'hook_event_name': 'PreToolUse', 'session_id': session,
                'cwd': str(cwd or self.root), 'tool_name': tool,
                'tool_input': args or {'file_path': 'scripts/policy.py'}}

    def body(self, spec=S1):
        return (f'## What\n변경 내용과 대상.\n## Why\n문제를 해결한다.\n## How\n'
                f'{spec}에 따라 구현하고 단위 검사를 실행했다.\n'
                '흐름 변경: 없음\n시각화 생략 이유: 기존 동작을 유지하는 시험용 수정이다.\n')

    def test_documents_and_ten_module_specs(self):
        policy.check_docs(self.root)
        entries = policy.registry(self.root)
        self.assertEqual(sum(e['kind'] == 'reverse' for e in entries.values()), 10)
        for source in (self.root / 'src').glob('*.v'):
            self.assertTrue(any(e['targets'] == [f'src/{source.name}'] for e in entries.values()))

    def test_fresh_clone_preserves_rfc_versions(self):
        clone = Path(self.temp.name) / 'fresh clone'
        result = run(self.root, 'git', 'clone', str(self.root), str(clone))
        self.assertEqual(result.returncode, 0, result.stderr)
        for entry in policy.registry(clone).values():
            policy.validate_spec(clone, entry)
        with contextlib.redirect_stdout(io.StringIO()):
            policy.review(clone, 'new-clone', [S1], '새 clone의 줄바꿈과 규약 버전이 같은지 확인한다.')

    def test_unmapped_rtl_is_rejected(self):
        (self.root / 'src/new.v').write_text('module new; endmodule')
        with self.assertRaisesRegex(policy.PolicyError, '관련 SPEC'):
            policy.check_docs(self.root)

    def test_new_nested_module_accepts_forward_spec(self):
        folder=self.root/'src/new'; folder.mkdir()
        (folder/'forward.sv').write_text('module forward; endmodule')
        path=self.root/policy.INDEX
        data=json.loads(path.read_text(encoding='utf-8'))
        data['specs'][0]['targets'].append('src/new/forward.sv')
        path.write_text(json.dumps(data),encoding='utf-8')
        policy.check_docs(self.root)

    def test_unmapped_nested_module_is_rejected(self):
        folder=self.root/'src/new'; folder.mkdir()
        (folder/'new.sv').write_text('module new; endmodule')
        with self.assertRaisesRegex(policy.PolicyError, '관련 SPEC'):
            policy.check_docs(self.root)

    def test_missing_or_empty_sections(self):
        for body in ['## What\n내용', '## What\n<!-- note -->\n## Why\n이유\n## How\n방법',
                     '## What\nTODO\n## Why\n이유\n## How\n방법']:
            with self.subTest(body=body), self.assertRaises(policy.PolicyError):
                policy.check_pr(self.root, body)

    def test_headings_in_fences_do_not_count(self):
        with self.assertRaises(policy.PolicyError):
            policy.check_pr(self.root, '```\n'+self.body()+'\n```')

    def test_duplicate_heading_is_rejected(self):
        with self.assertRaisesRegex(policy.PolicyError, '중복'):
            policy.check_pr(self.root, self.body()+'\n## What\n다시')

    def test_complete_pr_passes(self):
        policy.check_pr(self.root, self.body(), self.base)
        policy.check_pr(self.root, self.body()+'\n문서 목록: docs/specs/README.md', self.base)

    def test_native_edit_is_denied_before_review(self):
        with self.assertRaisesRegex(policy.PolicyError, 'SPEC·RFC 확인'):
            policy.hook(self.event())

    def test_native_edit_passes_after_review(self):
        self.review()
        policy.hook(self.event())

    def test_review_does_not_allow_another_scope(self):
        self.review()
        with self.assertRaisesRegex(policy.PolicyError, '범위'):
            policy.hook(self.event(args={'file_path': 'src/ternary_decoder.v'}))

    def test_module_spec_allows_only_that_module(self):
        self.review(S2)
        policy.hook(self.event(args={'file_path': 'src/ternary_decoder.v'}))
        with self.assertRaises(policy.PolicyError):
            policy.hook(self.event(args={'file_path': 'src/adder12.v'}))

    def test_new_session_requires_review(self):
        self.review()
        with self.assertRaises(policy.PolicyError):
            policy.hook(self.event(session='session-b'))

    def test_rfc_change_invalidates_review(self):
        self.review()
        path = self.root / 'docs/rfcs/0002-collaboration.md'
        path.write_text(path.read_text(encoding='utf-8')+'\n규칙 추가\n', encoding='utf-8')
        with self.assertRaisesRegex(policy.PolicyError, '버전'):
            policy.hook(self.event())

    def test_spec_change_invalidates_review(self):
        self.review()
        path = self.root / S1
        path.write_text(path.read_text(encoding='utf-8')+'\n계획 변경\n', encoding='utf-8')
        with self.assertRaisesRegex(policy.PolicyError, '다시 확인'):
            policy.hook(self.event())

    def test_index_change_invalidates_review(self):
        self.review()
        path = self.root / policy.INDEX
        path.write_text(path.read_text(encoding='utf-8')+'\n', encoding='utf-8')
        with self.assertRaises(policy.PolicyError):
            policy.hook(self.event())

    def test_plain_read_and_readme_edit_are_allowed(self):
        policy.hook(self.event('Bash', {'command': 'git status --short'}))
        policy.hook(self.event('Write', {'file_path': 'README.md'}))

    def test_arbitrary_shell_writer_requires_review(self):
        for command in ['python write_file.py', 'Set-Content src/adder12.v changed',
                        'git status; python write_file.py', 'rg --pre writer pattern .']:
            with self.subTest(command=command), self.assertRaises(policy.PolicyError):
                policy.hook(self.event('Bash', {'command': command}))
        self.review()
        policy.hook(self.event('PowerShell', {'command': 'python write_file.py'}))

    def test_review_command_is_allowed_without_receipt(self):
        policy.hook(self.event('Bash', {'command': 'python scripts/policy.py review --session x --spec a --summary b'}))

    def test_another_policy_script_is_not_a_review_bypass(self):
        with self.assertRaises(policy.PolicyError):
            policy.hook(self.event('Bash', {'command': 'python elsewhere/scripts/policy.py review'}))

    def test_hook_bypass_is_denied_even_after_review(self):
        self.review()
        with self.assertRaisesRegex(policy.PolicyError, '우회'):
            policy.hook(self.event('Bash', {'command': 'git push --no-verify origin feature'}))

    def test_patch_checks_deleted_and_move_paths(self):
        self.review(S2)
        policy.hook(self.event('apply_patch', {'command': '*** Update File: src/ternary_decoder.v\n@@\n'}))
        for patch in ['*** Delete File: src/adder12.v\n',
                      '*** Update File: src/ternary_decoder.v\n*** Move to: src/adder12.v\n']:
            with self.subTest(patch=patch), self.assertRaises(policy.PolicyError):
                policy.hook(self.event('apply_patch', {'command': patch}))

    def test_relative_edit_in_subdirectory(self):
        self.review(S2)
        policy.hook(self.event('apply_patch', {'command': '*** Update File: ternary_decoder.v\n'},
                               cwd=self.root / 'src'))

    def test_source_change_needs_correct_spec_in_pr(self):
        path = self.root / 'src/ternary_decoder.v'
        path.write_text(path.read_text(encoding='utf-8')+'\n// fixture\n', encoding='utf-8')
        self.g('add', '.'); self.g('commit', '-m', 'changed code')
        with self.assertRaisesRegex(policy.PolicyError, 'SPEC을 PR에 연결'):
            policy.check_pr(self.root, self.body(), self.base)
        with self.assertRaisesRegex(policy.PolicyError, 'SPEC을 PR에 연결'):
            policy.check_pr(self.root, self.body('docs/specs/README.md'), self.base)
        policy.check_pr(self.root, self.body(S2), self.base)

    def test_flow_change_requires_paired_diagrams_and_diff(self):
        path = self.root / 'src/ternary_decoder.v'
        path.write_text(path.read_text(encoding='utf-8')+'\n// fixture\n', encoding='utf-8')
        self.g('add', '.'); self.g('commit', '-m', 'changed code')
        with self.assertRaisesRegex(policy.PolicyError, '변경 전후'):
            policy.check_pr(self.root, self.body(S2).replace('흐름 변경: 없음', '흐름 변경: 있음'), self.base)

    def test_missing_flow_declaration_is_rejected(self):
        path = self.root / 'src/ternary_decoder.v'
        path.write_text(path.read_text(encoding='utf-8')+'\n// fixture\n', encoding='utf-8')
        self.g('add', '.'); self.g('commit', '-m', 'changed code')
        with self.assertRaisesRegex(policy.PolicyError, '흐름 변경'):
            policy.check_pr(self.root, self.body(S2).replace('흐름 변경: 없음', ''), self.base)

    def test_unregistered_spec_in_pr_is_rejected(self):
        with self.assertRaisesRegex(policy.PolicyError, '등록되지 않은'):
            policy.check_pr(self.root, self.body('docs/specs/not-real.md'))

    def test_deleted_code_requires_spec(self):
        (self.root / 'src/ternary_decoder.v').unlink()
        self.g('add', '.'); self.g('commit', '-m', 'deleted code')
        with self.assertRaises(policy.PolicyError):
            policy.check_pr(self.root, self.body(), self.base)

    def test_renamed_code_requires_both_paths(self):
        self.g('mv', 'src/ternary_decoder.v', 'src/new_decoder.v')
        self.g('commit', '-m', 'renamed code')
        with self.assertRaisesRegex(policy.PolicyError, 'new_decoder'):
            policy.check_pr(self.root, self.body(S2), self.base)

    def test_cli_pr_requires_body_and_base(self):
        for cmd in ['gh pr create --fill', 'gh pr create --body something']:
            with self.subTest(cmd=cmd), self.assertRaises(policy.PolicyError):
                policy.hook(self.event('Bash', {'command': cmd}))
        file = self.root / 'body.md'; file.write_text(self.body(), encoding='utf-8')
        policy.hook(self.event('Bash', {'command': f'gh pr create --base {self.base} --body-file body.md'}))
        policy.hook(self.event('Bash', {'command': 'gh pr edit 1 --add-reviewer lumirevel'}))

    def test_cli_compound_pr_is_rejected(self):
        with self.assertRaises(policy.PolicyError):
            policy.hook(self.event('Bash', {'command': 'cd elsewhere; gh pr create --body-file body.md'}))

    def test_mcp_pr_and_remote_writes(self):
        for prefix in ('mcp__github__', 'mcp__codex_apps__github_'):
            policy.hook(self.event(prefix+'create_pull_request', {'body': self.body()}))
            with self.assertRaises(policy.PolicyError):
                policy.hook(self.event(prefix+'create_pull_request', {'body': ''}))
            with self.assertRaises(policy.PolicyError):
                policy.hook(self.event(prefix+'update_ref', {'ref': 'refs/heads/main'}))

    def test_bad_registry_path_cannot_escape(self):
        path = self.root / policy.INDEX; data = json.loads(path.read_text(encoding='utf-8'))
        data['specs'][0]['rfcs'][0]['path'] = 'docs/rfcs/../../../../outside'
        path.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(policy.PolicyError):
            policy.registry(self.root)

    def test_raw_adapter_returns_blocking_exit_code(self):
        for agent, tool in [('claude', 'Edit'), ('codex', 'apply_patch')]:
            args = {'file_path': 'scripts/policy.py'} if tool == 'Edit' else {'command': '*** Update File: scripts/policy.py\n'}
            result = run(self.root, sys.executable, 'scripts/policy.py', 'hook', '--agent', agent,
                         input=json.dumps(self.event(tool, args)))
            self.assertEqual(result.returncode, 2, result.stderr)
        self.review()
        result = run(self.root, sys.executable, 'scripts/policy.py', 'hook', '--agent', 'codex',
                     input=json.dumps(self.event('apply_patch', {'command': '*** Update File: scripts/policy.py\n'})))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_malformed_hook_input_is_denied(self):
        for text in ['{', '[]', '{"tool_input": [] ,"hook_event_name":"PreToolUse"}']:
            result = run(self.root, sys.executable, 'scripts/policy.py', 'hook', '--agent', 'codex', input=text)
            self.assertEqual(result.returncode, 2, result.stderr)

    def test_session_start_returns_readable_context(self):
        event = self.event(); event['hook_event_name'] = 'SessionStart'
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            policy.hook(event)
        result = json.loads(out.getvalue())
        self.assertIn('RFC 0002', result['hookSpecificOutput']['additionalContext'])

    def test_installer_preserves_another_hook_setup(self):
        self.g('config', '--local', 'core.hooksPath', 'other-hooks')
        with self.assertRaisesRegex(policy.PolicyError, '덮어쓰지'):
            install(self.root)
        self.assertEqual(self.g('config', '--get', 'core.hooksPath'), 'other-hooks')

    def test_real_push_to_local_remote(self):
        remote = Path(self.temp.name) / 'remote.git'
        self.g('init', '--bare', str(remote))
        self.g('remote', 'add', 'test', str(remote))
        with contextlib.redirect_stdout(io.StringIO()):
            install(self.root)
        result = run(self.root, 'git', 'push', 'test', 'HEAD:refs/heads/feature')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run(self.root, 'git', 'push', 'test', 'HEAD:refs/heads/main')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('main 직접 push', result.stderr)
        self.assertNotIn('refs/heads/main', self.g('ls-remote', 'test'))
        result = run(self.root, 'git', 'push', 'test', 'HEAD:refs/heads/other', 'HEAD:refs/heads/main')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('refs/heads/other', self.g('ls-remote', 'test'))
        # Seed a main ref in the isolated bare fixture, then exercise delete/force inputs.
        seeded = run(self.root, 'git', '--git-dir', str(remote), 'update-ref',
                     'refs/heads/main', self.base)
        self.assertEqual(seeded.returncode, 0, seeded.stderr)
        result = run(self.root, 'git', 'push', 'test', '--delete', 'main')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('main 직접 push', result.stderr)
        self.g('commit', '--allow-empty', '-m', 'new fixture head')
        result = run(self.root, 'git', 'push', '--force', 'test', 'HEAD:refs/heads/main')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('main 직접 push', result.stderr)

    def test_bash_settings_command_receives_stdin(self):
        bash = Path('C:/Program Files/Git/bin/bash.exe') if os.name == 'nt' else shutil.which('bash')
        if not bash or not Path(bash).is_file():
            self.skipTest('Git Bash/bash is unavailable')
        for agent, path in [('claude', '.claude/settings.json'), ('codex', '.codex/hooks.json')]:
            config = json.loads((self.root / path).read_text(encoding='utf-8'))
            command = config['hooks']['PreToolUse'][0]['hooks'][0]['command']
            result = run(self.root, str(bash), '-c', command, input=json.dumps(self.event()))
            self.assertEqual(result.returncode, 2, f'{agent}: {result.stderr}')
        self.review()
        result = run(self.root, str(bash), '-c', command, input=json.dumps(self.event()))
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(os.name == 'nt', 'Windows command override')
    def test_codex_windows_command_receives_stdin(self):
        config = json.loads((self.root / '.codex/hooks.json').read_text(encoding='utf-8'))
        command = config['hooks']['PreToolUse'][0]['hooks'][0]['commandWindows']
        result = run(self.root, 'powershell.exe', '-NoProfile', '-Command', command,
                     input=json.dumps(self.event()))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.review()
        result = run(self.root, 'powershell.exe', '-NoProfile', '-Command', command,
                     input=json.dumps(self.event()))
        self.assertEqual(result.returncode, 0, result.stderr)


class PushInputTest(unittest.TestCase):
    def test_creation_deletion_force_and_mixed_main_are_denied(self):
        zero, sha = '0'*40, 'a'*40
        for local, local_sha, remote_sha in [('refs/heads/feature',sha,zero),
                                            ('(delete)',zero,sha),('HEAD',sha,'b'*40)]:
            with self.subTest(local=local), self.assertRaises(policy.PolicyError):
                policy.pre_push(f'{local} {local_sha} refs/heads/main {remote_sha}')

    def test_feature_and_tag_main_name_are_allowed(self):
        policy.pre_push('HEAD a refs/heads/feature 0\nHEAD a refs/tags/main 0\n')

    def test_malformed_ref_input_is_denied(self):
        with self.assertRaises(policy.PolicyError):
            policy.pre_push('not a ref record with five fields')


if __name__ == '__main__':
    unittest.main()
