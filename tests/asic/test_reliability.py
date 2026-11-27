"""Golden results are keyed by the fixture definition, not by GDS bytes."""
import contextlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'/'asic'))
import reliability
import drc_catalog
from drc_cases import cases

GOLDEN_DIR = ROOT/'verification/reliability/golden/drc-fixtures-20261128'
GOLDEN = GOLDEN_DIR/'golden.json'
RELIABILITY = ROOT/'verification/reliability'
RULES_JSON = ROOT/'verification/asic/drc-rules.json'
SERVER_TRACE = re.compile(r'polaris|snu\.|\d+\.\d+\.\d+\.\d+|/tmp|/home|/var/|authorized_keys', re.I)
META = dict(calibre_version='v2023.4_17.10', deck_sha256=drc_catalog.SOURCE_SHA,
            fixture_tarball_sha256='a125b25350f984c46dde3d9c73f172bd085508ac540eddb35b86709e18a394d8',
            generator_commit='303bcb6', run_date='2026-11-28')


class CaseHashTests(unittest.TestCase):
    def test_case_sha_is_stable_and_order_free(self):
        a = {'rule': '8.MET1.W', 'label': 'x', 'dbu': 0.001, 'hierarchy': False, 'shapes': [[[8, 0], [0, 0, 1, 1]]]}
        b = dict(reversed(list(a.items())))
        self.assertEqual(reliability.case_sha256(a), reliability.case_sha256(b))
        self.assertEqual(len(reliability.case_sha256(a)), 64)

    def test_every_fixture_case_hashes(self):
        hashes = [reliability.case_sha256(c) for c in cases()]
        self.assertEqual(len(hashes), 427)


def golden(*fixtures):
    return {'fixtures': [dict(zip(('gds', 'rule', 'case_sha256', 'calibre'), f[:4]), **(f[4] if len(f) > 4 else {}))
                         for f in fixtures]}


def selftest(*records):
    return {'records': [dict(zip(('gds', 'rule', 'errors', 'case_sha256'), r)) for r in records]}


class CompareTests(unittest.TestCase):
    def test_compare_verdicts(self):
        g = golden(('a.gds', 'R', 'h1', 'fired'), ('b.gds', 'R', 'h2', 'clean'),
                   ('c.gds', 'R', 'h3', 'refused', {'refused_reason': 'dbu'}))
        s = selftest(('a.gds', 'R', 4, 'h1'), ('b.gds', 'R', 0, 'h2'), ('c.gds', 'R', 4, 'h3'))
        r = reliability.compare(g, s)
        self.assertEqual([f['verdict'] for f in r['fixtures']], ['match', 'match', 'excluded'])
        self.assertEqual(r['fixtures'][2]['reason'], 'dbu')
        self.assertEqual(r['rules']['R'], 'match')

    def test_count_difference_is_still_match(self):  # 0242: KLayout 4, Calibre 1
        g = golden(('a.gds', 'R', 'h1', 'fired', {'target_count': 1}))
        r = reliability.compare(g, selftest(('a.gds', 'R', 4, 'h1')))
        self.assertEqual(r['fixtures'][0]['verdict'], 'match')
        self.assertEqual(r['rules']['R'], 'match')

    def test_changed_definition_has_no_golden(self):
        g = golden(('a.gds', 'R', 'h1', 'fired'), ('b.gds', 'R', 'h2', 'clean'))
        r = reliability.compare(g, selftest(('a.gds', 'R', 4, 'h9'), ('b.gds', 'R', 0, 'h2')))
        self.assertEqual([f['verdict'] for f in r['fixtures']], ['no_golden', 'match'])
        self.assertEqual(r['rules']['R'], 'no_golden')

    def test_flip_is_mismatch(self):
        g = golden(('a.gds', 'R', 'h1', 'fired'), ('b.gds', 'R', 'h2', 'clean'), ('c.gds', 'R', 'h3', 'fired'))
        r = reliability.compare(g, selftest(('a.gds', 'R', 0, 'h1'), ('b.gds', 'R', 0, 'h2'), ('c.gds', 'R', 1, 'h9')))
        self.assertEqual([f['verdict'] for f in r['fixtures']], ['mismatch', 'match', 'no_golden'])
        self.assertEqual(r['rules']['R'], 'mismatch')

    def test_klayout_input_error_against_a_calibre_verdict_is_mismatch(self):
        g = golden(('a.gds', 'R', 'h1', 'clean'))
        s = {'records': [{'gds': 'a.gds', 'rule': 'R', 'case_sha256': 'h1', 'error': 'dbu'}]}
        self.assertEqual(reliability.compare(g, s)['fixtures'][0]['verdict'], 'mismatch')

    def test_all_excluded_rule_is_not_evidence(self):
        g = golden(('c.gds', 'R', 'h3', 'refused', {'refused_reason': 'dbu'}))
        r = reliability.compare(g, selftest(('c.gds', 'R', 4, 'h3')))
        self.assertEqual(r['fixtures'][0]['verdict'], 'excluded')
        self.assertEqual(r['rules']['R'], 'no_golden')

    def test_rules_are_judged_separately(self):
        g = golden(('a.gds', 'R', 'h1', 'fired'), ('b.gds', 'S', 'h2', 'clean'))
        r = reliability.compare(g, selftest(('a.gds', 'R', 1, 'h1'), ('b.gds', 'S', 3, 'h2')))
        self.assertEqual(r['rules'], {'R': 'match', 'S': 'mismatch'})


