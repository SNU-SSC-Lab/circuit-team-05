"""Golden results are keyed by the fixture definition, not by GDS bytes."""
import collections
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'/'asic'))
import reliability
import drc_catalog
from drc_cases import cases

GOLDEN_DIR = ROOT/'verification/reliability/golden/drc-fixtures-20261128'
GOLDEN = GOLDEN_DIR/'golden.json'
MUTATION_DIR = ROOT/'verification/reliability/golden/drc-mutations-20261128'
MUTATION_GOLDEN = MUTATION_DIR/'golden.json'
RELIABILITY = ROOT/'verification/reliability'
RULES_JSON = ROOT/'verification/asic/drc-rules.json'
SERVER_TRACE = re.compile(r'\.ac\.kr|\d+\.\d+\.\d+\.\d+|/tmp|/home|/var/|authorized_keys', re.I)
LOCAL_PATH = re.compile(r'\b[A-Za-z]:[\\/](?!/)|/mnt/[a-z]/|Users[\\/]', re.I)
PENDING_DIR = RELIABILITY/'golden'/'drc-unported-20261128'
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
        self.assertEqual(len(hashes), 451)  # 427 in golden/drc-fixtures-20261128 + 24 in golden/drc-fixtures-20261128b


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
        records = [('a.gds', 'R', 4, 'h1'), ('c.gds', 'R', 4, 'h3'), ('b.gds', 'P', 0, 'h7')]  # P has no golden yet
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


    # Checks moved here from baseline-guard (Task 7 fix round 1): they need the fixture definitions,
    # which only the unprivileged pull_request job may evaluate.
    def test_golden_fixture_missing_from_selftest_fails(self):  # a verified rule loses evidence
        code, result, summary = self.run_check([('a.gds', 'R', 4, 'h1')])  # golden also has c.gds (h3)
        self.assertEqual(code, 1)
        self.assertEqual(result['gate']['failing'], ['R'])
        self.assertEqual([f['gds'] for f in result['gate']['lost']], ['c.gds'])
        self.assertIn('`c.gds`', summary)
        self.assertIn('사라진', summary)

    def test_changed_or_added_fixture_of_verified_rule_fails(self):
        for records in ([('a.gds', 'R', 4, 'h9'), ('c.gds', 'R', 4, 'h3')],  # definition changed
                        [('a.gds', 'R', 4, 'h1'), ('c.gds', 'R', 4, 'h3'), ('n.gds', 'R', 0, 'h8')]):  # added
            with self.subTest(records=records):
                code, result, summary = self.run_check(records)
                self.assertEqual(code, 1)
                self.assertIn('근거 없음', summary)

    def test_only_refused_fixtures_left_fails(self):
        code, result, summary = self.run_check([('c.gds', 'R', 4, 'h3')])
        self.assertEqual(code, 1)
        self.assertIn('Calibre가 거부한 제외 fixture만', summary)

    def test_zero_verified_rules_fails(self):
        code, result, summary = self.run_check([('a.gds', 'R', 4, 'h1'), ('c.gds', 'R', 4, 'h3')], R='ported')
        self.assertEqual(code, 1)
        self.assertEqual(result['gate']['status'], 'fail')
        self.assertIn('verified 규칙이 하나도 없', summary)


class RuleStateTests(unittest.TestCase):
    def test_three_states(self):
        self.assertEqual(reliability.rule_state({'implementation': 'unported', 'golden_compared': False}), 'unported')
        self.assertEqual(reliability.rule_state({'implementation': 'geometry_port', 'golden_compared': False}), 'ported')
        self.assertEqual(reliability.rule_state({'implementation': 'geometry_port', 'golden_compared': True}), 'verified')

    def test_state_counts_feed_selftest_and_audit_records(self):
        catalog = {'rules': [{'id': 'A', 'implementation': 'unported'},
                             {'id': 'B', 'implementation': 'geometry_port', 'golden_compared': False},
                             {'id': 'C', 'implementation': 'geometry_port', 'golden_compared': True}]}
        self.assertEqual(reliability.state_counts(catalog), {'unported': 1, 'ported': 1, 'verified': 1})
        self.assertEqual(reliability.state_counts(catalog, {'B', 'C'}), {'unported': 0, 'ported': 1, 'verified': 1})
        real = json.loads(RULES_JSON.read_text(encoding='utf-8'))
        self.assertEqual(reliability.state_counts(real), {'unported': 113, 'ported': 0, 'verified': 96})

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
        # lvs-vs-calibre left on 2026-11-28: core and SOP28 chip both have an open-source ↔ Calibre comparison;
        # the remaining gap (pad-internal devices on the open-source side) is gpio-internal-lvs.
        # synth-vs-genus left on 2026-11-28: RTL ↔ Genus and RTL ↔ Yosys formally proven (golden/synth-20261128).
        self.assertEqual([i['id'] for i in self.items], [
            'drc-unported-rules', 'drc-global-flags', 'antenna', 'gpio-internal-lvs',
            'pnr-sta-vs-innovus-tempus', 'sdc-portability', 'pex', 'wire-rc-zero', 'pinmap-25'])
        for item in self.items:
            self.assertEqual(set(item), {'id', 'what', 'why', 'exit_evidence', 'allows_checks', 'docs'}, item['id'])
            for key in ('what', 'why', 'exit_evidence'):
                self.assertTrue(item[key].strip(), (item['id'], key))
            for doc in item['docs']:
                self.assertTrue((ROOT/doc.split('#')[0]).exists(), doc)

    def test_allowed_checks_are_the_unqualified_flow_checks(self):
        allowed = set().union(*(i['allows_checks'] for i in self.items))
        self.assertEqual(allowed, {'asic-drc', 'asic-pex', 'asic-chip-lvs', 'asic-chip-timing', 'asic-pinmap'})

    def test_gpio_lvs_states_what_is_left(self):
        item = next(i for i in self.items if i['id'] == 'gpio-internal-lvs')
        self.assertIn('9/9 CORRECT', item['why'])
        self.assertIn('오픈소스 쪽 패드 내부 소자 LVS는 아직 없다', item['why'])
        self.assertEqual(item['allows_checks'], ['asic-chip-lvs'])

    def test_new_items_state_the_2026_11_28_facts(self):
        items = {i['id']: i for i in self.items}
        # std-cell-netgen-11 closed 2026-11-28: lvs_reduce.py + netgen_setup.tcl match all 34 kit cells.
        self.assertNotIn('std-cell-netgen-11', items)
        self.assertIn('estimated.spef', items['wire-rc-zero']['what'])
        # sdc-portability narrowed 2026-11-28: the flow SDC now lists the inputs; only a Tempus read is missing.
        self.assertIn('Tempus', items['sdc-portability']['what'])
        self.assertIn('get_ports {IN[0] IN[1] IN[2] IN[3] IN_VALID RST_N}', items['sdc-portability']['why'])
        self.assertIn('remove_from_collection', items['sdc-portability']['why'])
        # pnr-sta-vs-innovus-tempus narrowed 2026-11-28 (approved): chip timing only, no Innovus placement match.
        chip = items['pnr-sta-vs-innovus-tempus']
        self.assertEqual(chip['what'], 'GPIO·패키지 지연을 넣은 칩 단위 타이밍')
        self.assertNotIn('Innovus P&R', chip['exit_evidence'])
        self.assertEqual(chip['allows_checks'], ['asic-chip-timing'])
        self.assertNotIn('synth-vs-genus', items)
        self.assertIn('drc-unported-20261128', items['drc-unported-rules']['why'])
        self.assertIn('drc-unported-20261128', items['antenna']['why'])


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

    def test_row_verdicts_after_wave_2(self):
        rows = {r['id']: r for r in self.table['rows']}
        self.assertEqual([r['id'] for r in self.table['rows']], [
            'drc-fixtures', 'drc-mutations', 'drc-unported', 'drc-chip-v2', 'drc-chip-openflow', 'lvs-core', 'lvs-cells', 'lvs-chip',
            'spice', 'synth', 'pnr-sta', 'pex', 'antenna'])
        verdicts = {key: row['verdict'] for key, row in rows.items()}
        self.assertEqual(verdicts, {
            'drc-fixtures': 'match', 'drc-mutations': 'match', 'drc-unported': 'no_evidence', 'drc-chip-v2': 'match',
            'drc-chip-openflow': 'match', 'lvs-core': 'match', 'lvs-cells': 'match', 'lvs-chip': 'match',
            'spice': 'match', 'synth': 'match', 'pnr-sta': 'match', 'pex': 'no_evidence',
            'antenna': 'no_evidence'})
        self.assertEqual(rows['lvs-core']['scope'], '오픈소스 흐름 코어 1건')
        self.assertIn('오픈소스 쪽 패드 내부 소자 LVS는 아직 없음', rows['lvs-chip']['scope'])
        self.assertIn('gpio-internal-lvs', rows['lvs-chip']['unverified'])
        self.assertIn('estimated.spef는 RC 0', rows['pnr-sta']['scope'])
        self.assertIn('hold 최대 0.353 ns', rows['pnr-sta']['scope'])
        self.assertTrue(rows['pnr-sta']['scope'].startswith('STA 계산만:'))
        self.assertIn('check-pending', rows['drc-unported']['pr_check'])
        self.assertIn('451개 중 449개', rows['drc-fixtures']['note'])
        self.assertIn('golden/drc-fixtures-20261128b/golden.json', rows['drc-fixtures']['evidence'])
        self.assertEqual(rows['drc-mutations']['evidence'], ['golden/drc-mutations-20261128/golden.json',
                                                             'golden/drc-mutations-20261128b/golden.json'])
        self.assertEqual(len({r['stage'] for r in self.table['rows']}), len(self.table['rows']))  # labels tell rows apart
        self.assertIn('제외', rows['drc-unported']['note'])
        self.assertEqual(rows['lvs-cells']['unverified'], [])
        self.assertIn('34/34 일치', rows['lvs-cells']['note'])
        self.assertIn('golden/lvs-20261128/README.md', rows['lvs-cells']['evidence'])
        self.assertIn('wire-rc-zero', rows['pex']['unverified'])
        self.assertIn('golden/drc-unported-20261128/golden.json', rows['antenna']['evidence'])
        self.assertIn('golden/drc-unported-20261128/golden.json', rows['drc-unported']['evidence'])
        self.assertIn('golden/pex-reference-20261128/README.md', rows['pex']['evidence'])
        self.assertIn('golden/spice-20261128/summary.json', rows['spice']['evidence'])
        self.assertIn('golden/sta-20261128/summary.json', rows['pnr-sta']['evidence'])
        self.assertEqual(rows['synth']['evidence'], ['golden/synth-20261128/summary.json'])
        self.assertTrue(rows['synth']['scope'].startswith('기준점 1건'))
        self.assertIn('기준점에서만', rows['synth']['pr_check'])
        for key in ('lvs-cells', 'lvs-chip'):
            self.assertIn('golden/lvs-20261128/summary.json', rows[key]['evidence'])

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

    def test_no_local_paths_in_reliability_or_pending_files(self):
        paths = [p for p in RELIABILITY.rglob('*') if p.is_file() and p.suffix in ('.md', '.json')]
        paths += sorted((ROOT/'scripts'/'asic').glob('drc_cases_pending*.py'))
        self.assertGreaterEqual(len(paths), 4)
        for path in paths:
            with self.subTest(path=path.name):
                text = path.read_text(encoding='utf-8')
                self.assertIsNone(LOCAL_PATH.search(text))
                if path.parent.name == 'drc-unported-20261128' or path.suffix == '.py':
                    self.assertIsNone(SERVER_TRACE.search(text))


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
        self.assertIsNone(SERVER_TRACE.search(text))


