"""Golden results are keyed by the fixture definition, not by GDS bytes."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'/'asic'))
import reliability


class CaseHashTests(unittest.TestCase):
    def test_case_sha_is_stable_and_order_free(self):
        a = {'rule': '8.MET1.W', 'label': 'x', 'dbu': 0.001, 'hierarchy': False, 'shapes': [[[8, 0], [0, 0, 1, 1]]]}
        b = dict(reversed(list(a.items())))
        self.assertEqual(reliability.case_sha256(a), reliability.case_sha256(b))
        self.assertEqual(len(reliability.case_sha256(a)), 64)

    def test_every_fixture_case_hashes(self):
        from drc_cases import cases
        hashes = [reliability.case_sha256(c) for c in cases()]
        self.assertEqual(len(hashes), 427)


if __name__ == '__main__':
    unittest.main()
