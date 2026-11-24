"""Failure decisions, not a second implementation of the layout checker."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'run_physical.py'
spec = importlib.util.spec_from_file_location('physical', SCRIPT)
physical = importlib.util.module_from_spec(spec)
spec.loader.exec_module(physical)


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.cell = dict(name=['demo', 'demo'], devices=[[['nfet', 1]], [['nfet', 1]]],
                         nets=[4, 4], pins=[['D', 'S', 'G'], ['D', 'S', 'G']],
                         badnets=[], badelements=[])
        self.report = 'Final result:\nCircuits match uniquely.\n'

    def check(self, value, report=None):
        return physical.lvs_verdict(self.report if report is None else report, value, 'demo')

    def test_positive_needs_top_and_devices(self):
        self.assertTrue(self.check([self.cell]))

    def test_no_results_are_not_success(self):
        for value in ([], {}, None):
            self.assertFalse(self.check(value))

    def test_intermediate_match_cannot_hide_final_failure(self):
        self.assertFalse(self.check([self.cell], 'Circuits match uniquely.\nFinal result: mismatch'))

    def test_ubuntu_netgen_133_final_line_with_complete_json(self):
        old_report = 'Cell pin lists are equivalent.\nCircuits match uniquely.\n'
        self.assertTrue(self.check([self.cell], old_report))
        self.assertFalse(self.check([], old_report))

    def test_older_report_intermediate_success_is_not_final_success(self):
        report = 'Circuits match uniquely.\nTop level cell failed pin matching.\n'
        self.assertFalse(self.check([self.cell], report))

    def test_netgen_323_exact_dot_terminator_with_complete_json(self):
        report = self.report + '.\n'
        self.assertTrue(self.check([self.cell], report))
        self.assertFalse(self.check([], report))
        self.assertFalse(self.check([dict(self.cell, properties=['wrong W'])], report))
        self.assertFalse(self.check([self.cell], report + 'Top level failed\n'))

    def test_property_and_connectivity_errors_fail(self):
        for key in ('badnets', 'badelements', 'properties'):
            with self.subTest(key=key):
                cell = dict(self.cell, **{key: ['problem']})
                self.assertFalse(self.check([cell]))
        self.assertFalse(self.check([self.cell], self.report + 'Property errors were found.'))

    def test_missing_or_altered_top_fails(self):
        self.assertFalse(self.check([dict(self.cell, name=['child', 'child'])]))
        self.assertFalse(self.check([dict(self.cell, name=['demo', 'wrong'])]))

    def test_empty_cells_fail_even_with_success_text(self):
        self.assertFalse(self.check([dict(self.cell, devices=[[], []])]))

    def test_both_empty_pin_lists_are_not_accepted(self):
        self.assertFalse(self.check([dict(self.cell, pins=[[], []])]))

    def test_pin_net_device_mismatches_fail(self):
        for values in (dict(pins=[['D'], ['S']]), dict(nets=[4, 5]),
                       dict(devices=[[['nfet', 1]], [['nfet', 2]]])):
            self.assertFalse(self.check([dict(self.cell, **values)]))

    def test_unknown_cells_or_blackbox_fail(self):
        self.assertFalse(self.check([self.cell], self.report + 'Black box cell found'))
        self.assertFalse(self.check([dict(name=['demo', 'demo'])]))


class InputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.files = {}
        for key in physical.FILE_KEYS:
            path = self.base / ('demo.mag' if key == 'layout' else key + '.txt')
            path.write_text(key, encoding='utf-8')
            self.files[key] = path
        self.manifest = physical.demo_manifest(self.base, self.files)

    def test_valid_manifest(self):
        design, files, hashes, dependencies = physical.load_manifest(self.manifest)
        self.assertEqual(design['top'], 'demo')
        self.assertEqual(files['layout'], self.files['layout'])
        self.assertEqual(len(hashes), 5)
        self.assertEqual(dependencies, [])

    def test_changed_input_does_not_use_old_hash(self):
        self.files['technology'].write_text('changed')
        with self.assertRaisesRegex(ValueError, 'technology'):
            physical.load_manifest(self.manifest)

    def test_missing_and_empty_inputs_fail(self):
        self.files['schematic'].unlink()
        with self.assertRaisesRegex(ValueError, 'schematic'):
            physical.load_manifest(self.manifest)
        self.files['schematic'].touch()
        with self.assertRaisesRegex(ValueError, 'schematic'):
            physical.load_manifest(self.manifest)

    def test_extra_dependency_hash_is_checked(self):
        with self.manifest.open('a', encoding='utf-8') as target:
            target.write('\n[[dependencies]]\npath = "missing.cdl"\nsha256 = "' + '0' * 64 + '"\n')
        with self.assertRaisesRegex(ValueError, '의존'):
            physical.load_manifest(self.manifest)

    def test_reused_output_is_rejected_without_deleting(self):
        stale = self.base / 'old-success.json'
        stale.write_text('success')
        with self.assertRaisesRegex(ValueError, '비어 있지'):
            physical.fresh(self.base)
        self.assertTrue(stale.is_file())

    def test_incomplete_input_returns_failure_evidence(self):
        self.files['layout'].unlink()
        out = physical.fresh(self.base / 'out')
        result = physical.inspect(self.manifest, out)
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['lvs'], 'not_run')
        self.assertEqual(json.loads((out / 'result.json').read_text(encoding='utf-8'))['status'], 'fail')

    def test_empty_spice_is_not_an_extracted_circuit(self):
        path = self.base / 'empty.spice'
        path.write_text('.subckt demo A B\n.ends demo\n')
        self.assertFalse(physical.spice_has_devices(path, 'demo'))

    def test_report_names_scope(self):
        path = self.base / 'result.json'
        path.write_text(json.dumps(dict(scope='scmos_tool_selftest', tests=[])))
        self.assertIn('실제 5팀 DRC** | **미실행', physical.report(path))


if __name__ == '__main__':
    unittest.main()