MUTATION_META = dict(calibre_version='v2023.4_17.10', deck_sha256=drc_catalog.SOURCE_SHA,
                     corpus_tarball_sha256='0dbbcf4dcbcbae612b51e8d76da887a81e9524e3636ade5929ae9a45eaeb2225',
                     run_date='2026-11-28', klayout_version='0.28.16')


def mutation(gds, calibre='ok', fired=None, sha=None, polygons=10, reason=None):
    return {'gds': gds, 'source': 's.gds', 'cell': gds[:-4], 'variant': 1, 'op': 'grow',
            'geometry_sha256': sha or 'g-'+gds, 'polygons': polygons, 'calibre': calibre,
            'rules_fired': fired or {}, 'refused_reason': reason}


def drc(**errors):
    """KLayout drc.py `rules` part: drc(R=2) -> {'R': {'errors': 2}}."""
    return {rule: {'errors': count} for rule, count in errors.items()}


class MutationImportTests(unittest.TestCase):
    RECORDS = [{'gds': 'a.gds', 'source': 's.gds', 'cell': 'A', 'variant': 0, 'op': 'original'},
               {'gds': 'b.gds', 'source': 's.gds', 'cell': 'A', 'variant': 1, 'op': 'grow', 'delta_um': 0.8,
                'layer': '31/0', 'near_um': [0, 0, 1, 1]}]
    GEOMETRY = {'a.gds': {'geometry_sha256': 'ga', 'polygons': 3}, 'b.gds': {'geometry_sha256': 'gb', 'polygons': 3}}

    def corpus(self, tmp, rows, records, geometry):
        tmp = Path(tmp)
        (tmp/'c2_counts.csv').write_text('gds,rules_fired,calibre_exit,run_ms,calibre_error\n'+''.join(r+'\n' for r in rows))
        (tmp/'manifest.json').write_text(json.dumps({'seed': 20261128, 'per_cell': 6, 'records': records}))
        (tmp/'geometry.json').write_text(json.dumps(geometry))
        return tmp/'c2_counts.csv', tmp/'manifest.json', tmp/'geometry.json'

    def test_import_binds_manifest_geometry_and_calibre(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.corpus(tmp, ['a.gds,7.CONT.E1:2;1.PWL.bad1:1,0,600,',
                                      'b.gds,,4,500,"Non-orientable boundary at location (1,2) in cell mut on layer 14 datatype 0."'],
                                self.RECORDS, self.GEOMETRY)
            g = reliability.import_mutations(*paths, MUTATION_META)
        self.assertEqual((g['meta']['seed'], g['meta']['per_cell']), (20261128, 6))
        self.assertEqual(g['meta']['deck_sha256'], drc_catalog.SOURCE_SHA)
        a, b = g['mutations']
        self.assertEqual((a['calibre'], a['rules_fired'], a['geometry_sha256'], a['polygons']),
                         ('ok', {'7.CONT.E1': 2, '1.PWL.bad1': 1}, 'ga', 3))
        self.assertIsNone(a['refused_reason'])
        self.assertEqual((b['calibre'], b['rules_fired'], b['op'], b['delta_um'], b['layer']), ('refused', {}, 'grow', 0.8, '31/0'))
        self.assertTrue(b['refused_reason'].startswith('Non-orientable boundary'))

    def test_import_rejects_unmatched_inputs(self):
        bad = [(['a.gds,,0,1,'], self.GEOMETRY),  # b.gds has no Calibre row
               (['a.gds,,0,1,', 'b.gds,,0,1,', 'c.gds,,0,1,'], self.GEOMETRY),  # c.gds not in manifest
               (['a.gds,,0,1,', 'b.gds,,0,1,'], {'a.gds': self.GEOMETRY['a.gds']}),  # b.gds has no geometry
               (['a.gds,,0,1,', 'b.gds,,4,1,'], self.GEOMETRY)]  # refused without a reason
        for rows, geometry in bad:
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):
                    reliability.import_mutations(*self.corpus(tmp, rows, self.RECORDS, geometry), MUTATION_META)
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.corpus(tmp, ['a.gds,,0,1,', 'b.gds,,0,1,'], self.RECORDS, self.GEOMETRY)
            with self.assertRaises(ValueError):
                reliability.import_mutations(*paths, dict(MUTATION_META, deck_sha256='0'*64))


