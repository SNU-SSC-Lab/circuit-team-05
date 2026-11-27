"""Baseline guard: verification baselines only move forward (SPEC 0019)."""
import contextlib
import io
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'/'asic'))
import baseline_guard

# Reviewer probes: walk from a generator frame into the guard's globals.
WALK = 'def g():\n    yield me.gi_frame.f_back\nme = g()\ntop = next(me)\n'
FRAME_EXIT = WALK+"top.f_back.f_globals['os']._exit(0)\ndef cases():\n    return []\n"
FRAME_PATCH = WALK+"top.f_back.f_globals['violations'] = lambda base, head: []\ndef cases():\n    return []\n"
# Review PoC: class patterns read dunder attributes without any Attribute node.
MATCH_ESCAPE = ("def cases():\n    match ():\n        case tuple(__class__=t):\n            pass\n"
                "    match t:\n        case type(__base__=o):\n            pass\n"
                "    match o:\n        case type(__subclasses__=s):\n            pass\n"
                "    return [{'rule': 'LEAK', 'n': len(s())}]\n")
LAST_LINE = '기준 파일 변경은 도재겸이 근거를 확인한 뒤 PR에서 우회 머지합니다(SPEC 0019).'


def snap(rules=None, unverified=(), golden=None, fixtures=None, rule='B', golden_fixtures=None,
         table=None, unverified_checks=None, files=None, guard=None):
    """Snapshot for tests; every fixture belongs to `rule` unless fixtures map gds -> (rule, hash)."""
    fixtures = fixtures or {}
    pairs = {gds: (v if isinstance(v, tuple) else (rule, v)) for gds, v in fixtures.items()}
    return {'rules': dict(rules or {}),
            'unverified': None if unverified is None else set(unverified),
            'unverified_checks': dict(unverified_checks or {}),
            'golden': dict(golden or {}),
            'fixtures': {gds: digest for gds, (_, digest) in pairs.items()},
            'fixture_rules': {gds: owner for gds, (owner, _) in pairs.items()},
            'golden_fixtures': {digest: dict(zip(('gds', 'rule', 'calibre'), entry))
                                for digest, entry in (golden_fixtures or {}).items()},
            'table': table,
            'baseline_files': dict(files or {}),
            'guard_files': dict(guard or {})}


# Golden fixtures of verified rule B: one fired, one clean.
BACKED = dict(rules={'B': 'verified'}, golden={'verification/reliability/golden/g/golden.json': 's1'},
              fixtures={'x.gds': 'h1', 'y.gds': 'h2'},
              golden_fixtures={'h1': ('x.gds', 'B', 'fired'), 'h2': ('y.gds', 'B', 'clean')})


def backed(**changes):
    return snap(**dict(BACKED, **changes))


class RuleStateTests(unittest.TestCase):
    def test_forward_moves_pass(self):
        base = snap(rules={'A': 'unported', 'B': 'ported'})
        head = snap(rules={'A': 'ported', 'B': 'ported'})
        self.assertEqual(baseline_guard.violations(base, head), [])

    def test_verified_downgrade_fails(self):
        base = snap(rules={'A': 'verified', 'B': 'verified'})
        head = snap(rules={'A': 'verified', 'B': 'ported'})
        found = baseline_guard.violations(base, head)
        self.assertEqual(len(found), 1, found)
        self.assertIn('`B`', found[0])

    def test_removed_rule_fails(self):
        found = baseline_guard.violations(snap(rules={'A': 'ported', 'B': 'ported'}), snap(rules={'A': 'ported'}))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`B`', found[0])

    def test_zero_verified_rules_fails(self):
        found = baseline_guard.violations(backed(), backed(rules={'B': 'ported'}))
        self.assertTrue(any('하나도' in v for v in found), found)

    def test_promotion_without_golden_fails(self):
        base = backed(rules={'B': 'verified', 'C': 'ported'})
        head = backed(rules={'B': 'verified', 'C': 'verified'},
                      fixtures={'x.gds': 'h1', 'y.gds': 'h2', 'c.gds': ('C', 'h9')})
        found = baseline_guard.violations(base, head)
        self.assertTrue(found and all('`C`' in v for v in found), found)

    def test_promotion_with_golden_needs_bypass(self):  # CI cannot tell real Calibre output from a hand-written one
        base = backed(rules={'B': 'verified', 'C': 'ported'})
        head = backed(rules={'B': 'verified', 'C': 'verified'},
                      fixtures={'x.gds': 'h1', 'y.gds': 'h2', 'c.gds': ('C', 'h9')},
                      golden_fixtures=dict(BACKED['golden_fixtures'], h9=('c.gds', 'C', 'fired')))
        found = baseline_guard.violations(base, head)
        self.assertEqual(len(found), 1, found)
        self.assertIn('`C`', found[0])
        self.assertIn('verified', found[0])