class ImportTests(unittest.TestCase):
    def batch(self, tmp, rows, records, logs=None):
        tmp = Path(tmp)
        (tmp/'counts.csv').write_text(
            'gds,target_rule,target_rule_count,other_rules_fired,status,calibre_exit,run_ms\n'+''.join(r+'\n' for r in rows))
        (tmp/'selftest.json').write_text(json.dumps({'records': records}))
        (tmp/'results').mkdir()
        for name, text in (logs or {}).items():
            (tmp/'results'/name).write_text(text)
        return tmp/'counts.csv', tmp/'selftest.json'

    def test_import_sets_verdicts_reason_and_other_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            counts, st = self.batch(tmp, [
                'x-fire.gds,R,1,1.PWL.bad1:1;OFFGRID_PWELL:4,ok,0,600',
                'x-clean.gds,R,0,1.PWL.bad1:1,ok,0,600',
                'x-dbu.gds,R,,,calibre_error,4,600'],
                [{'gds': 'x-fire.gds', 'rule': 'R', 'errors': 4, 'case_sha256': 'h1'},
                 {'gds': 'x-clean.gds', 'rule': 'R', 'errors': 0, 'case_sha256': 'h2'},
                 {'gds': 'x-dbu.gds', 'rule': 'R', 'error': 'dbu', 'case_sha256': 'h3'}],
                {'x-dbu.calibre.log': 'DATABASE PRECISION: 0.003\nERROR: Rule file precision 1000 is not consistent with database precision 333.333333333 in input file fixture.gds.\nERROR: later\n'})
            g = reliability.import_calibre(counts, st, META)
        self.assertEqual(g['meta']['deck_sha256'], drc_catalog.SOURCE_SHA)
        fire, clean, dbu = g['fixtures']
        self.assertEqual((fire['calibre'], fire['target_count'], fire['case_sha256']), ('fired', 1, 'h1'))
        self.assertEqual(fire['other_rules'], {'1.PWL.bad1': 1, 'OFFGRID_PWELL': 4})
        self.assertIsNone(fire['refused_reason'])
        self.assertEqual((clean['calibre'], clean['target_count']), ('clean', 0))
        self.assertEqual((dbu['calibre'], dbu['target_count'], dbu['other_rules']), ('refused', None, {}))
        self.assertTrue(dbu['refused_reason'].startswith('Rule file precision 1000 is not consistent with database precision'))

    def test_import_hashes_old_selftest_from_fixture_names(self):
        first = cases()[0]
        name = reliability.fixture_name(0, first)+'.gds'
        record = {k: v for k, v in first.items() if k != 'shapes'}
        with tempfile.TemporaryDirectory() as tmp:
            counts, st = self.batch(tmp, [f'{name},{first["rule"]},0,,ok,0,1'], [dict(record, gds=name, errors=0)])
            g = reliability.import_calibre(counts, st, META)
        self.assertEqual(g['fixtures'][0]['case_sha256'], reliability.case_sha256(first))
        self.assertEqual(g['meta']['case_sha256_from'], 'drc_cases')

    def test_import_rejects_unknown_or_unmatched_fixtures(self):
        bad = [
            (['ghost.gds,R,0,,ok,0,1'], [{'gds': 'ghost.gds', 'rule': 'R', 'errors': 0}]),  # no hash, no such case
            (['a.gds,R,0,,ok,0,1'], [{'gds': 'a.gds', 'rule': 'S', 'errors': 0, 'case_sha256': 'h'}]),  # rule differs
            (['a.gds,R,0,,ok,0,1'], [{'gds': 'a.gds', 'rule': 'R', 'errors': 0, 'case_sha256': 'h'},
                                     {'gds': 'b.gds', 'rule': 'R', 'errors': 0, 'case_sha256': 'i'}]),  # b has no row
            (['a.gds,R,,,calibre_error,4,1'], [{'gds': 'a.gds', 'rule': 'R', 'case_sha256': 'h'}]),  # no log
        ]
        for rows, records in bad:
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as tmp:
                counts, st = self.batch(tmp, rows, records)
                with self.assertRaises(ValueError):
                    reliability.import_calibre(counts, st, META)

    def test_import_rejects_another_deck(self):
        with tempfile.TemporaryDirectory() as tmp:
            counts, st = self.batch(tmp, ['a.gds,R,0,,ok,0,1'], [{'gds': 'a.gds', 'rule': 'R', 'errors': 0, 'case_sha256': 'h'}])
            with self.assertRaises(ValueError):
                reliability.import_calibre(counts, st, dict(META, deck_sha256='0'*64))

    def test_import_cli_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            counts, st = self.batch(tmp, ['a.gds,R,0,,ok,0,1'], [{'gds': 'a.gds', 'rule': 'R', 'errors': 0, 'case_sha256': 'h'}])
            out = Path(tmp)/'golden.json'
            out.write_text('keep')
            args = ['import', '--counts', str(counts), '--selftest', str(st), '--out', str(out),
                    '--calibre-version', META['calibre_version'], '--deck-sha256', META['deck_sha256'],
                    '--fixture-tarball-sha256', META['fixture_tarball_sha256'],
                    '--generator-commit', META['generator_commit'], '--run-date', META['run_date']]
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                reliability.main(args)
            self.assertEqual(out.read_text(), 'keep')
            out.unlink()
            self.assertEqual(reliability.main(args), 0)
            self.assertEqual(json.loads(out.read_text())['fixtures'][0]['calibre'], 'clean')


