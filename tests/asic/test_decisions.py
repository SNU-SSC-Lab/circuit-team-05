"""A partial or failed build must never become a qualified physical pass."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from asic.flow import outcome, CORE_CHECKS, CHIP_CHECKS
from asic.reference import convert


class OutcomeTests(unittest.TestCase):
    def test_empty_or_partial_success_is_incomplete(self):
        self.assertEqual(outcome({}), 'incomplete')
        self.assertEqual(outcome({'asic-gds': {'status': 'pass'}}), 'incomplete')

    def test_failed_check_overrides_other_success_and_missing_qualification(self):
        self.assertEqual(outcome({'asic-gds': {'status': 'pass'},
                                  'asic-lvs': {'status': 'fail'},
                                  'asic-pex': {'status': 'unsupported'}}), 'fail')
        self.assertEqual(outcome({}, 'tool timed out'), 'fail')

    def test_core_pass_cannot_be_reported_as_chip_pass(self):
        checks = {name: {'status': 'pass'} for name in CORE_CHECKS}
        self.assertEqual(outcome(checks), 'pass')
        self.assertEqual(outcome(checks, target='chip'), 'incomplete')
        checks.update({name: {'status': 'pass'} for name in CHIP_CHECKS})
        checks['asic-chip-lvs'] = {'status': 'unsupported'}
        self.assertEqual(outcome(checks, target='chip'), 'incomplete')
        for name in ['asic-cts', 'asic-drc-subset', 'asic-pex']:
            value = {key: {'status': 'pass'} for key in CORE_CHECKS}
            del value[name]
            self.assertEqual(outcome(value), 'incomplete')


class IndependentReferenceTests(unittest.TestCase):
    def setUp(self):
        self.cdl = '.SUBCKT INVX1 A Y VDD VSS\nM1 Y A VSS VSS nmos4 W=3u L=0.5u\n.ENDS\n'
        self.data = {'modules': {'core': {'ports': {
            'a': {'bits': [2]}, 'y': {'bits': [3]}}, 'cells': {
            'u1': {'type': 'INVX1', 'connections': {'A': [2], 'Y': [3]}}}}}}

    def test_unknown_cell_and_missing_pin_cannot_make_reference(self):
        for change in ['unknown', 'missing']:
            value = json.loads(json.dumps(self.data))
            cell = value['modules']['core']['cells']['u1']
            if change == 'unknown':
                cell['type'] = 'UNDEFINED'
            else:
                del cell['connections']['A']
            with self.assertRaises(ValueError):
                convert(value, self.cdl, 'core')

    def test_unmapped_constant_and_aliased_package_pins_are_rejected(self):
        value = json.loads(json.dumps(self.data))
        value['modules']['core']['cells']['u1']['connections']['A'] = ['1']
        with self.assertRaises(ValueError):
            convert(value, self.cdl, 'core')

    def test_cts_floating_output_is_preserved_but_floating_input_is_rejected(self):
        value = json.loads(json.dumps(self.data))
        value['modules']['INVX1'] = {'ports': {'A': {'direction': 'input'}, 'Y': {'direction': 'output'}}}
        value['modules']['core']['cells']['u1']['connections'].pop('Y')
        self.assertIn('__floating_u1_Y', convert(value, self.cdl, 'core'))
        value['modules']['core']['cells']['u1']['connections'].pop('A')
        with self.assertRaises(ValueError):
            convert(value, self.cdl, 'core')
        value = json.loads(json.dumps(self.data))
        value['modules']['core']['ports']['y']['bits'] = [2]
        with self.assertRaises(ValueError):
            convert(value, self.cdl, 'core')


if __name__ == '__main__':
    unittest.main()