class FixtureTests(unittest.TestCase):
    def test_backed_snapshot_is_clean(self):
        self.assertEqual(baseline_guard.violations(backed(), backed()), [])

    def test_verified_fixture_changed_fails(self):  # Review Focus 1
        base = snap(rules={'B': 'verified'}, fixtures={'x.gds': 'h1'})
        head = snap(rules={'B': 'verified'}, fixtures={'x.gds': 'h2'})
        found = baseline_guard.violations(base, head)
        self.assertTrue(any('`x.gds`' in v for v in found), found)

    def test_backed_fixture_changed_fails(self):  # the golden still holds the old definition
        found = baseline_guard.violations(backed(), backed(fixtures={'x.gds': 'h3', 'y.gds': 'h2'}))
        self.assertTrue(any('`x.gds`' in v for v in found), found)

    def test_fixture_added_to_verified_rule_fails(self):  # Review Focus 5
        head = backed(fixtures={'x.gds': 'h1', 'y.gds': 'h2', 'z.gds': 'h9'})
        found = baseline_guard.violations(backed(), head)
        self.assertEqual(len(found), 1, found)
        self.assertIn('`z.gds`', found[0])
        self.assertIn('`B`', found[0])

    def test_fixture_added_with_new_golden_needs_bypass(self):
        new = 'verification/reliability/golden/g2/golden.json'
        head = backed(fixtures={'x.gds': 'h1', 'y.gds': 'h2', 'z.gds': 'h9'},
                      golden=dict(BACKED['golden'], **{new: 's9'}),
                      golden_fixtures=dict(BACKED['golden_fixtures'], h9=('z.gds', 'B', 'fired')))
        found = baseline_guard.violations(backed(), head)
        self.assertEqual(len(found), 1, found)
        self.assertIn(f'`{new}`', found[0])

    def test_golden_of_another_rule_does_not_back(self):
        head = backed(golden_fixtures={'h1': ('x.gds', 'B', 'fired'), 'h2': ('y.gds', 'OTHER', 'clean')})
        found = baseline_guard.violations(backed(), head)
        self.assertTrue(any('`y.gds`' in v for v in found), found)

    def test_fixture_deleted_from_verified_rule_fails(self):  # renumbered names do not matter
        found = baseline_guard.violations(backed(), backed(fixtures={'x.gds': 'h1'}))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`y.gds`', found[0])
        self.assertIn('`B`', found[0])

    def test_only_refused_evidence_fails(self):
        base = backed(golden_fixtures={'h1': ('x.gds', 'B', 'fired'), 'h2': ('y.gds', 'B', 'refused')})
        head = backed(fixtures={'y.gds': 'h2'},
                      golden_fixtures={'h1': ('x.gds', 'B', 'fired'), 'h2': ('y.gds', 'B', 'refused')})
        found = baseline_guard.violations(base, head)
        self.assertTrue(any('거부' in v and '`B`' in v for v in found), found)

    def test_problem_already_in_base_is_not_repeated(self):
        base = backed(fixtures={'x.gds': 'h1', 'y.gds': 'h2', 'z.gds': 'h9'})
        self.assertEqual(baseline_guard.violations(base, base), [])

    def test_ported_rule_fixtures_are_free(self):
        base = snap(rules={'B': 'ported'})
        head = snap(rules={'B': 'ported'}, fixtures={'x.gds': 'h1'})
        self.assertEqual(baseline_guard.violations(base, head), [])


class GoldenTests(unittest.TestCase):
    def test_golden_edit_fails(self):  # Review Focus 3
        found = baseline_guard.violations(snap(golden={'g.json': 's1'}), snap(golden={'g.json': 's2'}))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`g.json`', found[0])

    def test_golden_delete_fails(self):
        found = baseline_guard.violations(snap(golden={'g.json': 's1'}), snap())
        self.assertEqual(len(found), 1, found)
        self.assertIn('`g.json`', found[0])

    def test_golden_add_needs_bypass(self):
        found = baseline_guard.violations(snap(golden={'g.json': 's1'}), snap(golden={'g.json': 's1', 'h.json': 's2'}))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`h.json`', found[0])

    def test_every_reliability_file_change_is_listed(self):
        base = snap(files={'t.md': 'a', 'c.md': 'b', 'old.md': 'c'})
        head = snap(files={'t.md': 'a', 'c.md': 'B', 'new.md': 'd'})
        found = baseline_guard.violations(base, head)
        self.assertEqual(len(found), 3, found)
        for path in ('`c.md`', '`old.md`', '`new.md`'):
            self.assertTrue(any(path in v for v in found), (path, found))


class UnverifiedTests(unittest.TestCase):
    def test_new_unverified_item_fails(self):
        found = baseline_guard.violations(snap(unverified={'pex'}), snap(unverified={'pex', 'new'}))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`new`', found[0])

    def test_removed_item_fails_even_with_new_golden(self):
        found = baseline_guard.violations(snap(unverified={'pex'}), snap(unverified=set()))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`pex`', found[0])
        head = snap(unverified=set(), golden={'verification/reliability/golden/pex/summary.json': 's'})
        found = baseline_guard.violations(snap(unverified={'pex'}), head)
        self.assertEqual(len(found), 1, found)
        self.assertIn('`pex`', found[0])

    def test_wider_allows_checks_fails(self):
        base = snap(unverified={'pex'}, unverified_checks={'pex': ('asic-pex',)})
        head = snap(unverified={'pex'}, unverified_checks={'pex': ('asic-pex', 'asic-gate')})
        found = baseline_guard.violations(base, head)
        self.assertEqual(len(found), 1, found)
        self.assertIn('`asic-gate`', found[0])

    def test_first_introduction_has_no_baseline(self):
        base = snap(unverified=None)
        head = snap(unverified={'pex'}, golden={'g.json': 's'}, table={'pex': 'no_evidence', 'drc': 'match'})
        self.assertEqual(baseline_guard.violations(base, head), [])
        # 303bcb6: drc-rules.json existed with every implemented rule ported, before any golden or guard.
        base = snap(rules={'B': 'ported'}, unverified=None, guard={'.github/workflows/asic.yml': 'a'})
        head = backed(table={'drc': 'match'}, guard={'.github/workflows/asic.yml': 'b'})
        self.assertEqual(baseline_guard.violations(base, head), [])


class TableTests(unittest.TestCase):
    def test_match_to_no_evidence_fails(self):
        for verdict in ('no_evidence', 'mismatch'):
            found = baseline_guard.violations(snap(table={'lvs': 'match'}), snap(table={'lvs': verdict}))
            self.assertEqual(len(found), 1, found)
            self.assertIn('`lvs`', found[0])

    def test_new_match_fails_even_with_new_golden(self):
        found = baseline_guard.violations(snap(table={'pex': 'no_evidence'}), snap(table={'pex': 'match'}))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`pex`', found[0])
        head = snap(table={'pex': 'match'}, golden={'verification/reliability/golden/pex/summary.json': 's'})
        found = baseline_guard.violations(snap(table={'pex': 'no_evidence'}), head)
        self.assertEqual(len(found), 1, found)
        self.assertIn('`pex`', found[0])

    def test_removed_row_fails(self):
        found = baseline_guard.violations(snap(table={'lvs': 'no_evidence'}), snap(table={}))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`lvs`', found[0])