def rules_file(path, **states):
    """drc-rules.json with one rule per keyword: 'verified', 'ported' or 'unported'."""
    rules = [{'id': name, 'implementation': 'unported' if state == 'unported' else 'geometry_port',
              'golden_compared': state == 'verified'} for name, state in states.items()]
    path.write_text(json.dumps({'rules': rules}))
    return path


class CheckCliTests(unittest.TestCase):
    def run_check(self, records, **states):
        states = states or {'R': 'verified'}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rules_file(tmp/'drc-rules.json', **states)
            (tmp/'golden'/'batch').mkdir(parents=True)
            (tmp/'golden'/'batch'/'golden.json').write_text(json.dumps(dict(meta=META, **golden(
                ('a.gds', 'R', 'h1', 'fired', {'target_count': 1}),
                ('c.gds', 'R', 'h3', 'refused', {'refused_reason': 'Rule file precision 1000'})))))
            (tmp/'selftest.json').write_text(json.dumps(selftest(*records)))
            with contextlib.redirect_stdout(io.StringIO()):
                code = reliability.main(['check', '--selftest', str(tmp/'selftest.json'),
                                         '--golden', str(tmp/'golden'), '--out', str(tmp/'out'),
                                         '--rules', str(tmp/'drc-rules.json')])
            return code, json.loads((tmp/'out'/'result.json').read_text()), (tmp/'out'/'summary.md').read_text(encoding='utf-8')

    def test_check_passes_and_reports_exclusion(self):
        code, result, summary = self.run_check([('a.gds', 'R', 4, 'h1'), ('c.gds', 'R', 4, 'h3')])
        self.assertEqual(code, 0)
        self.assertEqual(result['rules'], {'R': 'match'})
        self.assertIn('c.gds', summary)
        self.assertIn('Rule file precision 1000', summary)

    def test_check_fails_on_mismatch_or_missing_golden(self):
        for records in ([('a.gds', 'R', 0, 'h1')], [('a.gds', 'R', 4, 'h9')]):
            with self.subTest(records=records):
                self.assertEqual(self.run_check(records)[0], 1)

    def test_check_gates_only_verified_rules(self):
        records = [('a.gds', 'R', 4, 'h1'), ('b.gds', 'P', 0, 'h7')]  # P has no golden yet
        code, result, summary = self.run_check(records, R='verified', P='ported')
        self.assertEqual(code, 0)
        self.assertEqual(result['gate']['rules'], ['R'])
        self.assertEqual(result['rules']['P'], 'no_golden')

    def test_verified_rule_without_usable_fixture_fails(self):
        # Only an excluded fixture, or no fixture at all, is not evidence for a verified rule.
        for records, states in (([('c.gds', 'R', 4, 'h3')], {'R': 'verified'}),
                                ([('a.gds', 'R', 4, 'h1')], {'R': 'verified', 'Q': 'verified'})):
            with self.subTest(records=records, states=states):
                code, result, summary = self.run_check(records, **states)
                self.assertEqual(code, 1)
                self.assertIn('근거 없음', summary)


