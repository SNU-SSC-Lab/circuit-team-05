"""Cell exclusions must preserve neighbors and fail on unknown/ambiguous cells."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from pdk import abc_liberty

class ABCLibraryTests(unittest.TestCase):
    def test_nested_cell_is_removed_without_its_similarly_named_neighbor(self):
        first = '  cell(INVX1) {\n    pin(A) {\n      direction : input;\n    }\n  }\n'
        second = '  cell(INVX16) {\n    pin(Y) {\n      function : "!A";\n    }\n  }\n'
        content = 'library(test) {\n'+first+second+'}\n'
        self.assertEqual(abc_liberty(content, ['INVX1']), 'library(test) {\n'+second+'}\n')
        self.assertEqual(abc_liberty(content, []), content)

    def test_missing_duplicate_and_injected_names_fail(self):
        cell = '  cell(INVX1) {\n    area : 1;\n  }\n'
        for content, names in [(cell, ['INVX2']), (cell*2, ['INVX1']),
                               (cell, ['INVX1', 'INVX1']), (cell, ['INVX1); exec bad'])]:
            with self.assertRaises(ValueError):
                abc_liberty(content, names)