class GuardFileTests(unittest.TestCase):
    GUARD = 'scripts/asic/baseline_guard.py'

    def test_guard_edit_or_delete_fails(self):
        base = snap(guard={self.GUARD: 'a', 'scripts/asic/reliability.py': 'r'})
        for head in (snap(guard={self.GUARD: 'b', 'scripts/asic/reliability.py': 'r'}),
                     snap(guard={self.GUARD: 'a'})):
            found = baseline_guard.violations(base, head)
            self.assertEqual(len(found), 1, found)
        self.assertIn('`scripts/asic/reliability.py`', found[0])

    def test_workflow_edit_fails_once_the_guard_exists(self):
        base = snap(guard={self.GUARD: 'a', '.github/workflows/asic.yml': 'w'})
        found = baseline_guard.violations(base, snap(guard={self.GUARD: 'a', '.github/workflows/asic.yml': 'W'}))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`.github/workflows/asic.yml`', found[0])

    def test_new_guard_file_passes(self):
        base = snap(guard={self.GUARD: 'a'})
        head = snap(guard={self.GUARD: 'a', '.github/workflows/baseline.yml': 'w'})
        self.assertEqual(baseline_guard.violations(base, head), [])


class SnapshotTests(unittest.TestCase):
    def test_working_tree_snapshot(self):
        head = baseline_guard.snapshot(ROOT, run_fixtures=True)
        verified = [r for r, s in head['rules'].items() if s == 'verified']
        self.assertEqual(len(verified), 96)
        self.assertEqual(len(head['fixtures']), 451)
        self.assertEqual(set(head['fixture_rules'].values()), set(verified))
        # the mutation golden has no fixtures; the pending golden (unported rules, 857) does
        self.assertEqual(len(head['golden_fixtures']), 451+857)
        self.assertIn('verification/reliability/golden/drc-fixtures-20261128b/golden.json', head['golden'])
        self.assertIn('verification/reliability/golden/drc-mutations-20261128/golden.json', head['golden'])
        self.assertIn('verification/reliability/golden/drc-fixtures-20261128/golden.json', head['golden'])
        self.assertIn('pex', head['unverified'])
        self.assertEqual(head['table']['drc-fixtures'], 'match')
        self.assertIn('verification/reliability/table.md', head['baseline_files'])
        self.assertIn('verification/reliability/golden/drc-fixtures-20261128/golden.json', head['baseline_files'])
        self.assertIn('scripts/asic/baseline_guard.py', head['guard_files'])
        self.assertIn('scripts/asic/reliability.py', head['guard_files'])
        self.assertEqual(baseline_guard.violations(head, head), [])

    def test_first_introduction_against_working_tree(self):
        self.assertEqual(baseline_guard.violations(baseline_guard.empty(), baseline_guard.snapshot(ROOT)), [])
        self.assertEqual(baseline_guard.violations(baseline_guard.empty(),
                                                   baseline_guard.snapshot(ROOT, run_fixtures=True)), [])

    def test_snapshot_at_reads_git(self):
        at = baseline_guard.snapshot_at('HEAD', ROOT, run_fixtures=True)
        self.assertEqual(at['rules'], baseline_guard.snapshot(ROOT)['rules'])
        self.assertEqual(len(at['fixtures']), 451)
        self.assertIsNone(baseline_guard.snapshot_at('HEAD', ROOT)['fixtures'])  # data only by default
        with self.assertRaises(ValueError):
            baseline_guard.snapshot_at('no-such-ref-0019', ROOT)

    def test_cases_run_isolated(self):
        source = 'def cases():\n    return [dict(rule="B", label="a b", shapes=[])]\n'
        fixtures, owners = baseline_guard.fixtures_from_source(source, {'B': 'verified', 'C': 'ported'})
        self.assertEqual(list(fixtures), ['0000-B-a_b.gds'])
        self.assertEqual(owners, {'0000-B-a_b.gds': 'B'})
        self.assertNotIn('cases', vars(baseline_guard))

    def test_cases_with_import_fail_closed(self):
        for source in ('import os\ndef cases():\n    return []\n',
                       'from os import path\ndef cases():\n    return []\n',
                       'def cases():\n    __import__("os")\n    return []\n',
                       'def cases():\n    return [().__class__]\n',
                       'raise SystemExit(0)\ndef cases():\n    return []\n',
                       'def cases():\n    quit()\n',
                       'def cases():\n    exit(0)\n',
                       'if __name__ == "drc_cases_snapshot":\n    pass\ndef cases():\n    return []\n',
                       'def cases():\n    return [x._fields for x in []]\n',
                       FRAME_EXIT, FRAME_PATCH, MATCH_ESCAPE):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'drc_cases.py'):
                baseline_guard.fixtures_from_source(source, {})

    def test_early_exit_while_running_cases_fails_closed(self):  # even past the AST check
        with mock.patch.object(baseline_guard, '_check_cases_source'):
            for source in ('raise SystemExit(0)\n', 'def cases():\n    quit()\n',
                           'def cases():\n    raise KeyboardInterrupt\n', 'x = 1\n'):
                with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'drc_cases.py'):
                    baseline_guard.fixtures_from_source(source, {})

    def test_cases_do_not_see_a_guard_name(self):
        with mock.patch.object(baseline_guard, '_check_cases_source'):
            source = 'def cases():\n    return [dict(rule="B", label=str(globals().get("__name__")), shapes=[])]\n'
            fixtures, _ = baseline_guard.fixtures_from_source(source, {'B': 'verified'})
        self.assertEqual(list(fixtures), ['0000-B-None.gds'])


