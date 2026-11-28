"""Kit ANT deck port (scripts/asic/drc_antenna.py): deck lines, ratio arithmetic at the limits, hierarchy.

The arithmetic tests run with plain Python. The geometry tests run KLayout (`klayout -b`) and skip where it
is not installed; CI runs them.
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
sys.path.insert(0, str(ASIC))
sys.path.insert(0, str(ROOT/'scripts'))
import drc_antenna  # noqa: E402
from drc_antenna import RULES, fires, user_units, precision  # noqa: E402
from drc_cases import cases  # noqa: E402
import reliability  # noqa: E402

GOLDEN = ROOT/'verification'/'reliability'/'golden'/'ant-fixtures-20261128'/'golden.json'
S = 1000  # precision for 0.001 um GDS (deck PRECISION 1000)


def perimeter(dbu):
    return user_units(dbu, S, 'perimeter')


def area(dbu2):
    return user_units(dbu2, S)


class DeckTests(unittest.TestCase):
    def test_twelve_rulechecks_at_the_deck_lines(self):
        import drc_cases_pending_c1b
        self.assertEqual({name: spec['line'] for name, spec in RULES.items()}, drc_cases_pending_c1b.ANT_LINES)
        for name, spec in RULES.items():
            # the bracketed expression sits inside the RULECHECK block
            self.assertTrue(spec['line'] < spec['expression_line'] < spec['line']+12, name)
            self.assertTrue(set(spec['diode_connect'] or []) <= set(spec['connect']), name)

    def test_diode_area_uses_only_the_connects_above_it(self):
        # ANT_02_x/03_1/05_x: ACTIVE_DIODE is defined before CONNECT MET1 POLY; ANT_03_2/03_3/06_0x after it.
        poly = drc_antenna.M1_POLY
        for name in ('ANT_02_1', 'ANT_02_2', 'ANT_02_3', 'ANT_03_1', 'ANT_05_1', 'ANT_05_2'):
            self.assertNotIn(poly, RULES[name]['diode_connect'], name)
        for name in ('ANT_03_2', 'ANT_03_3', 'ANT_06_01', 'ANT_06_02'):
            self.assertIn(poly, RULES[name]['diode_connect'], name)

    def test_precision_follows_the_gds_dbu(self):
        self.assertEqual(precision(.001), 1000)
        self.assertEqual(precision(.0005), 2000)
        with self.assertRaisesRegex(ValueError, 'dbu cannot represent'):
            precision(.003)


class LimitTests(unittest.TestCase):
    """Each RULECHECK at its limit (no violation: the deck compares with `>`) and 0.01 um above it.

    Values are the integer dbu of the kit fixtures (golden/ant-fixtures-20261128)."""

    def check(self, rule, measured, gate, diode, expected):
        self.assertEqual(fires(rule, measured, gate, diode), expected, (rule, measured, gate, diode))

    def test_ratio_checks(self):
        for rule, measure, at, above, gate in [
                ('ANT_01', 'perimeter', 800000, 800020, 1000000),     # 0.25 * P / Ag > 200
                ('ANT_02_1', 'perimeter', 800000, 800020, 1050000),   # 0.525 * P / Ag > 400
                ('ANT_02_2', 'perimeter', 800000, 800020, 1050000),
                ('ANT_02_3', 'perimeter', 800000, 800020, 1740000),   # 0.870 * P / Ag > 400
                ('ANT_04', 'area', 3600000, 3606000, 360000),         # A(CONT AND POLY) / Ag > 10
                ('ANT_05_1', 'area', 6400000, 6408000, 320000),       # A(VIA1) / Ag > 20
                ('ANT_05_2', 'area', 6400000, 6408000, 320000)]:
            with self.subTest(rule=rule):
                self.check(rule, user_units(at, S, measure), area(gate), 0.0, False)
                self.check(rule, user_units(above, S, measure), area(gate), 0.0, True)
                self.check(rule, user_units(above, S, measure), 0.0, 0.0, False)  # !!AREA(GATE) = 0

    def test_without_diode_checks_skip_nets_with_a_diode(self):
        for rule, measure, value, gate in [('ANT_02_1', 'perimeter', 1600000, 1050000),
                                           ('ANT_05_1', 'area', 9600000, 320000)]:
            with self.subTest(rule=rule):
                self.check(rule, user_units(value, S, measure), area(gate), 0.0, True)
                self.check(rule, user_units(value, S, measure), area(gate), area(1000000), False)

    def test_diode_limit_checks(self):
        for rule, at, above, gate in [('ANT_03_1', 1040000, 1040020, 210000),    # 0.525P - Ag(400Ad + 2200) > 0
                                      ('ANT_03_2', 1040000, 1040020, 210000),
                                      ('ANT_03_3', 19000000, 19002000, 435000)]:  # 0.870P - Ag(8000Ad + 30000)
            with self.subTest(rule=rule):
                self.check(rule, perimeter(at), area(gate), 1.0, False)
                self.check(rule, perimeter(above), area(gate), 1.0, True)
                self.check(rule, perimeter(above), area(gate), 0.0, False)  # *_WITH_DIODE is empty
                self.check(rule, perimeter(above), area(gate), 2.0, False)  # a larger diode raises the limit

    def test_ant06_equality_fires_like_calibre(self):
        # 123 vias 0.8x0.8 + one 0.5x0.89: 79.165 um2; Ag 0.5, Ad 1.0: limit 0.5*(83.33+75) = 79.165 exactly
        # in decimal, but 83.33 is not a binary number: the deck expression is 1.4e-14 > 0 (Calibre: 124).
        for rule in ('ANT_06_01', 'ANT_06_02'):
            with self.subTest(rule=rule):
                self.check(rule, area(79165000), area(500000), area(1000000), True)
                self.check(rule, area(79160000), area(500000), area(1000000), False)   # 0.01 um below
                self.check(rule, area(79165000), area(500000), 0.0, False)            # no diode: ANT_05 territory
                self.check(rule, area(32000000), area(320000), area(300000), True)    # 83.33 literal, not 250/3
        # x 1e-6 would land exactly on the limit and miss Calibre's violation; dividing is what matches.
        self.assertEqual(79165000*1e-6 - (.5*((1.0*83.33)+75)), 0.0)
        self.assertGreater(79165000/1e6 - (.5*((1.0*83.33)+75)), 0.0)


class FixtureDataTests(unittest.TestCase):
    def test_moved_fixtures_are_the_calibre_ones(self):
        ant = [c for c in cases() if c['rule'] in RULES]
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        self.assertEqual(golden['meta']['deck_sha256'], drc_antenna.ANT_SOURCE_SHA)
        self.assertEqual([reliability.case_sha256(c) for c in ant], [e['case_sha256'] for e in golden['fixtures']])
        self.assertEqual([c['fail'] for c in ant], [e['calibre'] == 'fired' for e in golden['fixtures']])
        self.assertEqual(len(ant), 102)
        # every RULECHECK has a violating fixture in a rotated, mirrored child cell
        self.assertEqual({c['rule'] for c in ant if c['hierarchy'] and c['fail']}, set(RULES))

    def test_flow_requires_antenna_checks(self):
        from asic.flow import CORE_CHECKS, CHIP_CHECKS, UNVERIFIED, exit_status, load_allowed
        self.assertIn('asic-antenna', CORE_CHECKS)
        self.assertIn('asic-chip-antenna', CHIP_CHECKS)
        allowed = load_allowed(UNVERIFIED)
        self.assertFalse({'asic-antenna', 'asic-chip-antenna'} & allowed)
        checks = {name: {'status': 'pass'} for name in CORE_CHECKS | CHIP_CHECKS}
        checks.update({name: {'status': 'unsupported'} for name in allowed})
        self.assertEqual(exit_status(checks, target='chip', allowed=allowed), 0)
        for name in ('asic-antenna', 'asic-chip-antenna'):
            for status in ('unsupported', 'fail'):
                with self.subTest(check=name, status=status):
                    self.assertEqual(exit_status(dict(checks, **{name: {'status': status}}), target='chip',
                                                 allowed=allowed), 1)


# Runs inside KLayout: SSC_TEST_CASES = [{name, rules, cells: {cell: shapes}, instances: [[parent, child, rot,
# mirror, x, y]]}], shapes as in drc_cases.py ([layer, box] or [layer, points]); the top cell is 'top'.
BATCH = '''
import json, os, sys
sys.path.insert(0, os.environ['SSC_TEST_ASIC'])
import pya
from drc_antenna import check
result = {}
for case in json.loads(os.environ['SSC_TEST_CASES']):
    layout = pya.Layout()
    layout.dbu = .001
    cells = {'top': layout.create_cell('top')}
    for name in case['cells']:
        cells.setdefault(name, layout.create_cell(name))
    for name, shapes in case['cells'].items():
        for layer, shape in shapes:
            target = cells[name].shapes(layout.layer(layer, 0))
            if isinstance(shape[0], list):
                target.insert(pya.DPolygon([pya.DPoint(*p) for p in shape]))
            else:
                target.insert(pya.DBox(*shape))
    for parent, child, rot, mirror, x, y in case['instances']:
        cells[parent].insert(pya.DCellInstArray(cells[child].cell_index(), pya.DCplxTrans(1, rot, mirror, x, y)))
    rules = check(layout, cells['top'], case['rules'])['rules']
    result[case['name']] = {rule: [rules[rule]['errors'], rules[rule]['first_boxes_um']] for rule in case['rules']}
with open(os.environ['SSC_TEST_OUT'], 'w') as stream:
    json.dump(result, stream)
'''


def run_cases(batch_cases):
    with tempfile.TemporaryDirectory() as tmp:
        script, out = Path(tmp)/'batch.py', Path(tmp)/'out.json'
        script.write_text(BATCH, encoding='utf-8')
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1', SSC_TEST_ASIC=str(ASIC),
                   SSC_TEST_CASES=json.dumps(batch_cases), SSC_TEST_OUT=str(out))
        done = subprocess.run(['klayout', '-b', '-r', str(script)], env=env, capture_output=True, text=True,
                              timeout=300)
        if done.returncode or not out.is_file():
            raise AssertionError(done.stdout+done.stderr)
        return json.loads(out.read_text(encoding='utf-8'))


def from_fixture(index, case):
    """drc_cases.py fixture as drc_fixture_test.py writes it (hierarchy: leaf in middle, rotated and mirrored)."""
    spec = {'name': f'{index:04}', 'rules': [case['rule']], 'instances': []}
    if case['hierarchy']:
        spec['cells'] = {'leaf': case['shapes'], 'middle': []}
        spec['instances'] = [['middle', 'leaf', 90, True, 30, 40], ['top', 'middle', 0, False, 0, 0]]
    else:
        spec['cells'] = {'top': case['shapes']}
    return spec


# A transistor as in the kit fixtures (drc_cases.py ANT section): gate 0.5 x 2.1 (1.05 um2), poly head with a
# contact at y 3.95..4.55. M1 3 wide from y 3.6: perimeter 2(3+H), 0.525 P / 1.05 = 400 at H = 397.
MOS = [[11, [-1.5, 0, 2, 2.1]], [14, [-2, -.5, 2.5, 2.6]], [12, [0, -.6, .5, 4.1]], [12, [-.3, 3.7, .8, 4.8]],
       [31, [-.05, 3.95, .55, 4.55]]]


def wire(height):
    return [[32, [-.5, 3.6, 2.5, 3.6+height]]]


@unittest.skipUnless(shutil.which('klayout'), 'KLayout is not installed')
class KLayoutTests(unittest.TestCase):
    def test_every_ant_fixture_matches_its_calibre_verdict(self):
        fixtures = [(i, c) for i, c in enumerate(cases()) if c['rule'] in RULES]
        result = run_cases([from_fixture(i, c) for i, c in fixtures])
        for index, case in fixtures:
            errors, boxes = result[f'{index:04}'][case['rule']]
            with self.subTest(fixture=index, rule=case['rule'], label=case['label']):
                self.assertEqual(errors > 0, case['fail'])
                if case['hierarchy'] and errors:
                    # rotation, mirror and offset of the child reach the reported box
                    self.assertTrue(all(box[0] > 20 and box[1] > 30 for box in boxes), boxes)

    def test_net_across_cells_and_instances(self):
        # transistor and wire are sibling cells under a rotated, mirrored group: one net across three cells.
        def case(name, height, second=False):
            instances = [['group', 'mos', 0, False, 0, 0], ['group', 'wire', 0, False, 0, 0],
                         ['top', 'group', 90, True, 30, 40]]
            if second:  # a second gate on the same wire, 200 um along it: gate area doubles, ratio halves
                instances.insert(1, ['group', 'mos', 0, False, 0, 200])
            return {'name': name, 'rules': ['ANT_02_1', 'ANT_03_1'], 'instances': instances,
                    'cells': {'mos': MOS, 'wire': wire(height), 'group': []}}
        result = run_cases([case('at-limit', 397), case('above', 397.01), case('above-two-gates', 397.01, True),
                            case('far-two-gates', 797.01, True)])
        self.assertEqual(result['at-limit']['ANT_02_1'][0], 0)
        self.assertEqual(result['above']['ANT_02_1'][0], 1)
        box = result['above']['ANT_02_1'][1][0]
        self.assertTrue(box[0] > 30 and box[1] > 30, box)  # reported in top coordinates
        self.assertEqual(result['above-two-gates']['ANT_02_1'][0], 0)
        self.assertEqual(result['far-two-gates']['ANT_02_1'][0], 1)
        for name in result:  # no diode on the net: the WITH_DIODE check has nothing to measure
            self.assertEqual(result[name]['ANT_03_1'][0], 0, name)

    def test_diode_in_another_cell_protects_the_gate(self):
        # N+ diode 1x1 with a contact under a short M1 strap at the wire's end; the diode sits in its own cell.
        diode = [[11, [1, 300, 2, 301]], [14, [.9, 299.9, 2.1, 301.1]], [31, [1.2, 300.2, 1.8, 300.8]]]
        base = {'rules': ['ANT_02_1', 'ANT_03_1'], 'cells': {'mos': MOS, 'wire': wire(797), 'diode': diode}}
        result = run_cases([
            dict(base, name='no-diode', instances=[['top', 'mos', 0, False, 0, 0], ['top', 'wire', 0, False, 0, 0]]),
            dict(base, name='diode', instances=[['top', 'mos', 0, False, 0, 0], ['top', 'wire', 0, False, 0, 0],
                                               ['top', 'diode', 0, False, 0, 0]])])
        self.assertEqual(result['no-diode']['ANT_02_1'][0], 1)   # ratio 800 > 400
        self.assertEqual(result['diode']['ANT_02_1'][0], 0)      # net has 1 um2 of diode: not WO_DIODE
        self.assertEqual(result['diode']['ANT_03_1'][0], 0)      # 800 < 400 * 1 + 2200


if __name__ == '__main__':
    unittest.main()
