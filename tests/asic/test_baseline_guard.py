"""Baseline guard: verification baselines only move forward (SPEC 0019)."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'/'asic'))
import baseline_guard

LAST_LINE = '기준 파일 변경은 도재겸이 근거를 확인한 뒤 PR에서 우회 머지합니다(SPEC 0019).'


def snap(rules=None, unverified=(), golden=None, fixtures=None, rule='B', golden_fixtures=None,
         table=None, unverified_checks=None):
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
            'table': table}


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

    def test_fixture_added_with_new_golden_passes(self):
        new = 'verification/reliability/golden/g2/golden.json'
        head = backed(fixtures={'x.gds': 'h1', 'y.gds': 'h2', 'z.gds': 'h9'},
                      golden=dict(BACKED['golden'], **{new: 's9'}),
                      golden_fixtures=dict(BACKED['golden_fixtures'], h9=('z.gds', 'B', 'fired')))
        self.assertEqual(baseline_guard.violations(backed(), head), [])

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

    def test_golden_add_passes(self):
        self.assertEqual(baseline_guard.violations(snap(golden={'g.json': 's1'}),
                                                   snap(golden={'g.json': 's1', 'h.json': 's2'})), [])


class UnverifiedTests(unittest.TestCase):
    def test_new_unverified_item_fails(self):
        found = baseline_guard.violations(snap(unverified={'pex'}), snap(unverified={'pex', 'new'}))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`new`', found[0])

    def test_removed_item_needs_evidence(self):
        found = baseline_guard.violations(snap(unverified={'pex'}), snap(unverified=set()))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`pex`', found[0])
        head = snap(unverified=set(), golden={'verification/reliability/golden/pex/summary.json': 's'})
        self.assertEqual(baseline_guard.violations(snap(unverified={'pex'}), head), [])

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


class TableTests(unittest.TestCase):
    def test_match_to_no_evidence_fails(self):
        for verdict in ('no_evidence', 'mismatch'):
            found = baseline_guard.violations(snap(table={'lvs': 'match'}), snap(table={'lvs': verdict}))
            self.assertEqual(len(found), 1, found)
            self.assertIn('`lvs`', found[0])

    def test_new_match_needs_new_golden(self):
        found = baseline_guard.violations(snap(table={'pex': 'no_evidence'}), snap(table={'pex': 'match'}))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`pex`', found[0])
        head = snap(table={'pex': 'match'}, golden={'verification/reliability/golden/pex/summary.json': 's'})
        self.assertEqual(baseline_guard.violations(snap(table={'pex': 'no_evidence'}), head), [])

    def test_removed_row_fails(self):
        found = baseline_guard.violations(snap(table={'lvs': 'no_evidence'}), snap(table={}))
        self.assertEqual(len(found), 1, found)
        self.assertIn('`lvs`', found[0])


class SnapshotTests(unittest.TestCase):
    def test_working_tree_snapshot(self):
        head = baseline_guard.snapshot(ROOT)
        verified = [r for r, s in head['rules'].items() if s == 'verified']
        self.assertEqual(len(verified), 96)
        self.assertEqual(len(head['fixtures']), 427)
        self.assertEqual(set(head['fixture_rules'].values()), set(verified))
        self.assertEqual(len(head['golden_fixtures']), 427)
        self.assertIn('verification/reliability/golden/drc-fixtures-20261128/golden.json', head['golden'])
        self.assertIn('pex', head['unverified'])
        self.assertEqual(head['table']['drc-fixtures'], 'match')
        self.assertEqual(baseline_guard.violations(head, head), [])

    def test_first_introduction_against_working_tree(self):
        self.assertEqual(baseline_guard.violations(baseline_guard.empty(), baseline_guard.snapshot(ROOT)), [])

    def test_snapshot_at_reads_git(self):
        at = baseline_guard.snapshot_at('HEAD', ROOT)
        self.assertEqual(at['rules'], baseline_guard.snapshot(ROOT)['rules'])
        self.assertEqual(len(at['fixtures']), 427)
        with self.assertRaises(ValueError):
            baseline_guard.snapshot_at('no-such-ref-0019', ROOT)

    def test_cases_run_isolated(self):
        source = 'def cases():\n    return [dict(rule="B", label="a b", shapes=[])]\n'
        fixtures, owners = baseline_guard.fixtures_from_source(source, {'B': 'verified', 'C': 'ported'})
        self.assertEqual(list(fixtures), ['0000-B-a_b.gds'])
        self.assertEqual(owners, {'0000-B-a_b.gds': 'B'})
        self.assertNotIn('cases', vars(baseline_guard))


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

    def test_self_compare_against_head(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), contextlib.redirect_stdout(out):
            self.assertEqual(baseline_guard.main(['--base', 'HEAD']), 0)


if __name__ == '__main__':
    unittest.main()
