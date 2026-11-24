"""Guard omitted checks, commented-out checks, source identity and fixture scope."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from asic.drc_catalog import parse_checks, disabled_checks, compare_rules, validate, assura_labels, CALIBRE, ASSURA, CATALOG
from asic.drc_ports import PORTS
from asic.drc_cases import cases

class SourceParserTests(unittest.TestCase):
    def test_comments_macros_and_quoted_braces_cannot_add_checks(self):
        text = '''// 8.MET1.ANT { ignored }
/* FAKE { 3.PL1.W1 { not a check } } */
TITLE "quoted { brace // ; }"
DMACRO Width_check layer value { INT layer < value }
1.NWL.W {
 @ description with { harmless }
 COPY "quoted }"
 NESTED { COPY A }
}
OFFGRID_MET1{ OFFGRID MET1 10 }
'''
        self.assertEqual(set(parse_checks(text)), {'1.NWL.W', 'OFFGRID_MET1'})
        self.assertEqual(parse_checks(text)['1.NWL.W']['source_line'], 5)

    def test_disabled_checks_are_separate_from_active_checks(self):
        text = '//9.VIA1.bad2 {\n// @ disabled\n// COPY A\n//}\n9.VIA1.W { COPY B }\n'
        self.assertEqual(set(parse_checks(text)), {'9.VIA1.W'})
        self.assertEqual(set(disabled_checks(text)), {'9.VIA1.bad2'})

    def test_duplicate_or_unterminated_source_fails(self):
        for text in ['X {COPY A}\nX {COPY B}', 'X { COPY A', '/* unfinished', 'TITLE "unfinished']:
            with self.assertRaises(ValueError):
                parse_checks(text)

    def test_assura_semicolon_comments_do_not_hide_quoted_labels(self):
        text = ''';errorLayer(A "FAKE: disabled")
offGrid(FVTNi 0.01 "off grid on layer FVTN")
offGrid(FVTPi 0.01 "off grid on layer FVTP")
errorLayer(A "1.NWL.W: quoted ; punctuation") ; end of line
'''
        self.assertEqual(assura_labels(text), {'OFFGRID_FVTN', 'OFFGRID_FVTP', '1.NWL.W'})

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.actual = parse_checks('1.NWL.W { COPY A }\n')
        self.catalog = {'rules': [dict(self.actual['1.NWL.W'], id='1.NWL.W', implementation='geometry_port')],
                        'disabled_rules': {}}

    def test_missing_extra_duplicate_and_reclassified_checks_fail(self):
        compare_rules(self.actual, {}, self.catalog, {'1.NWL.W'})
        for mutate in ['missing', 'extra', 'duplicate', 'reclassified', 'hash', 'line', 'disabled']:
            value = copy.deepcopy(self.catalog)
            if mutate == 'missing': value['rules'] = []
            if mutate == 'extra': value['rules'].append(dict(value['rules'][0], id='UNKNOWN'))
            if mutate == 'duplicate': value['rules'].append(value['rules'][0])
            if mutate == 'reclassified': value['rules'][0]['implementation'] = 'unported'
            if mutate == 'hash': value['rules'][0]['body_sha256'] = '0'*64
            if mutate == 'line': value['rules'][0]['source_line'] = 200
            if mutate == 'disabled': value['disabled_rules'] = {'9.VIA1.bad2': {}}
            with self.assertRaises(ValueError, msg=mutate):
                compare_rules(self.actual, {}, value, {'1.NWL.W'})

    def test_wrong_pdk_is_rejected_before_geometry_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in [CALIBRE, ASSURA]:
                file = root/name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('not the reviewed process')
            with self.assertRaisesRegex(ValueError, 'unreviewed Calibre'):
                validate(root)

    def test_every_executable_port_has_positive_and_negative_fixtures(self):
        fixtures = cases()
        self.assertEqual({case['rule'] for case in fixtures}, set(PORTS))
        catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
        self.assertEqual({r['id'] for r in catalog['rules'] if r['implementation'] == 'geometry_port'}, set(PORTS))
        for name in PORTS:
            applicable = [case for case in fixtures if case['rule'] == name]
            self.assertTrue(any(c['fail'] for c in applicable), name)
            self.assertTrue(any(not c['fail'] for c in applicable), name)
        for rule in catalog['rules']:
            self.assertEqual(rule['fixture_definitions'], sum(c['rule'] == rule['id'] for c in fixtures), rule['id'])
        self.assertFalse(any(r['golden_compared'] for r in catalog['rules']))