class RuleStateTests(unittest.TestCase):
    def test_three_states(self):
        self.assertEqual(reliability.rule_state({'implementation': 'unported', 'golden_compared': False}), 'unported')
        self.assertEqual(reliability.rule_state({'implementation': 'geometry_port', 'golden_compared': False}), 'ported')
        self.assertEqual(reliability.rule_state({'implementation': 'geometry_port', 'golden_compared': True}), 'verified')

    def test_catalog_has_96_verified_and_113_unported(self):
        from drc_ports import PORTS
        catalog = json.loads(RULES_JSON.read_text(encoding='utf-8'))
        states = [reliability.rule_state(r) for r in catalog['rules']]
        self.assertEqual((states.count('verified'), states.count('ported'), states.count('unported')), (96, 0, 113))
        self.assertEqual(set(reliability.verified_rules(catalog)), set(PORTS))


class UnverifiedListTests(unittest.TestCase):
    def setUp(self):
        self.items = json.loads((RELIABILITY/'unverified.json').read_text(encoding='utf-8'))['items']

    def test_initial_items(self):
        self.assertEqual([i['id'] for i in self.items], [
            'drc-unported-rules', 'drc-global-flags', 'antenna', 'gpio-internal-lvs', 'lvs-vs-calibre',
            'synth-vs-genus', 'pnr-sta-vs-innovus-tempus', 'pex', 'pinmap-25'])
        for item in self.items:
            self.assertEqual(set(item), {'id', 'what', 'why', 'exit_evidence', 'allows_checks', 'docs'}, item['id'])
            for key in ('what', 'why', 'exit_evidence'):
                self.assertTrue(item[key].strip(), (item['id'], key))
            for doc in item['docs']:
                self.assertTrue((ROOT/doc.split('#')[0]).exists(), doc)

    def test_allowed_checks_are_the_unqualified_flow_checks(self):
        allowed = set().union(*(i['allows_checks'] for i in self.items))
        self.assertEqual(allowed, {'asic-drc', 'asic-pex', 'asic-chip-lvs', 'asic-chip-timing', 'asic-pinmap'})

    def test_gpio_lvs_states_cdl_progress(self):
        item = next(i for i in self.items if i['id'] == 'gpio-internal-lvs')
        self.assertIn('원회로 CDL 확보, Calibre·오픈소스 대조 전', item['why'])