class DataOnlyTests(unittest.TestCase):
    """baseline-guard runs on pull_request_target: it must never run PR code (Task 7 fix round 1)."""

    def head_root(self, tmp, marker):
        # A head drc_cases.py that would leave a marker file if anything executed it.
        source = f'open({str(marker)!r}, "w").write("ran")\ndef cases():\n    return []\n'
        for relpath, text in ((baseline_guard.CASES, source), (baseline_guard.RULES, '{"rules": []}')):
            (Path(tmp)/relpath).parent.mkdir(parents=True, exist_ok=True)
            (Path(tmp)/relpath).write_text(text, encoding='utf-8')

    def test_default_run_never_executes_head_cases(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as away:
            marker = Path(away)/'marker'
            self.head_root(tmp, marker)
            out = io.StringIO()
            with mock.patch.object(baseline_guard, '_check_cases_source'), \
                    mock.patch.object(baseline_guard, 'snapshot_at', return_value=baseline_guard.empty()), \
                    mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), contextlib.redirect_stdout(out):
                code = baseline_guard.main(['--base', 'origin/main', '--root', tmp])
            # The AST scan (no exec) reports `open` as a violation; the file itself never ran.
            self.assertEqual(code, 1, out.getvalue())
            self.assertIn('`scripts/asic/drc_cases.py`', out.getvalue())
            self.assertFalse(marker.exists())
            # The same head file does run when fixtures are asked for, so the marker would have shown it.
            with mock.patch.object(baseline_guard, '_check_cases_source'), \
                    mock.patch.object(baseline_guard, 'snapshot_at', return_value=baseline_guard.empty()), \
                    mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), contextlib.redirect_stdout(io.StringIO()):
                baseline_guard.main(['--base', 'origin/main', '--root', tmp, '--run-fixtures'])
            self.assertTrue(marker.exists())

    def test_git_refs_are_read_as_data(self):
        with mock.patch.object(baseline_guard, '_run_cases', side_effect=AssertionError('executed PR code')):
            at = baseline_guard.snapshot_at('HEAD', ROOT)
            self.assertIsNone(at['fixtures'])
            self.assertEqual(baseline_guard.violations(at, at), [])
            out = io.StringIO()
            with mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), contextlib.redirect_stdout(out):
                self.assertEqual(baseline_guard.main(['--base', 'HEAD', '--head', 'HEAD']), 0, out.getvalue())

    def test_data_only_skips_fixture_evidence_but_keeps_file_checks(self):
        base = dict(backed(), fixtures=None, fixture_rules=None)
        head = dict(backed(golden={'verification/reliability/golden/g/golden.json': 'edited'}),
                    fixtures=None, fixture_rules=None)
        found = baseline_guard.violations(base, head)
        self.assertEqual(len(found), 1, found)
        self.assertIn('golden.json', found[0])

    def test_match_patterns_are_rejected_before_running(self):  # review PoC reached object.__subclasses__
        with self.assertRaisesRegex(ValueError, 'drc_cases.py'):
            baseline_guard._check_cases_source(MATCH_ESCAPE)
        for source in ('def cases():\n    match 1:\n        case 1:\n            pass\n    return []\n',
                       'def cases():\n    match {}:\n        case {**rest}:\n            pass\n    return []\n'):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'drc_cases.py'):
                baseline_guard._check_cases_source(source)

    def test_codeowners_is_a_guard_file(self):
        self.assertIn('.github/CODEOWNERS', baseline_guard.GUARD)

LOADER = ("def cases():\n    p = __loader__.load_module('posix')\n"
          "    return [{'rule': 'LEAK', 'label': str(p.getpid())}]\n")
# Review probe `casesonly`: a head drc_cases.py that rebinds reliability.case_sha256 for drc_fixture_test.py.
CASESONLY = "def cases():\n    return []\nimport reliability as _r\n_o = _r.case_sha256\n_r.case_sha256 = lambda c: _o(c)\n"
CASES_PATH = 'scripts/asic/drc_cases.py'
PENDING_PATH = 'scripts/asic/drc_cases_pending_c1a.py'


def scan(path, text):
    return baseline_guard.source_problems(path, text.encode('utf-8') if isinstance(text, str) else text)


class SourceScanTests(unittest.TestCase):
    """Fixture sources are parsed with ast only (never compiled or run) and judged as data (fix round 2)."""

    def test_repository_sources_are_clean(self):
        for path in [CASES_PATH] + sorted(p.relative_to(ROOT).as_posix()
                                          for p in (ROOT/'scripts'/'asic').glob('drc_cases_pending*.py')):
            with self.subTest(path=path):
                self.assertEqual(scan(path, (ROOT/path).read_bytes()), [])

    def test_casesonly_probe_is_reported(self):
        found = scan(CASES_PATH, CASESONLY)
        self.assertTrue(found)
        self.assertTrue(any('import' in why for why in found), found)

    def test_strict_rules_for_drc_cases(self):
        for source in ('import math\ndef cases():\n    return []\n', LOADER, MATCH_ESCAPE,
                       'def cases():\n    _x = 1\n    return []\n', 'def cases():\n    return [().__class__]\n',
                       'def cases():\n    setattr(1, "a", 2)\n    return []\n', 'x = [1]\nx.y = 2\n',
                       'def cases():\n    return open("f")\n'):
            with self.subTest(source=source):
                self.assertTrue(scan(CASES_PATH, source), source)

    def test_pending_rules_allow_known_imports_only(self):
        self.assertEqual(scan(PENDING_PATH, 'import math\nimport reliability\nimport drc_cases_pending_c1b\n'
                                            '_n = 1\nif __name__ == "__main__":\n    import collections\n'), [])
        for source in ('import os\n', 'from os import path\n', 'from . import x\n', LOADER,
                       'import reliability\nreliability.case_sha256 = len\n',
                       'import reliability\ndel reliability.case_sha256\n', 'x = vars()\n'):
            with self.subTest(source=source):
                self.assertTrue(scan(PENDING_PATH, source), source)

    def test_unreadable_sources_fail_closed(self):
        for data in (b'def cases(:\n', b'\xff\xfe', b'x = ' + b'(' * 5000 + b')' * 5000 + b'\n',
                     b'x = 1\n' * 200000, b'x = 1\x00\n'):
            with self.subTest(data=data[:20]):
                self.assertTrue(scan(CASES_PATH, data))

    def test_changed_source_is_a_violation_unchanged_is_not(self):
        bad = {CASES_PATH: ('d1', ['3번째 줄: import']), PENDING_PATH: ('d2', [])}
        base = dict(snap(), sources=dict(bad))
        self.assertEqual(baseline_guard.violations(base, dict(snap(), sources=dict(bad))), [])
        head = dict(snap(), sources={CASES_PATH: ('d9', ['3번째 줄: import']), PENDING_PATH: ('d2', [])})
        found = baseline_guard.violations(base, head)
        self.assertEqual(len(found), 1, found)
        self.assertIn(f'`{CASES_PATH}`', found[0])

    def test_casesonly_head_is_reported_without_running_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            for relpath, text in ((CASES_PATH, CASESONLY), (baseline_guard.RULES, '{"rules": []}')):
                (Path(tmp)/relpath).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp)/relpath).write_text(text, encoding='utf-8')
            out = io.StringIO()
            with mock.patch.object(baseline_guard, '_run_cases', side_effect=AssertionError('ran PR code')), \
                    mock.patch.object(baseline_guard, 'snapshot_at', return_value=baseline_guard.empty()), \
                    mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), contextlib.redirect_stdout(out):
                code = baseline_guard.main(['--base', 'origin/main', '--root', tmp])
        self.assertEqual(code, 1, out.getvalue())
        self.assertIn(f'`{CASES_PATH}`', out.getvalue())

    def test_exec_path_rejects_every_underscore_name(self):  # review PoC: __loader__.load_module('posix')
        for source in (LOADER, 'def cases():\n    _x = []\n    return _x\n'):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'drc_cases.py'):
                baseline_guard._check_cases_source(source)


