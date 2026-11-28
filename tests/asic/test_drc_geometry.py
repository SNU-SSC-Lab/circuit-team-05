"""Enclosure ports follow the deck's `ENC a b < v ... OVERLAP`: an inner shape partly outside fails.

These tests run KLayout (`klayout -b`), so they skip where KLayout is not installed.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ASIC = ROOT/'scripts'/'asic'
# Runs inside KLayout: SSC_TEST_CASES = [{name, rules, shapes: [[layer, [x1, y1, x2, y2]], ...]}].
BATCH = '''
import json, os, sys
sys.path.insert(0, os.environ['SSC_TEST_ASIC'])
import pya
from drc_geometry import check
result = {}
for case in json.loads(os.environ['SSC_TEST_CASES']):
    layout = pya.Layout()
    layout.dbu = .001
    top = layout.create_cell('t')
    for layer, box in case['shapes']:
        top.shapes(layout.layer(layer, 0)).insert(pya.DBox(*box))
    rules = check(layout, top, case['rules'])['rules']
    result[case['name']] = {rule: rules[rule]['errors'] for rule in case['rules']}
with open(os.environ['SSC_TEST_OUT'], 'w') as stream:
    json.dump(result, stream)
'''
# (rule, inner layer, outer layers, context shapes); inner is always the box (0, 0, size, size).
ENCLOSURES = [
    ('2.ACT.E2', 11, [2], 2, [[15, [0, 0, 2, 2]], [12, [.5, -1, 1.5, 3]]]),  # PMOS: P+ ACT under POLY1
    ('2.ACT.E3', 11, [2], 2, [[14, [0, 0, 2, 2]]]),  # NTAP: N+ ACT in NWELL without POLY1
    ('7.CONT.E1', 31, [11], 2, []),
    ('7.CONT.E2', 31, [12], 2, []),
    ('7.CONT.E3', 31, [32], 2, []),
    ('13.PAD.E', 37, [32, 34, 36], 80, []),
]


def run_cases(cases, batch=BATCH):
    with tempfile.TemporaryDirectory() as tmp:
        script, out = Path(tmp)/'batch.py', Path(tmp)/'out.json'
        script.write_text(batch, encoding='utf-8')
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1', SSC_TEST_ASIC=str(ASIC),
                   SSC_TEST_CASES=json.dumps(cases), SSC_TEST_OUT=str(out))
        done = subprocess.run(['klayout', '-b', '-r', str(script)], env=env, capture_output=True, text=True, timeout=120)
        if done.returncode or not out.is_file():
            raise AssertionError('KLayout batch failed:\n'+done.stdout+done.stderr)
        return json.loads(out.read_text())


@unittest.skipUnless(shutil.which('klayout'), 'KLayout is not installed')
class EnclosureOverlapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cases = []
        for rule, inner, outers, size, context in ENCLOSURES:
            margin = 3  # far above every enclosure value except 13.PAD.E's 2.5
            inside = [[inner, [0, 0, size, size]]]+context
            for name, box in [('inside', [-margin, -margin, size+margin, size+margin]),
                              # outer covers the left half only: the inner shape crosses its right edge
                              ('partial', [-margin, -margin, size/2, size+margin]),
                              ('outside', [size+5, -margin, 2*size+5, size+margin]),
                              # outer wholly inside the inner shape: no inner edge crosses it
                              ('island', [size/4, size/4, size*3/4, size*3/4])]:
                cases.append(dict(name=rule+'/'+name, rules=[rule],
                                  shapes=inside+[[outer, box] for outer in outers]))
        # 13.PAD.E with a 20 um hole in every metal under the PAD (C9 0449: Calibre 0).
        ring = [[-3.5, -3.5, 83.5, 30], [-3.5, 50, 83.5, 83.5], [-3.5, 30, 30, 50], [50, 30, 83.5, 50]]
        cases.append(dict(name='13.PAD.E/hole', rules=['13.PAD.E'],
                          shapes=[[37, [0, 0, 80, 80]]]+[[m, box] for m in (32, 34, 36) for box in ring]))
        # 0023-AOI22X1-v3 of the 2026-11-28 C2 corpus, reduced: one 0.6 um contact with 0.5 um ACT and
        # 0.6 um MET1 enclosure shifted right by 0.8 um. Calibre fired 7.CONT.E1 and 7.CONT.E3 (2 each);
        # KLayout before the OVERLAP fix fired neither.
        act, met1 = [11, [0, 0, 2.6, 1.6]], [32, [.9, -.1, 2.7, 1.7]]
        for name, x in [('c2-0023-original', 1.5), ('c2-0023-shifted', 2.3)]:
            cases.append(dict(name=name, rules=['7.CONT.E1', '7.CONT.E3'],
                              shapes=[act, met1, [31, [x, .5, x+.6, 1.1]]]))
        cls.result = run_cases(cases)

    def errors(self, name, rule):
        return self.result[name][rule]

    def test_inner_fully_inside_with_margin_passes(self):
        for rule, *_ in ENCLOSURES:
            with self.subTest(rule=rule):
                self.assertEqual(self.errors(rule+'/inside', rule), 0)

    def test_inner_partly_outside_fails(self):
        for rule, *_ in ENCLOSURES:
            with self.subTest(rule=rule):
                self.assertGreater(self.errors(rule+'/partial', rule), 0)

    def test_inner_without_overlap_is_not_measured(self):
        for rule, *_ in ENCLOSURES:
            with self.subTest(rule=rule):
                self.assertEqual(self.errors(rule+'/outside', rule), 0)

    def test_outer_wholly_inside_inner_is_not_overlap(self):
        # Calibre C9 0439-0449: only 2.ACT.E3 fires, because NTAP is clipped to the NWELL
        # island and every NTAP edge lies on an NWELL edge (distance 0).
        for rule, *_ in ENCLOSURES:
            with self.subTest(rule=rule):
                if rule == '2.ACT.E3':
                    self.assertGreater(self.errors(rule+'/island', rule), 0)
                else:
                    self.assertEqual(self.errors(rule+'/island', rule), 0)
        self.assertEqual(self.errors('13.PAD.E/hole', '13.PAD.E'), 0)

    def test_reduced_c2_case_matches_calibre(self):
        self.assertEqual(self.result['c2-0023-original'], {'7.CONT.E1': 0, '7.CONT.E3': 0})
        shifted = self.result['c2-0023-shifted']
        self.assertGreater(shifted['7.CONT.E1'], 0)
        self.assertGreater(shifted['7.CONT.E3'], 0)


# Runs inside KLayout: one MET1 box per case at the given dbu; records errors of the listed rules or the
# ValueError text (SSC_TEST_CASES = [{name, dbu, rules, shapes}]).
DBU_BATCH = '''
import json, os, sys
sys.path.insert(0, os.environ['SSC_TEST_ASIC'])
import pya
from drc_geometry import check
result = {}
for case in json.loads(os.environ['SSC_TEST_CASES']):
    layout = pya.Layout()
    layout.dbu = case['dbu']
    top = layout.create_cell('t')
    for layer, box in case['shapes']:
        top.shapes(layout.layer(layer, 0)).insert(pya.DBox(*box))
    try:
        rules = check(layout, top, case['rules'])['rules']
        result[case['name']] = {rule: rules[rule]['errors'] for rule in case['rules']}
    except ValueError as error:
        result[case['name']] = {'error': str(error)}
with open(os.environ['SSC_TEST_OUT'], 'w') as stream:
    json.dump(result, stream)
'''


@unittest.skipUnless(shutil.which('klayout'), 'KLayout is not installed')
class WidthClassTests(unittest.TestCase):
    """Deck `WITH WIDTH MET1 >= 10` (SPEC 0021): 10.00 um is wide, 9.99 um narrow; coarse dbu fails closed."""

    @classmethod
    def setUpClass(cls):
        cases = []
        for dbu in (.001, .0005, .01):
            for width in (9.99, 10.0):
                # a second wire 0.79 um away: S1 (narrow, 0.8) fires only for 9.99, S2 (wide, 1.0) only for 10.00
                cases.append(dict(name=f'{dbu}/{width}', dbu=dbu, rules=['8.MET1.S1', '8.MET1.S2'],
                                  shapes=[[32, [0, 0, width, 40]], [32, [width+.79, 0, width+2.79, 40]]]))
        cls.result = run_cases(cases, DBU_BATCH)

    def test_width_boundary(self):
        for dbu in ('0.001', '0.0005'):
            with self.subTest(dbu=dbu):
                self.assertGreater(self.result[dbu+'/9.99']['8.MET1.S1'], 0)
                self.assertEqual(self.result[dbu+'/9.99']['8.MET1.S2'], 0)
                self.assertEqual(self.result[dbu+'/10.0']['8.MET1.S1'], 0)
                self.assertGreater(self.result[dbu+'/10.0']['8.MET1.S2'], 0)

    def test_one_dbu_per_grid_step_is_refused(self):
        # 0.01 um dbu cannot place a sizing threshold between 9.99 and 10.00: no verdict, an input error.
        for width in ('9.99', '10.0'):
            with self.subTest(width=width):
                self.assertIn('WITH WIDTH threshold', self.result['0.01/'+width].get('error', ''))


if __name__ == '__main__':
    unittest.main()