class MutationCompareTests(unittest.TestCase):
    GOLDEN = {'meta': MUTATION_META, 'mutations': [
        mutation('ok.gds', fired={'R': 2, 'U': 1}),
        mutation('clean.gds'),
        mutation('refused.gds', 'refused', reason='Non-orientable boundary'),
        mutation('empty.gds', polygons=0, fired={'U': 1})]}

    def geometry(self, **changed):
        result = {m['gds']: {'geometry_sha256': m['geometry_sha256'], 'polygons': m['polygons']}
                  for m in self.GOLDEN['mutations']}
        result.update(changed)
        return result

    def test_targets_skip_refused_and_empty(self):
        self.assertEqual(reliability.mutation_targets(self.GOLDEN, self.geometry()), ['ok.gds', 'clean.gds'])

    def test_agreement_on_verified_rules_only(self):
        # Q is not verified, so its KLayout-only marker does not count; U is unported (Calibre only).
        r = reliability.compare_mutations(self.GOLDEN, self.geometry(),
                                          {'ok.gds': drc(R=1, Q=3), 'clean.gds': drc(R=0, Q=0)}, ['R'])
        self.assertEqual(r['status'], 'pass')
        self.assertEqual(r['counts'], {'both': 1, 'none': 1, 'klayout_only': 0, 'calibre_only': 0})
        self.assertEqual([m['verdict'] for m in r['mutations']], ['match', 'match', 'excluded', 'excluded'])
        self.assertEqual(r['mutations'][2]['reason'], 'Non-orientable boundary')
        self.assertIn('empty', r['mutations'][3]['reason'])

    def test_disagreement_fails_with_counts(self):
        r = reliability.compare_mutations(self.GOLDEN, self.geometry(),
                                          {'ok.gds': drc(R=0), 'clean.gds': drc(R=5)}, ['R'])
        self.assertEqual(r['status'], 'fail')
        self.assertEqual(r['disagreements'], [{'gds': 'ok.gds', 'rule': 'R', 'klayout': 0, 'calibre': 2},
                                              {'gds': 'clean.gds', 'rule': 'R', 'klayout': 5, 'calibre': 0}])

    def test_changed_or_missing_geometry_or_klayout_failure_fails(self):
        for geometry, klayout, verdict in [
                (self.geometry(**{'ok.gds': {'geometry_sha256': 'other', 'polygons': 10}}),
                 {'clean.gds': drc(R=0)}, 'geometry_changed'),
                ({k: v for k, v in self.geometry().items() if k != 'clean.gds'}, {'ok.gds': drc(R=1)}, 'missing'),
                (self.geometry(), {'ok.gds': drc(R=1)}, 'klayout_error'),  # no KLayout result for clean.gds
                (self.geometry(), {'ok.gds': drc(R=1), 'clean.gds': drc(Q=0)}, 'klayout_error')]:  # R missing
            with self.subTest(verdict=verdict, klayout=klayout):
                r = reliability.compare_mutations(self.GOLDEN, geometry, klayout, ['R'])
                self.assertEqual(r['status'], 'fail')
                self.assertIn(verdict, [m['verdict'] for m in r['mutations']])

    def test_empty_top_is_excluded_only_without_a_verified_calibre_verdict(self):
        golden = {'meta': MUTATION_META, 'mutations': [mutation('ok.gds'), mutation('empty.gds', polygons=0, fired={'R': 1})]}
        geometry = {m['gds']: {'geometry_sha256': m['geometry_sha256'], 'polygons': m['polygons']}
                    for m in golden['mutations']}
        r = reliability.compare_mutations(golden, geometry, {'ok.gds': drc(R=0)}, ['R'])
        self.assertEqual(r['status'], 'fail')
        self.assertEqual(r['mutations'][1]['verdict'], 'mismatch')
        self.assertEqual(r['disagreements'], [{'gds': 'empty.gds', 'rule': 'R', 'klayout': 0, 'calibre': 1}])

    def test_klayout_timeout_reads_as_klayout_error(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
                reliability.subprocess, 'run', side_effect=reliability.subprocess.TimeoutExpired('klayout', 600)):
            got = reliability._drc_one('a.gds', tmp, Path(tmp), 'klayout')
        self.assertIsNone(got)

    def test_no_verified_rule_fails(self):
        r = reliability.compare_mutations(self.GOLDEN, self.geometry(), {'ok.gds': drc(R=2), 'clean.gds': drc(R=0)}, [])
        self.assertEqual(r['status'], 'fail')

    def test_check_mutations_cli(self):
        for flip, code in [(False, 0), (True, 1)]:
            def fake_drc(gds_dir, targets, out, jobs, klayout):
                self.assertEqual(targets, ['ok.gds', 'clean.gds'])
                return {'ok.gds': drc(R=1), 'clean.gds': drc(R=int(flip))}
            with self.subTest(flip=flip), tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                (tmp/'golden.json').write_text(json.dumps(self.GOLDEN))
                rules_file(tmp/'drc-rules.json', R='verified', U='unported')
                (tmp/'corpus').mkdir()
                with mock.patch.object(reliability, '_mutation_geometry', return_value=self.geometry()), \
                        mock.patch.object(reliability, '_run_drc', side_effect=fake_drc), \
                        mock.patch.object(reliability, 'klayout_version', return_value='KLayout 0.28.16'), \
                        contextlib.redirect_stdout(io.StringIO()):
                    got = reliability.main(['check-mutations', '--golden', str(tmp/'golden.json'),
                                            '--gds-dir', str(tmp/'corpus'), '--out', str(tmp/'out'),
                                            '--rules', str(tmp/'drc-rules.json')])
                self.assertEqual(got, code)
                summary = (tmp/'out'/'summary.md').read_text(encoding='utf-8')
                result = json.loads((tmp/'out'/'result.json').read_text(encoding='utf-8'))
                self.assertEqual(result['status'], 'pass' if code == 0 else 'fail')
                self.assertEqual(result['klayout_version'], 'KLayout 0.28.16')
                self.assertIn('refused.gds', summary)
                if flip:
                    self.assertIn('| `clean.gds` | `R` | 1 | 0 |', summary)

    def test_check_mutations_needs_kit_or_folder(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            reliability.main(['check-mutations', '--golden', 'g.json', '--out', 'o'])

    def test_fixture_check_ignores_mutation_golden(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp/'fixtures').mkdir()
            (tmp/'fixtures'/'golden.json').write_text(json.dumps(dict(meta=META, **golden(('a.gds', 'R', 'h1', 'fired')))))
            (tmp/'mutations').mkdir()
            (tmp/'mutations'/'golden.json').write_text(json.dumps(self.GOLDEN))
            loaded = reliability.load_golden(tmp)
        self.assertEqual([f['gds'] for f in loaded['fixtures']], ['a.gds'])
        self.assertEqual([s['path'] for s in loaded['sources']], ['fixtures/golden.json'])


class EdgeGoldenFileTests(unittest.TestCase):
    FOLDER = RELIABILITY/'golden'/'drc-fixtures-20261128b'

    def test_edge_golden_backs_the_24_enclosure_fixtures(self):
        g = json.loads((self.FOLDER/'golden.json').read_text(encoding='utf-8'))
        self.assertEqual(g['meta']['deck_sha256'], drc_catalog.SOURCE_SHA)
        for needle in ('15acbafef6f71fbf0b4357a3bb1aa82e502347fce9dc3f4e0033d011646ff8ef',
                       '58c6e44f8ef30c79cf2641356cc7ba5ae5840d7359a712e20f54aa0a5597fb02'):
            self.assertIn(needle, g['meta']['fixture_tarball_sha256'])
        all_cases = cases()
        self.assertEqual([f['gds'] for f in g['fixtures']],
                         [reliability.fixture_name(i, all_cases[i])+'.gds' for i in range(427, 451)])
        self.assertEqual([f['case_sha256'] for f in g['fixtures']],
                         [reliability.case_sha256(all_cases[i]) for i in range(427, 451)])
        self.assertEqual([f['calibre'] == 'fired' for f in g['fixtures']], [all_cases[i]['fail'] for i in range(427, 451)])

    def test_all_fixture_golden_covers_every_case(self):
        loaded = reliability.load_golden(RELIABILITY/'golden')
        self.assertEqual(len(loaded['fixtures']), 451)
        self.assertEqual({f['case_sha256'] for f in loaded['fixtures']}, {reliability.case_sha256(c) for c in cases()})

    def test_readme_without_server_details(self):
        text = (self.FOLDER/'README.md').read_text(encoding='utf-8')
        for needle in ('v2023.4_17.10', drc_catalog.SOURCE_SHA, '756b384', '2026-11-28'):
            self.assertIn(needle, text)
        self.assertIsNone(SERVER_TRACE.search(text))
        self.assertIsNone(LOCAL_PATH.search(text))
        self.assertIsNone(LOCAL_PATH.search((self.FOLDER/'golden.json').read_text(encoding='utf-8')))


class MutationGoldenFileTests(unittest.TestCase):
    def test_golden_counts(self):
        g = json.loads(MUTATION_GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual({k: g['meta'][k] for k in MUTATION_META}, MUTATION_META)
        self.assertEqual((g['meta']['seed'], g['meta']['per_cell']), (20261128, 6))
        self.assertEqual(g['meta']['klayout_version'], '0.28.16')
        m = g['mutations']
        self.assertEqual(len(m), 695)
        self.assertEqual(sum(x['calibre'] == 'refused' for x in m), 81)
        self.assertEqual(sum(x['op'] == 'original' for x in m), 105)
        self.assertFalse(any(x['op'] == 'original' for x in m if x['calibre'] == 'refused'))
        self.assertTrue(all(x['refused_reason'].startswith('Non-orientable boundary') for x in m if x['calibre'] == 'refused'))
        self.assertEqual(sum(x['polygons'] == 0 for x in m), 5)
        self.assertTrue(all(re.fullmatch('[0-9a-f]{64}', x['geometry_sha256']) for x in m))
        # Calibre-only verdicts of the first KLayout comparison stay in the golden as Calibre saw them.
        by = {x['gds']: x for x in m}
        self.assertEqual(by['0023-AOI22X1-v3.gds']['rules_fired'].get('7.CONT.E1'), 2)
        self.assertEqual(by['0644-poly2cont_CDNS_756087690058-v5.gds']['rules_fired'].get('7.CONT.E3'), 3)

    def test_readme_states_conditions_without_server_details(self):
        text = (MUTATION_DIR/'README.md').read_text(encoding='utf-8')
        for needle in ('v2023.4_17.10', drc_catalog.SOURCE_SHA,
                       '0dbbcf4dcbcbae612b51e8d76da887a81e9524e3636ade5929ae9a45eaeb2225',
                       '20261128', 'scripts/asic/mutate.py', '2026-11-28'):
            self.assertIn(needle, text)
        self.assertIsNone(SERVER_TRACE.search(text))
        self.assertIsNone(LOCAL_PATH.search(text))
        data = MUTATION_GOLDEN.read_text(encoding='utf-8')
        self.assertIsNone(SERVER_TRACE.search(data))
        self.assertIsNone(LOCAL_PATH.search(data))


ANT_RULES = {'ANT_01', 'ANT_02_1', 'ANT_02_2', 'ANT_02_3', 'ANT_03_1', 'ANT_03_2', 'ANT_03_3', 'ANT_04',
             'ANT_05_1', 'ANT_05_2', 'ANT_06_01', 'ANT_06_02'}
# Calibre-refused 0225/0226 are not corrected: `raises` means our writer/KLayout raises (like 0169/0170).
REFUSED = {('C1a', '0225-NONSIMPLE-bow-tie.gds'), ('C1a', '0226-NONSIMPLE-orthogonal-self-crossing.gds')}
CORRECTED = {('C1a', '0227-NONSIMPLE-self-touching-vertex.gds'): {'fail': False},
             ('C1b', '0315-ANT_06_01-boundary.gds'): {'fail': True},
             ('C1b', '0323-ANT_06_02-boundary.gds'): {'fail': True}}


class PendingCaseTests(unittest.TestCase):
    """Fixtures of rules KLayout does not implement yet (C1a/C1b/C1c), kept out of drc_cases.py."""

    @classmethod
    def setUpClass(cls):
        import drc_cases_pending
        cls.records = drc_cases_pending.records()
        cls.module = drc_cases_pending

    def test_three_groups_857_fixtures(self):
        self.assertEqual(collections.Counter(r['group'] for r in self.records), {'C1a': 229, 'C1b': 330, 'C1c': 298})
        self.assertEqual([r['case'] for r in self.records], self.module.cases())
        self.assertEqual(len({reliability.case_sha256(r['case']) for r in self.records}), 857)
        self.assertEqual(collections.Counter(r['deck'] for r in self.records), {'DRC': 755, 'ANT': 102})
        for record in self.records:
            self.assertEqual(set(record['case']), {'rule', 'label', 'shapes', 'fail', 'hierarchy', 'dbu', 'raises'})
            group_index = record['index']
            self.assertEqual(record['gds'], reliability.fixture_name(group_index, record['case'])+'.gds')

    def test_rules_are_the_unported_ones_flags_and_ant(self):
        catalog = json.loads(RULES_JSON.read_text(encoding='utf-8'))
        states = {rule['id']: reliability.rule_state(rule) for rule in catalog['rules']}
        unported = {rule for rule, state in states.items() if state == 'unported'}
        drc = {r['case']['rule'] for r in self.records if r['deck'] == 'DRC'}
        self.assertEqual(drc, unported | {'ACUTE', 'NONSIMPLE'})
        self.assertEqual({r['case']['rule'] for r in self.records if r['deck'] == 'ANT'}, ANT_RULES)
        self.assertFalse({r['case']['rule'] for r in self.records} & {r for r, s in states.items() if s != 'unported'})

    def test_pending_cases_stay_out_of_the_ported_selftest(self):
        ported = {reliability.case_sha256(c) for c in cases()}
        self.assertFalse(ported & {reliability.case_sha256(r['case']) for r in self.records})
        self.assertFalse({c['rule'] for c in cases()} & {r['case']['rule'] for r in self.records})

    def test_intent_follows_calibre_for_the_three_corrected_fixtures(self):
        corrected = {(r['group'], r['gds']): r for r in self.records if r['correction']}
        self.assertEqual(set(corrected), set(CORRECTED))
        for key, change in CORRECTED.items():
            with self.subTest(fixture=key):
                record = corrected[key]
                for field, value in change.items():
                    self.assertEqual(record['case'][field], value)
                original = dict(record['case'], **{field: not value for field, value in change.items()})
                self.assertEqual(record['run_case_sha256'], reliability.case_sha256(original))
                self.assertNotEqual(record['run_case_sha256'], reliability.case_sha256(record['case']))
        for record in self.records:
            if not record['correction']:
                self.assertEqual(record['run_case_sha256'], reliability.case_sha256(record['case']))
            self.assertFalse(record['case']['raises'], record['gds'])  # no pending fixture expects a writer error

    def test_calibre_refused_fixtures_keep_their_run_definition(self):
        by = {(r['group'], r['gds']): r for r in self.records}
        for key in REFUSED:
            record = by[key]
            self.assertIsNone(record['correction'])
            self.assertEqual((record['case']['fail'], record['case']['raises']), (True, False))


def pending_doc(entries, **meta):
    return {'meta': dict({'pending': True, 'calibre_version': 'v2023.4_17.10'}, **meta), 'fixtures': entries}


class PendingGoldenTests(unittest.TestCase):
    def setUp(self):
        self.golden = json.loads((PENDING_DIR/'golden.json').read_text(encoding='utf-8'))

    def test_pending_golden_is_one_to_one_with_the_definitions(self):
        result = reliability.check_pending(RELIABILITY/'golden')
        self.assertEqual(result['problems'], [])
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['fixtures'], 857)
        self.assertEqual(result['sources'], ['drc-unported-20261128/golden.json'])

    def test_golden_counts_and_meta(self):
        meta, fixtures = self.golden['meta'], self.golden['fixtures']
        self.assertTrue(meta['pending'])
        self.assertEqual(meta['calibre_version'], 'v2023.4_17.10')
        self.assertEqual(meta['deck_sha256'], drc_catalog.SOURCE_SHA)
        self.assertEqual(meta['ant_deck_sha256'], '80dc257e6778121ab9a61a444d0e82c79999dc785d8e6aa5a6a2a5318c7b94b5')
        for digest in ('69f0e00051546ae97619ad0ab61ffc9f8fe5c8fed8b7a7b1dd620bef4a21a10f',
                       '5d6537293f63eb7205c77983662443cc0800197d99a654d31a52e705230eec9e',
                       '76d120fdd2fd826e1b7fb79eb8602ad345e2ace5203eb5e23eb5f4b61d6aeef9'):
            self.assertIn(digest, meta['fixture_tarball_sha256'])
        self.assertEqual(len(fixtures), 857)
        self.assertEqual(collections.Counter(f['calibre'] for f in fixtures)['refused'], 2)
        self.assertEqual(collections.Counter(f['deck'] for f in fixtures), {'DRC': 755, 'ANT': 102})
        refused = [f for f in fixtures if f['calibre'] == 'refused']
        self.assertEqual({f['gds'] for f in refused},
                         {'0225-NONSIMPLE-bow-tie.gds', '0226-NONSIMPLE-orthogonal-self-crossing.gds'})
        for entry in refused:
            self.assertTrue(entry['refused_reason'].startswith('Non-orientable boundary'))
        by = {(f['group'], f['gds']): f for f in fixtures}
        self.assertEqual(by[('C1b', '0315-ANT_06_01-boundary.gds')]['target_count'], 124)
        self.assertEqual(by[('C1a', '0227-NONSIMPLE-self-touching-vertex.gds')]['calibre'], 'clean')
        self.assertEqual(by[('C1a', '0222-ACUTE-right-triangle-45.gds')]['target_count'], 2)

    def test_every_calibre_verdict_equals_the_intent(self):
        import drc_cases_pending
        cases_by = {(r['group'], r['gds']): r['case'] for r in drc_cases_pending.records()}
        for entry in self.golden['fixtures']:
            case = cases_by[(entry['group'], entry['gds'])]
            self.assertFalse(case['raises'], entry['gds'])
            if entry['calibre'] == 'refused':
                self.assertIn((entry['group'], entry['gds']), REFUSED)  # excluded with a reason, no intent checked
                self.assertNotIn('run_case_sha256', entry)
                self.assertEqual(entry['case_sha256'], reliability.case_sha256(case))
            else:
                self.assertEqual(entry['calibre'] == 'fired', case['fail'], (entry['group'], entry['gds']))

    def test_fixture_check_ignores_pending_golden(self):
        loaded = reliability.load_golden(RELIABILITY/'golden')
        self.assertEqual(len(loaded['fixtures']), 451)
        self.assertNotIn('drc-unported-20261128/golden.json', [s['path'] for s in loaded['sources']])

    def test_check_pending_reports_drift(self):
        import drc_cases_pending
        good = [f for f in self.golden['fixtures']]
        broken = {
            'missing': good[1:],
            'extra': good+[dict(good[0], gds='9999-extra.gds', case_sha256='0'*64)],
            'changed': [dict(good[0], case_sha256='0'*64)]+good[1:],
            'verdict': [dict(good[0], calibre='fired' if good[0]['calibre'] == 'clean' else 'clean')]+good[1:],
        }
        refused = [i for i, f in enumerate(good) if f['calibre'] == 'refused']
        self.assertEqual(len(refused), 2)
        for name, entries in broken.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)/'golden'/'pending'
                folder.mkdir(parents=True)
                (folder/'golden.json').write_text(json.dumps(pending_doc(entries)), encoding='utf-8')
                result = reliability.check_pending(Path(tmp)/'golden', drc_cases_pending.records())
                self.assertEqual(result['status'], 'fail')
                self.assertTrue(result['problems'])

    def test_check_pending_excludes_calibre_refusals_whatever_the_intent(self):
        def record(gds, fail, raises=False):
            case = {'rule': 'R', 'label': gds, 'shapes': [], 'fail': fail, 'hierarchy': False, 'dbu': .001, 'raises': raises}
            return {'group': 'G', 'gds': gds, 'deck': 'DRC', 'case': case, 'run_case_sha256': reliability.case_sha256(case)}
        def entry(rec, calibre):
            return {'group': 'G', 'gds': rec['gds'], 'rule': 'R', 'deck': 'DRC', 'case_sha256': rec['run_case_sha256'],
                    'calibre': calibre, 'refused_reason': 'Non-orientable boundary' if calibre == 'refused' else None}
        records = [record('a.gds', True), record('b.gds', False), record('c.gds', True, raises=True), record('d.gds', True)]
        entries = [entry(records[0], 'refused'), entry(records[1], 'refused'), entry(records[2], 'refused'),
                   entry(records[3], 'fired')]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'p').mkdir()
            (Path(tmp)/'p'/'golden.json').write_text(json.dumps(pending_doc(entries)), encoding='utf-8')
            result = reliability.check_pending(Path(tmp), records)
            self.assertEqual((result['status'], result['problems'], result['excluded']), ('pass', [], 3))
            entries[3]['calibre'] = 'clean'
            (Path(tmp)/'p'/'golden.json').write_text(json.dumps(pending_doc(entries)), encoding='utf-8')
            self.assertEqual(reliability.check_pending(Path(tmp), records)['status'], 'fail')

    def test_check_pending_without_pending_golden_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'fixtures').mkdir()
            (Path(tmp)/'fixtures'/'golden.json').write_text(json.dumps(dict(meta=META, **golden(('a.gds', 'R', 'h1', 'fired')))))
            self.assertEqual(reliability.check_pending(Path(tmp))['status'], 'fail')

    def test_check_pending_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(reliability.main(['check-pending']), 0)
        self.assertIn('857', out.getvalue())

    def test_readme_states_conditions(self):
        text = (PENDING_DIR/'README.md').read_text(encoding='utf-8')
        for needle in ('v2023.4_17.10', drc_catalog.SOURCE_SHA, '80dc257e6778121ab9a61a444d0e82c79999dc785d8e6aa5a6a2a5318c7b94b5',
                       '69f0e00051546ae97619ad0ab61ffc9f8fe5c8fed8b7a7b1dd620bef4a21a10f', 'check-pending',
                       'drc_cases_pending.py', '2026-11-28'):
            self.assertIn(needle, text)
        self.assertIsNone(SERVER_TRACE.search(text))