# Round-3 probes (re-review of 306fe8a), as data.
UTF7 = b'# coding: utf-7\ndef cases():\n    return []\n#+AAo-import reliability+AAo-reliability.case+AF8-sha256 = len\n'
UNICODE_ESCAPE = b'# coding: unicode_escape\ndef cases():\n    return []\n# \\nimport reliability\n'
OBJTRICK = ('def cases():\n    return []\n\n\nclass Shapes(list):\n    def __iter__(self):\n        return iter([])\n\n\n'
            'real = cases\n\n\ndef cases():\n    out = real()\n    for case in out:\n'
            '        case["shapes"] = Shapes(case["shapes"])\n    return out\n')
PENDEXEC = ('import math\nimport reliability\n\n\ndef cases():\n    return []\n\n\n'
            'reliability.subprocess.run(["sh", "-c", "echo pwned"])\nreliability.sys.modules["json"] = None\n')
PEND_SETATTR = ("import reliability\nB = reliability.sys.modules['builtins']\nold = reliability.case_sha256\n"
                "B.setattr(reliability, 'case_sha256', lambda case: old(case))\n")


class Round3ScanTests(unittest.TestCase):
    def test_coding_other_than_utf8_is_rejected(self):  # UTF-7 cookie hid code from a str-based scan
        for data in (UTF7, UNICODE_ESCAPE, b'# -*- coding: latin-1 -*-\ndef cases():\n    return []\n'):
            with self.subTest(data=data[:30]):
                self.assertTrue(scan(CASES_PATH, data))
        self.assertEqual(scan(CASES_PATH, b'# coding: utf-8\ndef cases():\n    return []\n'), [])

    def test_strict_rejects_classes_lambdas_scopes_private_defs_and_type(self):
        for source in (OBJTRICK, 'def cases():\n    return list(map(lambda c: c, []))\n',
                       'X = 1\ndef cases():\n    global X\n    return []\n', 'def _h():\n    return []\n',
                       'def cases():\n    return [type(1)]\n', 'def cases():\n    return [[].open]\n'):
            with self.subTest(source=source):
                self.assertTrue(scan(CASES_PATH, source), source)

    def test_pending_modules_are_reached_only_through_allowed_attributes(self):
        for source in (PENDEXEC, PEND_SETATTR, 'import reliability\nr = reliability\n',
                       'import drc_cases_pending_c1b\nx = drc_cases_pending_c1b.reliability\n',
                       'import drc_cases_pending_c1b\nx = (drc_cases_pending_c1b,)\n',
                       'import math\nx = math.pi.real\n'):
            with self.subTest(source=source):
                self.assertTrue(scan(PENDING_PATH, source), source)
        ok = ('import math\nimport collections\nimport reliability\nimport drc_cases_pending_c1b\n'
              'a = math.floor(1.5) + math.sqrt(4)\nc = collections.Counter()\n'
              'h = reliability.case_sha256({})\nn = reliability.fixture_name(0, {})\n'
              'r = drc_cases_pending_c1b.records\n'
              'for group, make in (("g", drc_cases_pending_c1b.cases),):\n    make()\n')
        self.assertEqual(scan(PENDING_PATH, ok), [])

    def test_pending_imports_must_be_pending_files_of_the_same_tree(self):
        source = b'import drc_cases_pending_zz\n'
        self.assertTrue(baseline_guard.source_problems(PENDING_PATH, source, {'drc_cases_pending_c1a'}))
        self.assertEqual(baseline_guard.source_problems(PENDING_PATH, b'import drc_cases_pending_c1b\n',
                                                        {'drc_cases_pending_c1a', 'drc_cases_pending_c1b'}), [])


# Round-4 probes (re-review of 9fb2426).
HELPBYPASS = 'def cases():\n    return []\n\n\nhelp("drc_zz")\n'  # help -> pydoc.locate -> __import__
PENDCHAIN = ('import math\n\n\ndef cases():\n    return []\n\n\nimport reliability as helper\n'
             'import drc_cases_pending_c1c as me\nme.helper.ROOT.joinpath("g4-pending-wrote-this").write_text("x")\n'
             'me.helper.VERDICT_KO.update(mismatch="x")\n')
PENDING_C1C = 'scripts/asic/drc_cases_pending_c1c.py'
TREE = {'drc_cases_pending_c1a', 'drc_cases_pending_c1b', 'drc_cases_pending_c1c'}


class Round4ScanTests(unittest.TestCase):
    def test_helpbypass_is_reported_in_both_modes(self):
        self.assertTrue(scan(CASES_PATH, HELPBYPASS))
        self.assertTrue(scan(PENDING_PATH, HELPBYPASS))

    def test_pendchain_is_reported(self):
        found = baseline_guard.source_problems(PENDING_C1C, PENDCHAIN.encode('utf-8'), TREE)
        self.assertTrue(any('as' in why for why in found), found)
        self.assertTrue(any('자기 자신' in why for why in found), found)

    def test_names_outside_the_allow_list_are_reported(self):
        for name in ('help', 'breakpoint', 'getattr', 'memoryview', 'object', 'type', 'super', 'iter', 'next',
                     'classmethod', 'staticmethod', 'property', 'license', 'copyright', 'credits'):
            with self.subTest(name=name):
                self.assertTrue(scan(CASES_PATH, f'def cases():\n    return [{name}]\n'))
                self.assertTrue(scan(PENDING_PATH, f'x = {name}\n'))
        self.assertTrue(scan(CASES_PATH, 'def cases():\n    return [undefined_name]\n'))

    def test_binding_a_builtin_name_does_not_make_it_allowed(self):  # scope-insensitive binding check
        self.assertTrue(scan(PENDING_PATH, 'def f(help):\n    return help\nhelp("drc_zz")\n'))
        self.assertTrue(scan(PENDING_PATH, 'help = 1\n'))

    def test_allowed_names_and_local_bindings_pass(self):
        self.assertEqual(scan(CASES_PATH, 'def cases():\n    out = []\n    for i in range(len(out)):\n'
                                          '        out.append(dict(rule=str(i), shapes=list(), fail=round(1.5) > 1))\n'
                                          '    return [c for c in out if isinstance(c, dict)]\n'), [])

    def test_attributes_on_pending_modules_are_limited(self):
        for attr in ('cases', 'records', 'cases_with_meta'):
            with self.subTest(attr=attr):
                self.assertEqual(baseline_guard.source_problems(
                    PENDING_PATH, f'import drc_cases_pending_c1b\nx = drc_cases_pending_c1b.{attr}\n'.encode(),
                    TREE), [])
        for attr in ('helper', 'DECK_LINE', 'json'):
            with self.subTest(attr=attr):
                self.assertTrue(baseline_guard.source_problems(
                    PENDING_PATH, f'import drc_cases_pending_c1b\nx = drc_cases_pending_c1b.{attr}\n'.encode(),
                    TREE))

    def test_no_import_aliases_in_pending_files(self):
        for source in ('import math as m\n', 'import reliability as helper\n', 'import drc_cases_pending_c1b as b\n'):
            with self.subTest(source=source):
                self.assertTrue(baseline_guard.source_problems(PENDING_PATH, source.encode(), TREE))

    def test_non_regular_message_has_one_full_stop(self):
        head = baseline_guard._build(lambda rel: None, [], entries={'drc_cases.py': '120000'})
        found = baseline_guard.violations(baseline_guard.empty(), head)
        self.assertTrue(found)
        self.assertFalse(any('..' in text for text in found), found)