class TableTests(unittest.TestCase):
    def setUp(self):
        self.table = json.loads((RELIABILITY/'table.json').read_text(encoding='utf-8'))
        self.unverified = {i['id'] for i in json.loads((RELIABILITY/'unverified.json').read_text(encoding='utf-8'))['items']}

    def test_committed_markdown_is_rendered_from_json(self):
        self.assertEqual(reliability.render(self.table), (RELIABILITY/'table.md').read_text(encoding='utf-8'))

    def test_rows_are_backed_by_evidence_or_unverified_items(self):
        keys = {'id', 'stage', 'open_source', 'commercial', 'evidence', 'verdict', 'scope', 'updated', 'pr_check',
                'unverified', 'note'}
        for row in self.table['rows']:
            with self.subTest(row=row['id']):
                self.assertEqual(set(row), keys)
                self.assertIn(row['verdict'], ('match', 'mismatch', 'no_evidence'))
                self.assertRegex(row['updated'], r'^\d{4}-\d{2}-\d{2}$')
                for path in row['evidence']:
                    self.assertTrue((RELIABILITY/path).is_file(), path)
                if row['verdict'] == 'match':
                    self.assertTrue(row['evidence'])
                else:
                    self.assertTrue(row['unverified'])
                self.assertTrue(set(row['unverified']) <= self.unverified)

    def test_lvs_core_row_matches_and_antenna_stays_unverified(self):
        rows = {r['id']: r for r in self.table['rows']}
        self.assertEqual((rows['lvs-core']['verdict'], rows['lvs-core']['scope']), ('match', '오픈소스 흐름 코어 1건'))
        self.assertEqual(rows['lvs-chip']['verdict'], 'no_evidence')
        self.assertEqual(rows['antenna']['verdict'], 'no_evidence')
        self.assertEqual(rows['drc-fixtures']['verdict'], 'match')

    def test_render_cli_writes_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'table.md'
            self.assertEqual(reliability.main(['render', '--table', str(RELIABILITY/'table.json'), '--out', str(out)]), 0)
            self.assertNotIn(b'\r', out.read_bytes())
            self.assertEqual(out.read_text(encoding='utf-8'), (RELIABILITY/'table.md').read_text(encoding='utf-8'))