class EvidenceSummaryTests(unittest.TestCase):
    def load(self, name):
        folder = RELIABILITY/'golden'/name
        return json.loads((folder/'summary.json').read_text(encoding='utf-8')), (folder/'README.md').read_text(encoding='utf-8')

    def test_lvs_summary(self):
        summary, readme = self.load('lvs-20261128')
        meta = summary['meta']
        self.assertEqual(meta['calibre_version'], 'v2023.4_17.10')
        self.assertEqual(meta['lvs_deck_sha256'], '4cebfddc77ab6b4fb20e869281a895be9933a900670c98ff792ed5204c6366e0')
        self.assertFalse(meta['deck_modified'])
        runs = summary['runs']
        self.assertEqual(set(runs), {'core', 'chip', 'std_cells', 'gpio'})
        core, chip = runs['core'], runs['chip']
        self.assertEqual((core['result'], core['ports'], core['nets']), ('CORRECT', [15, 15], [2096, 2096]))
        self.assertEqual((chip['result'], chip['ports'], chip['nets']), ('CORRECT', [15, 15], [2129, 2129]))
        self.assertEqual(chip['instances']['R'], [7, 7])
        self.assertEqual(chip['header_extra'], [])
        self.assertEqual(chip['gds_sha256'], '967bcad67c0f3a4df18e2faec2c10df65c33b27f6da0fef8794ce6168c550fdb')
        self.assertEqual(chip['source_sha256']['ternary8_sop28.cdl'],
                         'f9b09d1731fc8790c80bc14ab552a82e690316138fe3f446729925d8030bfce1')
        self.assertEqual(chip['open_source']['pad_internal_lvs'], None)
        cells = runs['std_cells']
        self.assertEqual(len(cells['cells']), 34)
        self.assertTrue(all(c['result'] == 'CORRECT' for c in cells['cells'].values()))
        self.assertEqual(len(cells['open_source']['matched']), 23)
        self.assertEqual(sorted(cells['open_source']['unconfirmed']), [
            'AND2X2', 'AOI21X1', 'BUFX4', 'INVX2', 'INVX4', 'INVX8', 'NOR2X1', 'OAI21X1', 'OAI22X1', 'OR2X2', 'TBUFX2'])
        gpio = runs['gpio']
        self.assertEqual(gpio['header_extra'], ['VIRTUAL CONNECT NAME "VDD" "VSS"'])
        self.assertEqual(len(gpio['cells']), 9)
        self.assertTrue(all(c['result'] == 'CORRECT' for c in gpio['cells'].values()))
        self.assertIn('오픈소스 쪽 패드 내부 소자 LVS는 아직 없다', readme)

    def test_sta_summary(self):
        summary, readme = self.load('sta-20261128')
        self.assertEqual(summary['meta']['tempus_version'], 'v23.14-s089_1')
        self.assertEqual(summary['meta']['opensta_version'], '3.1.0')
        corners = summary['corners']
        self.assertEqual(set(corners), {'typical', 'bestRC', 'worstRC'})
        typical = corners['typical']
        self.assertEqual((typical['tempus']['setup_ns'], typical['tempus']['hold_ns']), (48.444, 1.895))
        self.assertEqual((typical['opensta']['dmp_ceff_elmore']['setup_ns'], typical['opensta']['dmp_ceff_elmore']['hold_ns']),
                         (48.3162, 1.6104))
        for corner in corners.values():
            self.assertEqual(corner['endpoints'], 72)
            for calc in ('dmp_ceff_elmore', 'arnoldi'):
                self.assertLessEqual(corner['max_abs_diff_ns'][calc]['setup'], 0.26)
                self.assertLessEqual(corner['max_abs_diff_ns'][calc]['hold'], 0.36)
        self.assertIn('delete_from_list', summary['sdc']['tempus_copy_diff'])
        self.assertTrue(summary['open_flow']['estimated_spef_rc_zero'])
        self.assertIn('remove_from_collection', readme)

    def test_synth_summary(self):
        summary, readme = self.load('synth-20261128')
        genus, yosys = summary['netlists']['genus'], summary['netlists']['yosys']
        self.assertEqual(genus['sha256'], '6fef0f3e70eb4c857500e3d697cd0017ab54d4dc8481fc014e9997bc3600ed24')
        self.assertEqual((genus['tool'], genus['cells'], genus['flops']), ('Genus(TM) Synthesis Solution 23.14-s090_1', 325, 64))
        self.assertEqual(sum(genus['by_type'].values()), 325)
        self.assertEqual((yosys['cells'], yosys['flops']), (452, 66))
        self.assertEqual(sum(yosys['by_type'].values()), 452)
        formal = summary['formal']
        for key, pairs in (('rtl_vs_genus', 109), ('rtl_vs_yosys', 72)):
            self.assertEqual((formal[key]['status'], formal[key]['pairs'], formal[key]['proven']), ('pass', pairs, pairs))
            self.assertEqual(formal[key]['outputs_left_out'], [])
        self.assertTrue(all(v.startswith('fail') for k, v in formal['negative_controls'].items() if k != 'note'))
        self.assertEqual(formal['kit_verilog_vs_liberty']['different'], [])
        self.assertEqual({r['jobs'] for r in summary['simulation']['results'].values()}, {42907})
        self.assertEqual(summary['meta']['rtl_sha256'], {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                         for p in sorted((ROOT/'src').glob('*.v'))})
        self.assertIn('6fef0f3e70eb4c857500e3d697cd0017ab54d4dc8481fc014e9997bc3600ed24', readme)
        self.assertFalse(list((RELIABILITY/'golden'/'synth-20261128').glob('*.v')))

    def test_spice_summary(self):
        summary, readme = self.load('spice-20261128')
        self.assertEqual(summary['tests'], 65)
        compare = summary['compare']
        self.assertEqual(compare['transient']['max_abs_rel'], 0.015)
        self.assertEqual(compare['dc_curves']['max_abs_rel'], 0.0367)
        self.assertEqual(compare['metrics']['max_abs_rel'], 0.0062)
        self.assertEqual(compare['gpio_transient_max_abs_rel'], 0.0092)
        self.assertIn('TEMP', readme)

    def test_pex_reference_readme(self):
        text = (RELIABILITY/'golden'/'pex-reference-20261128'/'README.md').read_text(encoding='utf-8')
        for needle in ('bd605b58e450ad173a32afebbde067a37a85562501b4b0e26680f7a87bbf57cc', 'QUERY XRC', 'Quantus',
                       'EXTGRMP-354', '164', '저장소 밖'):
            self.assertIn(needle, text)
        self.assertFalse(list((RELIABILITY/'golden'/'pex-reference-20261128').glob('*.spef')))
        self.assertFalse(list((RELIABILITY/'golden'/'pex-reference-20261128').glob('*.spf')))

    def test_every_evidence_folder_has_a_readme(self):
        for folder in (RELIABILITY/'golden').iterdir():
            if folder.is_dir():
                self.assertTrue((folder/'README.md').is_file(), folder.name)