def git(repo, *args, data=None):
    done = subprocess.run(['git', '-C', str(repo), *args], input=data, capture_output=True, check=True)
    return done.stdout.decode('utf-8').strip()


class TreeTests(unittest.TestCase):
    """New entries under scripts/asic that change what `import` finds are violations (git ls-tree, no checkout)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.tmp.name)
        git(cls.repo, 'init', '-q')
        git(cls.repo, 'config', 'user.name', 't')
        git(cls.repo, 'config', 'user.email', 't@t')
        files = {CASES_PATH: (ROOT/CASES_PATH).read_bytes(), PENDING_PATH: b'import math\n',
                 'scripts/asic/drc_cases_pending.py': b'import drc_cases_pending_c1a\n',
                 baseline_guard.RULES: b'{"rules": []}'}
        for path, data in files.items():
            blob = git(cls.repo, 'hash-object', '-w', '--stdin', data=data)
            git(cls.repo, 'update-index', '--add', '--cacheinfo', f'100644,{blob},{path}')
        cls.base = git(cls.repo, 'commit-tree', git(cls.repo, 'write-tree'), '-m', 'base')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def head(self, *entries):
        """Commit on top of base with extra (mode, path, bytes) entries; returns its sha."""
        git(self.repo, 'read-tree', self.base)
        for mode, path, data in entries:
            blob = git(self.repo, 'hash-object', '-w', '--stdin', data=data)
            git(self.repo, 'update-index', '--add', '--cacheinfo', f'{mode},{blob},{path}')
        return git(self.repo, 'commit-tree', git(self.repo, 'write-tree'), '-p', self.base, '-m', 'head')

    def found(self, *entries):
        base = baseline_guard.snapshot_at(self.base, self.repo)
        return baseline_guard.violations(base, baseline_guard.snapshot_at(self.head(*entries), self.repo))

    def test_base_against_itself_is_clean(self):
        self.assertEqual(self.found(), [])

    def test_new_import_shadows_are_violations(self):
        evil = b'import reliability\nreliability.case_sha256 = len\n'
        for name, entries in (
                ('symlink', [('120000', CASES_PATH, b'evil.py'), ('100644', 'scripts/asic/evil.py', evil)]),
                ('pkgshadow', [('100644', 'scripts/asic/drc_cases/__init__.py', evil)]),
                ('pendpkg', [('100644', 'scripts/asic/drc_cases_pending/__init__.py', evil)]),
                ('stdlib', [('100644', 'scripts/asic/hashlib.py', b'raise SystemExit("shadow")')]),
                ('pya', [('100644', 'scripts/asic/pya.py', b'x = 1\n')]),
                ('pyc', [('100644', 'scripts/asic/drc_cases.cpython-312.pyc', b'\x00')]),
                ('so', [('100644', 'scripts/asic/drc_cases.so', b'\x00')]),
                ('pycache', [('100644', 'scripts/asic/__pycache__/x.pyc', b'\x00')]),
                ('pendimp', [('100644', PENDING_PATH, b'import math\nimport drc_cases_pending_zz\n'),
                             ('100644', 'scripts/asic/drc_cases_pending_zz/__init__.py', evil)])):
            with self.subTest(name=name):
                self.assertTrue(self.found(*entries), name)

    def test_ordinary_new_helper_is_allowed(self):
        self.assertEqual(self.found(('100644', 'scripts/asic/new_helper.py', b'x = 1\n')), [])


class NormaliseTests(unittest.TestCase):
    """Fixture builders see exactly what case_sha256 hashed (json round trip), so subclasses cannot lie."""

    def test_fixture_test_normalises_cases(self):
        text = (ROOT/'scripts'/'asic'/'drc_fixture_test.py').read_text(encoding='utf-8')
        self.assertIn('json.loads(json.dumps(cases()))', text)

    def test_pending_records_normalise_cases(self):
        sys.path.insert(0, str(ROOT/'scripts'/'asic'))
        import drc_cases_pending
        import reliability

        class Lying(list):
            def __iter__(self):
                return iter([])
        real = drc_cases_pending.drc_cases_pending_c1a.cases
        with mock.patch.object(drc_cases_pending.drc_cases_pending_c1a, 'cases',
                               lambda: [dict(case, shapes=Lying(case['shapes'])) for case in real()]):
            records = drc_cases_pending.records()
        lying = [dict(case, shapes=Lying(case['shapes'])) for case in real()]
        got = [r for r in records if r['group'] == 'C1a']
        self.assertTrue(all(type(r['case']['shapes']) is list for r in got))
        # Whatever json saw is what the record holds and what was hashed: hash and GDS builder agree.
        for record, case in zip(got, lying):
            self.assertEqual(list(iter(record['case']['shapes'])), json.loads(json.dumps(case['shapes'])))
            self.assertEqual(record['run_case_sha256'], reliability.case_sha256(case))


class DuplicateRuleTests(unittest.TestCase):
    def rules_json(self, *entries):
        return json.dumps({'rules': [{'id': rid, 'implementation': impl, 'golden_compared': gc}
                                     for rid, impl, gc in entries]}).encode('utf-8')

    def test_duplicate_rule_id_is_a_violation(self):  # review probe `dupid`
        data = self.rules_json(('A', 'unported', False), ('B', 'geometry_port', True), ('A', 'geometry_port', True))
        files = {baseline_guard.RULES: data}
        head = baseline_guard._build(lambda rel: files.get(rel), [])
        found = baseline_guard.violations(baseline_guard.empty(), head)
        self.assertTrue(any('`A`' in v and '두 번' in v for v in found), found)

    def test_reliability_rejects_duplicate_ids(self):
        sys.path.insert(0, str(ROOT/'scripts'/'asic'))
        import reliability
        catalog = json.loads(self.rules_json(('A', 'geometry_port', True), ('A', 'unported', False)))
        with self.assertRaisesRegex(ValueError, 'A'):
            reliability.verified_rules(catalog)


class OutputTests(unittest.TestCase):
    """Names come from the PR; they must not start workflow commands or break the report (fix round 2)."""

    def test_newlines_and_backticks_in_names_are_escaped(self):
        path = 'verification/reliability/a\n::set-output name=result::clean\n::error::x`y'
        found = baseline_guard.violations(snap(golden={'verification/reliability/golden/g/golden.json': 's'}),
                                          snap(golden={'verification/reliability/golden/g/golden.json': 's'},
                                               files={path: 'h'}))
        text = baseline_guard.report('base', found)
        self.assertTrue(found)
        self.assertFalse([line for line in text.splitlines() if line.lstrip().startswith('::')], text)
        self.assertNotIn('x`y', text)
        item = 'z\n::set-output name=result::clean'
        found = baseline_guard.violations(snap(unverified=['a']), snap(unverified=['a', item]))
        self.assertTrue(found)
        self.assertNotIn('\n', ''.join(found))


class WorkflowTextTests(unittest.TestCase):
    """baseline.yml (pull_request_target) must never run PR code; pin the parts that guarantee it."""

    def setUp(self):
        self.text = (ROOT/'.github'/'workflows'/'baseline.yml').read_text(encoding='utf-8')

    def run_blocks(self):
        blocks, current, indent = [], None, None
        for line in self.text.splitlines():
            stripped = line.lstrip()
            if current is not None:
                if stripped and len(line) - len(stripped) <= indent:
                    blocks.append('\n'.join(current))
                    current = None
                else:
                    current.append(line)
                    continue
            if stripped.startswith('run:'):
                indent = len(line) - len(stripped)
                current = [stripped[4:]]
        if current is not None:
            blocks.append('\n'.join(current))
        return blocks

    def test_guard_code_comes_from_the_workflow_commit(self):
        self.assertIn('pull_request_target:', self.text)
        self.assertIn('git -C "$repo" show "$GITHUB_SHA:scripts/asic/baseline_guard.py"', self.text)
        self.assertIn('git -C "$repo" show "$GITHUB_SHA:scripts/asic/reliability.py"', self.text)
        self.assertNotIn('python scripts/', self.text)
        self.assertNotIn('cp scripts/', self.text)
        self.assertNotIn('actions/cache', self.text)
        self.assertIn('::stop-commands::', self.text)

    def test_pr_tree_is_never_the_working_directory_or_on_sys_path(self):  # round 3: secrets.py in the PR
        self.assertIn('path: head', self.text)
        self.assertNotIn('working-directory: head', self.text)
        self.assertNotIn('cd "$GITHUB_WORKSPACE"', self.text)
        for block in self.run_blocks():
            for line in block.splitlines():
                code = line.split('#', 1)[0]
                if re.search(r'(^|[^\w-])python3?( |$)', code):
                    self.assertIn('python -I -E -s', code, line)
        self.assertIn('od -An -N16 -tx1 /dev/urandom', self.text)
        self.assertNotIn('import secrets', self.text)

    def test_exact_guard_invocation(self):  # round 4
        self.assertIn('working-directory: ${{ runner.temp }}', self.text)
        self.assertIn('repo="$GITHUB_WORKSPACE/head"', self.text)
        self.assertIn('python -I -E -s "$guard/baseline_guard.py" --base "$BASE_SHA" --head "$HEAD_SHA" --root "$repo"',
                      self.text)
        runs = '\n'.join(self.run_blocks())
        self.assertEqual(len(re.findall(r'\bpython', runs)), 1, runs)  # exactly the guard command
        for pattern in (r'python3', r'\$pythonLocation', r'which\s+python', r'\buv\s+run', r'\bpip\b',
                        r'cd\s+"?\$\{?GITHUB_WORKSPACE', r'cd\s+"?\$repo', r'cd\s+"?head'):
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, runs), pattern)
        for line in self.text.splitlines():
            if 'working-directory:' in line:
                self.assertEqual(line.strip(), 'working-directory: ${{ runner.temp }}', line)

    def test_run_blocks_take_event_values_only_through_env(self):
        blocks = self.run_blocks()
        self.assertGreaterEqual(len(blocks), 2)
        for block in blocks:
            self.assertNotIn('${{', block)


class CliTests(unittest.TestCase):
    def run_main(self, found):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp)/'summary.md'
            with mock.patch.object(baseline_guard, 'snapshot_at', return_value=snap()), \
                 mock.patch.object(baseline_guard, 'snapshot', return_value=snap()), \
                 mock.patch.object(baseline_guard, 'violations', return_value=found), \
                 mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': str(summary)}), \
                 contextlib.redirect_stdout(out):
                code = baseline_guard.main(['--base', 'origin/main'])
            return code, out.getvalue(), summary.read_text(encoding='utf-8')

    def test_violations_exit_one_with_bypass_line(self):
        code, text, summary = self.run_main(['규칙 `B` 상태가 내려갔습니다.'])
        self.assertEqual(code, 1)
        self.assertEqual(text.rstrip('\n').splitlines()[-1], LAST_LINE)
        self.assertIn('규칙 `B`', summary)
        self.assertEqual(summary.rstrip('\n').splitlines()[-1], LAST_LINE)

    def test_clean_exit_zero(self):
        code, text, summary = self.run_main([])
        self.assertEqual(code, 0)
        self.assertNotIn(LAST_LINE, text)
        self.assertIn('origin/main', summary)

    def test_snapshot_error_fails_closed(self):
        out = io.StringIO()
        with mock.patch.object(baseline_guard, 'snapshot_at', side_effect=ValueError('가짜 오류')), \
             mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), contextlib.redirect_stdout(out):
            self.assertEqual(baseline_guard.main(['--base', 'origin/main']), 1)
        self.assertIn('가짜 오류', out.getvalue())

    def test_early_exit_in_head_cases_exits_one(self):
        for source, checked in (('raise SystemExit(0)\ndef cases():\n    return []\n', True),
                                ('def cases():\n    quit()\n', True),
                                ('raise SystemExit(0)\n', False), ('def cases():\n    quit()\n', False)):
            with self.subTest(source=source, checked=checked), tempfile.TemporaryDirectory() as tmp:
                for relpath, text in ((baseline_guard.CASES, source), (baseline_guard.RULES, '{"rules": []}')):
                    (Path(tmp)/relpath).parent.mkdir(parents=True, exist_ok=True)
                    (Path(tmp)/relpath).write_text(text, encoding='utf-8')
                out = io.StringIO()
                skip = (contextlib.nullcontext() if checked
                        else mock.patch.object(baseline_guard, '_check_cases_source'))
                with skip, mock.patch.object(baseline_guard, 'snapshot_at', return_value=baseline_guard.empty()), \
                     mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), contextlib.redirect_stdout(out):
                    code = baseline_guard.main(['--base', 'origin/main', '--root', tmp, '--run-fixtures'])
                self.assertEqual(code, 1, out.getvalue())
                self.assertIn('실행 실패', out.getvalue())

    def run_head_cases(self, source, base, check=False):
        """main() with head = a temp root holding only drc_cases.py and an empty drc-rules.json."""
        with tempfile.TemporaryDirectory() as tmp:
            for relpath, text in ((baseline_guard.CASES, source), (baseline_guard.RULES, '{"rules": []}')):
                (Path(tmp)/relpath).parent.mkdir(parents=True, exist_ok=True)
                (Path(tmp)/relpath).write_text(text, encoding='utf-8')
            out = io.StringIO()
            skip = (contextlib.nullcontext() if check
                    else mock.patch.object(baseline_guard, '_check_cases_source'))
            with skip, mock.patch.object(baseline_guard, 'snapshot_at', return_value=base), \
                 mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), contextlib.redirect_stdout(out):
                code = baseline_guard.main(['--base', 'origin/main', '--root', tmp, '--run-fixtures'])
        return code, out.getvalue()

    def test_frame_walk_exit_fails_closed(self):  # os._exit(0) ends only the child
        for check in (True, False):
            with self.subTest(check=check):
                code, text = self.run_head_cases(FRAME_EXIT, baseline_guard.empty(), check)
                self.assertEqual(code, 1, text)
                self.assertIn('실행 실패', text)

    def test_frame_walk_patch_cannot_reach_the_guard(self):
        real = baseline_guard.violations
        base = snap(golden={'verification/reliability/golden/g/golden.json': 's'})
        code, text = self.run_head_cases(FRAME_PATCH, base)
        self.assertIs(baseline_guard.violations, real)
        self.assertEqual(code, 1, text)
        self.assertIn('`verification/reliability/golden/g/golden.json`', text)
        self.assertEqual(text.rstrip('\n').splitlines()[-1], LAST_LINE)

    def test_hanging_cases_time_out(self):
        with mock.patch.object(baseline_guard, 'CHILD_TIMEOUT', 2):
            code, text = self.run_head_cases('def cases():\n    while True:\n        pass\n', baseline_guard.empty())
        self.assertEqual(code, 1, text)
        self.assertIn('시간 초과', text)

    def test_child_must_print_sentinel_and_json(self):
        with mock.patch.object(baseline_guard, '_check_cases_source'):
            for source in ('def cases():\n    print("[]")\n    raise SystemExit(0)\n',
                           'def cases():\n    return [1]\n',
                           'import os\ndef cases():\n    os._exit(0)\n'):
                rows = None
                with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'drc_cases.py'):
                    rows = baseline_guard.fixtures_from_source(source, {})
                self.assertIsNone(rows)

    def test_any_snapshot_exception_fails_closed(self):
        for error in (SystemExit(0), RuntimeError('boom'), KeyError('rules')):
            out = io.StringIO()
            with self.subTest(error=error), mock.patch.object(baseline_guard, 'snapshot', side_effect=error), \
                 mock.patch.object(baseline_guard, 'snapshot_at', return_value=baseline_guard.empty()), \
                 mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), contextlib.redirect_stdout(out):
                self.assertEqual(baseline_guard.main(['--base', 'origin/main']), 1)
            self.assertIn('실행 실패', out.getvalue())

    def test_runs_from_a_copy_with_root(self):  # Task 7 runs the base ref's guard from a temp directory
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('baseline_guard.py', 'reliability.py'):
                shutil.copy(ROOT/'scripts'/'asic'/name, tmp)
            env = dict(os.environ, GITHUB_STEP_SUMMARY='', PYTHONIOENCODING='utf-8')
            done = subprocess.run([sys.executable, '-X', 'utf8', '-I', '-E', '-s', str(Path(tmp)/'baseline_guard.py'), '--base', 'HEAD',
                                   '--root', str(ROOT)], cwd=tmp, env=env, capture_output=True, text=True,
                                  encoding='utf-8')
        # The working tree may hold uncommitted edits; the copy must judge exactly as the module does.
        expected = baseline_guard.violations(baseline_guard.snapshot_at('HEAD', ROOT), baseline_guard.snapshot(ROOT))
        self.assertEqual(done.returncode, 1 if expected else 0, done.stdout+done.stderr)
        self.assertEqual(done.stdout, baseline_guard.report('HEAD', expected))

    def test_self_compare_against_head(self):
        at = baseline_guard.snapshot_at('HEAD', ROOT)
        out = io.StringIO()
        with mock.patch.object(baseline_guard, 'snapshot', return_value=at), \
             mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), contextlib.redirect_stdout(out):
            self.assertEqual(baseline_guard.main(['--base', 'HEAD']), 0, out.getvalue())


if __name__ == '__main__':
    unittest.main()