class ChipSummaryTests(unittest.TestCase):
    def load(self, name):
        folder = RELIABILITY/'golden'/name
        return json.loads((folder/'summary.json').read_text(encoding='utf-8')), (folder/'README.md').read_text(encoding='utf-8')

    def test_openflow_summary(self):
        summary, readme = self.load('chip-openflow-20261128')
        self.assertEqual(summary['meta']['calibre_version'], 'v2023.4_17.10')
        self.assertEqual(summary['meta']['deck_sha256']['drc'], drc_catalog.SOURCE_SHA)
        core, chip = summary['designs']['v_ternary8_top'], summary['designs']['ternary8_sop28']
        self.assertEqual(core['gds_sha256'], 'fa6ab910b7f03fd4c966c9c19b2455fd7f26297614c1f20ccb221fed9b09ea93')
        self.assertEqual(chip['gds_sha256'], '967bcad67c0f3a4df18e2faec2c10df65c33b27f6da0fef8794ce6168c550fdb')
        self.assertEqual((core['calibre']['drc'], core['calibre']['ant'], core['calibre']['lvs']['result']), (0, 0, 'CORRECT'))
        self.assertEqual((chip['calibre']['drc'], chip['calibre']['ant']), (0, 0))
        self.assertIn(drc_catalog.SOURCE_SHA, readme)

    def test_v2_summary(self):
        summary, readme = self.load('chip-v2-20261128')
        self.assertEqual(summary['meta']['calibre_version'], 'v2023.4_17.10')
        gds = {g['seal_ring']: g for g in summary['gds']}
        self.assertEqual(gds[False]['calibre_drc'], {})
        self.assertEqual(gds[True]['calibre_drc'], {'1.PWL.bad1': 1})
        self.assertEqual(gds[False]['sha256'], '521a5010da74cd8ca75744ebef7141b9cadfd3c9fe155488d561f3132c622e58')
        self.assertEqual(gds[True]['sha256'], 'be4720283cbfc23a9bdca9e9e65609ce1cff60982f90c904a7191d0a3574f9c1')
        self.assertIn('521a5010da74cd8ca75744ebef7141b9cadfd3c9fe155488d561f3132c622e58', readme)

    def test_no_server_details_in_reliability_files(self):
        for path in RELIABILITY.rglob('*'):
            if path.is_file() and path.suffix in ('.md', '.json') and path.name != 'golden.json':
                with self.subTest(path=path.name):
                    self.assertIsNone(SERVER_TRACE.search(path.read_text(encoding='utf-8')))


class GoldenFileTests(unittest.TestCase):
    def test_import_real_batch(self):
        g = json.loads(GOLDEN.read_text())
        self.assertEqual(len(g['fixtures']), 427)
        self.assertEqual(sum(f['calibre'] == 'refused' for f in g['fixtures']), 2)
        self.assertEqual(sum(f['calibre'] == 'fired' for f in g['fixtures']), 253)
        self.assertEqual(sum(f['calibre'] == 'clean' for f in g['fixtures']), 172)
        self.assertEqual(g['meta']['deck_sha256'], drc_catalog.SOURCE_SHA)
        self.assertEqual({k: g['meta'][k] for k in META}, META)
        refused = {f['gds']: f['refused_reason'] for f in g['fixtures'] if f['calibre'] == 'refused'}
        self.assertEqual(set(refused), {'0169-OFFGRID_MET1-finer-dbu.gds', '0170-OFFGRID_MET1-incompatible-dbu.gds'})
        for reason in refused.values():
            self.assertTrue(reason.startswith('Rule file precision 1000 is not consistent with database precision'))

    def test_golden_pins_known_case_hash(self):
        g = json.loads(GOLDEN.read_text())
        first = g['fixtures'][0]
        self.assertEqual(first['gds'], '0000-OFFGRID_CHIPBOUNDARY-on-grid.gds')
        self.assertEqual(first['case_sha256'], reliability.case_sha256(cases()[0]))
        self.assertEqual(first['case_sha256'], 'adfc2d63c67ebc811a5bb9b901f72338eeacaa2041e7a331a9d26ff7c3fa9cab')

    def test_known_count_differences_are_recorded(self):
        g = {f['gds'][:4]: f for f in json.loads(GOLDEN.read_text())['fixtures']}
        self.assertEqual((g['0242']['calibre'], g['0242']['target_count']), ('fired', 1))
        self.assertEqual((g['0408']['calibre'], g['0408']['target_count']), ('fired', 2))
        self.assertEqual(g['0000']['other_rules'], {'1.PWL.bad1': 1})

    def test_readme_states_conditions_without_server_details(self):
        text = (GOLDEN_DIR/'README.md').read_text(encoding='utf-8')
        for needle in ('v2023.4_17.10', drc_catalog.SOURCE_SHA, 'a125b25350f984c46dde3d9c73f172bd085508ac540eddb35b86709e18a394d8',
                       '303bcb6', '2026-11-28'):
            self.assertIn(needle, text)
        self.assertIsNone(re.search(r'polaris|snu\.|\d+\.\d+\.\d+\.\d+|/tmp|/home|authorized_keys', text, re.I))


if __name__ == '__main__':
    unittest.main()
