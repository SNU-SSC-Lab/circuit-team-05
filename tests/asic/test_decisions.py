"""A partial or failed build must never become a qualified physical pass."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from asic.flow import (outcome, exit_status, estimated_sta, load_allowed, CORE_CHECKS, CHIP_CHECKS,
                       UNQUALIFIED_DEFAULT, UNVERIFIED)
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

    def test_experiment_only_allows_the_named_qualification_gaps(self):
        checks = {name: {'status': 'pass'} for name in CORE_CHECKS | CHIP_CHECKS}
        for name in UNQUALIFIED_DEFAULT:
            checks[name] = {'status': 'unsupported'}
        self.assertEqual(exit_status(checks, target='chip'), 1)
        self.assertEqual(exit_status(checks, target='chip', allowed=UNQUALIFIED_DEFAULT), 0)
        for state in ['not_run', 'unsupported', 'fail']:
            checks['asic-lvs'] = {'status': state}
            self.assertEqual(exit_status(checks, target='chip', allowed=UNQUALIFIED_DEFAULT), 1)
        del checks['asic-lvs']
        self.assertEqual(exit_status(checks, target='chip', allowed=UNQUALIFIED_DEFAULT), 1)


class GateTests(unittest.TestCase):
    """--gate: only checks named in unverified.json allows_checks may stay unsupported (SPEC 0019)."""

    def chip(self, **states):
        checks = {name: {'status': 'pass'} for name in CORE_CHECKS | CHIP_CHECKS}
        checks.update({name: {'status': state} for name, state in states.items()})
        return checks

    def test_unsupported_outside_allowed_fails(self):
        checks = self.chip(**{'asic-pex': 'unsupported', 'asic-drc': 'unsupported'})
        self.assertEqual(exit_status(checks, target='chip', allowed=frozenset({'asic-pex'})), 1)
        self.assertEqual(exit_status(checks, target='chip', allowed=frozenset()), 1)

    def test_unsupported_inside_allowed_passes(self):
        checks = self.chip(**{'asic-pex': 'unsupported', 'asic-drc': 'unsupported'})
        self.assertEqual(exit_status(checks, target='chip', allowed=frozenset({'asic-pex', 'asic-drc'})), 0)

    def test_fail_and_not_run_are_never_allowed(self):
        everything = frozenset(CORE_CHECKS | CHIP_CHECKS)
        for state in ['fail', 'not_run']:
            checks = self.chip(**{'asic-pex': state})
            self.assertEqual(exit_status(checks, target='chip', allowed=everything), 1, state)
        self.assertEqual(exit_status(self.chip(), 'tool timed out', target='chip', allowed=everything), 1)

    def test_load_allowed_reads_repository_unverified_list(self):
        self.assertEqual(load_allowed(UNVERIFIED), frozenset(
            {'asic-pex', 'asic-drc', 'asic-chip-lvs', 'asic-chip-timing', 'asic-pinmap'}))

    def test_load_allowed_rejects_unknown_check_names(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'unverified.json'
            path.write_text(json.dumps({'items': [{'id': 'x', 'allows_checks': ['asic-drcc']}]}), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_allowed(path)
            path.write_text(json.dumps({'items': [{'id': 'x'}]}), encoding='utf-8')
            self.assertEqual(load_allowed(path), frozenset())


class RunAsicOptionTests(unittest.TestCase):
    """run_asic.py: strict by default, --experimental keeps the old fixed set, --gate reads unverified.json."""

    def parse(self, *extra):
        import run_asic
        return run_asic.parse(['--pdk', 'kit', '--openroad', 'openroad', '--out', 'out', *extra])

    def test_modes_choose_the_allowed_set(self):
        self.assertEqual(self.parse().allowed, frozenset())
        self.assertEqual(self.parse('--experimental').allowed, UNQUALIFIED_DEFAULT)
        self.assertEqual(self.parse('--gate').allowed, load_allowed(UNVERIFIED))
        self.assertEqual(self.parse('--gate').mode, 'gate')

    def test_gate_and_experimental_are_exclusive(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse('--gate', '--experimental')


class EstimatedStaTests(unittest.TestCase):
    """asic-estimated-sta: setup and hold worst slack must both be >= 0 (SPEC 0019 gate condition)."""

    def log(self, setup, hold):
        return (f'report_worst_slack -max -digits 3\nworst slack max {setup}\n'
                f'report_worst_slack -min -digits 3\nworst slack min {hold}\n')

    def test_non_negative_setup_and_hold_pass(self):
        check = estimated_sta(self.log('38.412', '0.000'))
        self.assertEqual(check['status'], 'pass')
        self.assertEqual(check['slacks_ns'], [38.412, 0.0])

    def test_negative_setup_or_hold_fails(self):
        self.assertEqual(estimated_sta(self.log('-0.010', '1.410'))['status'], 'fail')
        self.assertEqual(estimated_sta(self.log('38.412', '-0.001'))['status'], 'fail')

    def test_missing_slack_fails(self):
        self.assertEqual(estimated_sta('worst slack max 1.0\n')['status'], 'fail')
        self.assertEqual(estimated_sta('')['status'], 'fail')


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