class WaveTwoMutationTests(unittest.TestCase):
    """Second mutation golden: kit part rebuilt in CI, core windows checkpoint-only."""
    GOLDEN = {'meta': dict(MUTATION_META, generator='scripts/asic/mutate_v2.py', seed=20261129,
                           sources={'s.gds': 'k'*64, 'core.gds': 'c'*64}, checkpoint_only_sources=['core.gds']),
              'mutations': [mutation('kit.gds', fired={'R': 1}), dict(mutation('w0.gds'), source='core.gds'),
                            dict(mutation('w1.gds', fired={'R': 2}), source='core.gds')]}

    def geometry(self, *names):
        return {m['gds']: {'geometry_sha256': m['geometry_sha256'], 'polygons': m['polygons']}
                for m in self.GOLDEN['mutations'] if m['gds'] in names}

    def test_checkpoint_only_records_are_counted_not_compared_nor_failed(self):
        unavailable = {'core.gds': '`core.gds` not given'}
        self.assertEqual(reliability.mutation_targets(self.GOLDEN, self.geometry('kit.gds'), unavailable), ['kit.gds'])
        r = reliability.compare_mutations(self.GOLDEN, self.geometry('kit.gds'), {'kit.gds': drc(R=1)}, ['R'], unavailable)
        self.assertEqual(r['status'], 'pass')
        self.assertEqual(r['compared_gds'], 1)
        self.assertEqual([m['verdict'] for m in r['mutations']], ['match', 'not_regenerated', 'not_regenerated'])
        summary = reliability.mutation_summary(r, self.GOLDEN['meta'])
        self.assertIn('2개: `core.gds` not given', summary)

    def test_core_given_is_compared_and_its_geometry_must_match(self):
        geometry = self.geometry('kit.gds', 'w0.gds', 'w1.gds')
        r = reliability.compare_mutations(self.GOLDEN, geometry, {g: drc(R=n) for g, n in
                                          (('kit.gds', 1), ('w0.gds', 0), ('w1.gds', 3))}, ['R'], {})
        self.assertEqual((r['status'], r['compared_gds']), ('pass', 3))
        geometry['w1.gds'] = {'geometry_sha256': 'other', 'polygons': 10}
        r = reliability.compare_mutations(self.GOLDEN, geometry, {'kit.gds': drc(R=1), 'w0.gds': drc(R=0)}, ['R'], {})
        self.assertEqual(r['status'], 'fail')
        self.assertEqual(r['mutations'][2]['verdict'], 'geometry_changed')

    def test_import_keeps_v2_records_and_meta(self):
        manifest = {'seed': 20261129, 'generator': 'mutate_v2.py', 'generator_sha256': 'f'*64,
                    'sources': {'s.gds': 'k'*64, 'core.gds': 'c'*64}, 'params': {'windows': 28},
                    'records': [{'gds': 'a.gds', 'source': 's.gds', 'cell': 'A', 'kind': 'kit_cell', 'variant': 1,
                                 'op': 'edge_move', 'params': {'delta_um': 0.01}, 'draws': 2, 'layer': '32/0',
                                 'shape_before_um': [[0, 0], [0, 1], [1, 1], [1, 0]], 'xor_area_um2': 0.01},
                                {'gds': 'w.gds', 'source': 'core.gds', 'cell': 'top', 'kind': 'core_window',
                                 'window': 'core_w00', 'window_um': [0, 0, 30, 30], 'variant': 0, 'op': 'original'}]}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp/'counts.csv').write_text('gds,rules_fired,calibre_exit,run_ms,calibre_error\na.gds,R:1,0,1,\nw.gds,,0,1,\n')
            (tmp/'manifest.json').write_text(json.dumps(manifest))
            (tmp/'geometry.json').write_text(json.dumps({'a.gds': {'geometry_sha256': 'ga', 'polygons': 3},
                                                         'w.gds': {'geometry_sha256': 'gw', 'polygons': 9}}))
            args = (tmp/'counts.csv', tmp/'manifest.json', tmp/'geometry.json', MUTATION_META)
            g = reliability.import_mutations(*args, 'scripts/asic/mutate_v2.py', ['core.gds'])
            for bad in (('scripts/asic/other.py', []), ('scripts/asic/mutate_v2.py', ['missing.gds'])):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    reliability.import_mutations(*args, *bad)
        a, w = g['mutations']
        self.assertEqual({k: a[k] for k in manifest['records'][0]}, manifest['records'][0])
        self.assertEqual((a['geometry_sha256'], a['rules_fired']), ('ga', {'R': 1}))
        self.assertEqual(w['window_um'], [0, 0, 30, 30])
        meta = g['meta']
        self.assertEqual((meta['generator'], meta['seed'], meta['sources'], meta['params']),
                         ('scripts/asic/mutate_v2.py', 20261129, manifest['sources'], {'windows': 28}))
        self.assertEqual(meta['original_generator_sha256'], 'f'*64)
        self.assertEqual(meta['checkpoint_only_sources'], ['core.gds'])

    def test_all_goldens_are_checked_and_combined(self):
        one = {'meta': MUTATION_META, 'mutations': [mutation('ok.gds', fired={'R': 1})]}

        def fake_check(path, out, *args):
            Path(out).mkdir(parents=True)
            name = Path(path).parent.name
            fired = 0 if name == 'bad' else 1
            r = reliability.compare_mutations(one, {'ok.gds': {'geometry_sha256': 'g-ok.gds', 'polygons': 10}},
                                              {'ok.gds': drc(R=fired)}, ['R'])
            r.update(wall_seconds=1.0, klayout_version='K')
            (Path(out)/'summary.md').write_text(reliability.mutation_summary(r, one['meta']), encoding='utf-8')
            return r
        for names, code in ((['a', 'b'], 0), (['a', 'bad'], 1), ([], 1)):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as tmp, \
                    mock.patch.object(reliability, 'check_mutations', side_effect=fake_check), \
                    mock.patch.object(reliability, 'klayout_version', return_value='K'):
                tmp = Path(tmp)
                got = reliability.check_all_mutations([tmp/n/'golden.json' for n in names], tmp/'out')
                result = json.loads((tmp/'out'/'result.json').read_text(encoding='utf-8'))
                self.assertEqual(got, code)
                self.assertEqual(sorted(result['goldens']), names)
                summary = (tmp/'out'/'summary.md').read_text(encoding='utf-8')
                for n in names:
                    self.assertIn(f'| `{n}` |', summary)

    def test_gds_dir_needs_one_golden(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            reliability.main(['check-mutations', '--golden', 'a/golden.json', '--golden', 'b/golden.json',
                              '--gds-dir', 'x', '--out', 'o'])


class WaveTwoGoldenFileTests(unittest.TestCase):
    FOLDER = RELIABILITY/'golden'/'drc-mutations-20261128b'

    def test_golden(self):
        g = json.loads((self.FOLDER/'golden.json').read_text(encoding='utf-8'))
        meta = g['meta']
        self.assertEqual({k: meta[k] for k in ('calibre_version', 'deck_sha256', 'run_date', 'klayout_version')},
                         {k: MUTATION_META[k] for k in ('calibre_version', 'deck_sha256', 'run_date', 'klayout_version')})
        self.assertEqual(meta['corpus_tarball_sha256'], 'ecf0263db5aa2ff527d26d4a5b07b8aebb47360f5036e1e853dc8d402784d5a1')
        self.assertEqual((meta['seed'], meta['generator']), (20261129, 'scripts/asic/mutate_v2.py'))
        self.assertEqual(meta['sources']['v_ternary8_top.gds'],
                         'fa6ab910b7f03fd4c966c9c19b2455fd7f26297614c1f20ccb221fed9b09ea93')
        self.assertEqual(meta['checkpoint_only_sources'], ['v_ternary8_top.gds'])
        m = g['mutations']
        self.assertEqual(len(m), 800)
        self.assertEqual(sum(x['kind'] == 'kit_cell' for x in m), 604)
        self.assertEqual(sum(x['source'] == 'v_ternary8_top.gds' for x in m), 196)
        self.assertEqual(sum(x['calibre'] == 'refused' for x in m), 0)
        empty = {x['gds']: x['rules_fired'] for x in m if x['polygons'] == 0}
        self.assertEqual(empty, {'0348-CONT-v1.gds': {'1.PWL.bad1': 1}, '0350-CONT-v3.gds': {'1.PWL.bad1': 1}})
        self.assertTrue(all(re.fullmatch('[0-9a-f]{64}', x['geometry_sha256']) for x in m))

    def test_empty_tops_are_excluded_because_calibre_fired_no_verified_rule(self):
        g = json.loads((self.FOLDER/'golden.json').read_text(encoding='utf-8'))
        empty = [x for x in g['mutations'] if x['polygons'] == 0]
        verified = reliability.verified_rules(json.loads(RULES_JSON.read_text(encoding='utf-8')))
        geometry = {x['gds']: {'geometry_sha256': x['geometry_sha256'], 'polygons': 0} for x in empty}
        r = reliability.compare_mutations({'meta': g['meta'], 'mutations': empty}, geometry, {}, verified)
        self.assertEqual([x['verdict'] for x in r['mutations']], ['excluded', 'excluded'])

    def test_readme_without_server_details(self):
        text = (self.FOLDER/'README.md').read_text(encoding='utf-8')
        for needle in ('v2023.4_17.10', drc_catalog.SOURCE_SHA, 'ecf0263db5aa2ff527d26d4a5b07b8aebb47360f5036e1e853dc8d402784d5a1',
                       '20261129', 'scripts/asic/mutate_v2.py', '--core-gds', '2026-11-28'):
            self.assertIn(needle, text)
        self.assertIsNone(SERVER_TRACE.search(text))
        self.assertIsNone(LOCAL_PATH.search(text))
        data = (self.FOLDER/'golden.json').read_text(encoding='utf-8')
        self.assertIsNone(SERVER_TRACE.search(data))
        self.assertIsNone(LOCAL_PATH.search(data))

def sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


class MutationRebuildTests(unittest.TestCase):
    """`_rebuild` sha guards, with the KLayout generators mocked (runs without KLayout)."""
    STD, GPIO, CORE = b'std library', b'gpio library', b'core gds'

    def setUp(self):
        import mutate_v2
        self.mutate_v2 = mutate_v2
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.kit = tmp/'kit'
        for relative, data in ((mutate_v2.STD_GDS, self.STD), (mutate_v2.GPIO_GDS, self.GPIO)):
            (self.kit/relative).parent.mkdir(parents=True, exist_ok=True)
            (self.kit/relative).write_bytes(data)
        self.core, self.other = tmp/'core.gds', tmp/'other.gds'
        self.core.write_bytes(self.CORE)
        self.other.write_bytes(b'core from another RTL')
        self.std_name, self.gpio_name = Path(mutate_v2.STD_GDS).name, Path(mutate_v2.GPIO_GDS).name
        self.golden = {'meta': {'generator': 'scripts/asic/mutate_v2.py', 'seed': 20261129,
                                'checkpoint_only_sources': ['v_ternary8_top.gds'],
                                'sources': {self.std_name: sha(self.STD), self.gpio_name: sha(self.GPIO),
                                            'v_ternary8_top.gds': sha(self.CORE)}}}
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def fake_generate(self, kit, out, seed, core, klayout='klayout', **kw):
        self.calls.append(core)
        sources = {self.std_name: sha((Path(kit)/self.mutate_v2.STD_GDS).read_bytes()),
                   self.gpio_name: sha((Path(kit)/self.mutate_v2.GPIO_GDS).read_bytes())}
        if core:
            sources[Path(core).name] = sha(Path(core).read_bytes())
        return {'sources': dict(sources, **self.manifest_sources)}

    manifest_sources = {}

    def rebuild(self, core=None, golden=None):
        with mock.patch.object(self.mutate_v2, 'run_generate', side_effect=self.fake_generate):
            return reliability._rebuild(golden or self.golden, Path(self.tmp.name)/'corpus', self.kit, core, 'klayout')

    def test_without_core_the_windows_are_not_regenerated(self):
        self.assertEqual(list(self.rebuild()), ['v_ternary8_top.gds'])
        self.assertEqual(self.calls, [None])

    def test_core_with_the_golden_sha_is_generated_and_compared(self):
        self.assertEqual(self.rebuild(self.core), {})
        self.assertEqual(self.calls, [self.core])

    def test_core_with_another_sha_is_not_regenerated_and_names_both_hashes(self):
        reason = self.rebuild(self.other)['v_ternary8_top.gds']
        self.assertIn(sha(self.other.read_bytes()), reason)
        self.assertIn(sha(self.CORE), reason)
        self.assertEqual(self.calls, [None])

    def test_kit_source_with_another_sha_stops_before_generating(self):
        (self.kit/self.mutate_v2.GPIO_GDS).write_bytes(b'patched gpio')
        with self.assertRaises(reliability.SourceMismatch) as caught:
            self.rebuild()
        self.assertIn(sha(b'patched gpio'), str(caught.exception))
        self.assertEqual(self.calls, [])

    def test_generated_manifest_with_another_kit_sha_fails(self):
        self.manifest_sources = {self.std_name: 'f'*64}
        with self.assertRaises(reliability.SourceMismatch):
            self.rebuild()

    def test_unknown_generator_fails(self):
        golden = {'meta': dict(self.golden['meta'], generator='scripts/asic/mutate_v9.py')}
        with self.assertRaises(ValueError):
            self.rebuild(golden=golden)
        self.assertEqual(self.calls, [])

    def wave_one(self):
        return {'meta': {'generator': 'scripts/asic/mutate.py', 'seed': 20261128, 'per_cell': 6,
                         'sources': [self.std_name, self.gpio_name]}}

    def test_wave_one_generator_is_called_with_its_seed(self):
        import mutate
        pinned = {self.std_name: sha(self.STD), self.gpio_name: sha(self.GPIO)}
        with mock.patch.object(mutate, 'generate') as generate, \
                mock.patch.object(reliability, 'KIT_SOURCE_SHA256', pinned):
            self.assertEqual(reliability._rebuild(self.wave_one(), Path(self.tmp.name)/'c', self.kit, None,
                                                  'klayout'), {})
        generate.assert_called_once_with(self.kit, Path(self.tmp.name)/'c', 20261128, 6, 'klayout')

    def test_wave_one_checks_the_kit_before_generating(self):  # final review: same guard as wave 2
        import mutate
        self.assertEqual(reliability.KIT_SOURCE_SHA256[self.std_name], self.golden_v2_sha('std'))
        with mock.patch.object(mutate, 'generate') as generate, self.assertRaises(reliability.SourceMismatch):
            reliability._rebuild(self.wave_one(), Path(self.tmp.name)/'c', self.kit, None, 'klayout')
        generate.assert_not_called()

    def golden_v2_sha(self, which):
        meta = json.loads((RELIABILITY/'golden'/'drc-mutations-20261128b'/'golden.json').read_text(
            encoding='utf-8'))['meta']
        return meta['sources'][self.std_name if which == 'std' else self.gpio_name]

    def test_missing_core_gds_is_a_failure_not_a_traceback(self):
        with self.assertRaises(reliability.CorpusError) as caught:
            self.rebuild(Path(self.tmp.name)/'no-such-core.gds')
        self.assertIn('--core-gds', str(caught.exception))
        self.assertEqual(self.calls, [])

    def test_golden_without_meta_keys_is_a_clear_error(self):
        for key in ('seed', 'sources'):
            meta = dict(self.golden['meta'])
            del meta[key]
            with self.subTest(key=key), self.assertRaises(reliability.CorpusError) as caught:
                self.rebuild(golden={'meta': meta})
            self.assertIn(key, str(caught.exception))
        meta = dict(self.golden['meta'], sources={self.std_name: sha(self.STD)})
        with self.assertRaises(reliability.CorpusError):
            self.rebuild(golden={'meta': meta})

    def test_kit_mismatch_writes_a_failing_result_instead_of_a_traceback(self):
        (self.kit/self.mutate_v2.STD_GDS).write_bytes(b'another kit')
        out = Path(self.tmp.name)/'out'
        (Path(self.tmp.name)/'golden'/'g').mkdir(parents=True)
        golden_path = Path(self.tmp.name)/'golden'/'g'/'golden.json'
        golden_path.write_text(json.dumps(dict(self.golden, mutations=[mutation('a.gds')])), encoding='utf-8')
        rules_file(Path(self.tmp.name)/'drc-rules.json', R='verified')
        with mock.patch.object(self.mutate_v2, 'run_generate', side_effect=self.fake_generate), \
                mock.patch.object(reliability, 'klayout_version', return_value='K'), \
                contextlib.redirect_stdout(io.StringIO()):
            code = reliability.main(['check-mutations', '--golden', str(golden_path), '--kit', str(self.kit),
                                     '--out', str(out), '--rules', str(Path(self.tmp.name)/'drc-rules.json')])
        self.assertEqual(code, 1)
        self.assertEqual(self.calls, [])
        result = json.loads((out/'g'/'result.json').read_text(encoding='utf-8'))
        self.assertEqual(result['status'], 'fail')
        self.assertIn('키트', result['error'])
        self.assertEqual(json.loads((out/'result.json').read_text(encoding='utf-8'))['status'], 'fail')
        summary = (out/'summary.md').read_text(encoding='utf-8')
        self.assertIn('키트 원본', summary)
        self.assertIn(sha(b'another kit'), summary)

if __name__ == '__main__':
    unittest.main()
