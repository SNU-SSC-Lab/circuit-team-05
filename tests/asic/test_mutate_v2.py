"""Wave-2 mutation generator: same seed, same corpus; the kit part does not depend on the core GDS.

Runs KLayout (`klayout -b`), so it skips where KLayout is not installed. With SSC_TEST_NSPL_KIT set to the
unpacked kit folder it also rebuilds the kit part and compares it with the committed golden.
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
sys.path.insert(0, str(ROOT/'scripts'/'asic'))
import mutate_v2

GOLDEN = ROOT/'verification/reliability/golden/drc-mutations-20261128b/golden.json'
# Runs inside KLayout: a tiny stand-in kit (two libraries) and a dense core in SSC_TEST_OUT.
FAKE = '''
import os
from pathlib import Path
import pya
out = Path(os.environ['SSC_TEST_OUT'])
def library(path, names):
    layout = pya.Layout(); layout.dbu = .001
    lib = layout.create_cell(path.stem)
    for i, name in enumerate(names):
        cell = layout.create_cell(name)
        cell.shapes(layout.layer(11, 0)).insert(pya.DBox(0, 0, 4, 2))
        cell.shapes(layout.layer(32, 0)).insert(pya.DBox(-.5, -.5, 4.5, 1.5))
        cell.shapes(layout.layer(31, 0)).insert(pya.DBox(.7, .7, 1.3, 1.3))
        cell.shapes(layout.layer(31, 0)).insert(pya.DBox(2.7, .7, 3.3, 1.3))
        cell.shapes(layout.layer(12, 0)).insert(pya.DBox(1.8, -1, 2.3, 3))
        lib.insert(pya.DCellInstArray(cell.cell_index(), pya.DTrans(10*i, 0)))
    path.parent.mkdir(parents=True, exist_ok=True)
    layout.write(str(path))
library(out/'kit'/'NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T_PnR/GDS/NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T_std.gds', ['A', 'B'])
library(out/'kit'/'ETRI_NSPL_GPIO_250610.gds', ['P'])
core = pya.Layout(); core.dbu = .001
top = core.create_cell('v_ternary8_top')
for x in range(0, 100, 2):
    for y in range(0, 100, 2):
        top.shapes(core.layer(32, 0)).insert(pya.DBox(x, y, x+1, y+1))
        top.shapes(core.layer(31, 0)).insert(pya.DBox(x+.2, y+.2, x+.8, y+.8))
core.write(str(out/'core.gds'))
'''


def strip(manifest):
    return {k: v for k, v in manifest.items() if k not in ('redraw_reasons', 'core_windows', 'sources', 'records')}


@unittest.skipUnless(shutil.which('klayout'), 'KLayout is not installed')
class WaveTwoGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        (tmp/'fake.py').write_text(FAKE, encoding='utf-8')
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', SSC_TEST_OUT=str(tmp))
        subprocess.run(['klayout', '-b', '-r', str(tmp/'fake.py')], env=env, check=True, capture_output=True, timeout=120)
        cls.kit, cls.core = tmp/'kit', tmp/'core.gds'
        cls.full_a = mutate_v2.run_generate(cls.kit, tmp/'a', core_gds=cls.core)
        cls.full_b = mutate_v2.run_generate(cls.kit, tmp/'b', core_gds=cls.core)
        cls.kit_only = mutate_v2.run_generate(cls.kit, tmp/'c')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_same_seed_gives_the_same_corpus(self):
        self.assertEqual(self.full_a['records'], self.full_b['records'])
        self.assertTrue(any(r['kind'] == 'core_window' for r in self.full_a['records']))
        for record in self.full_a['records']:
            a = (Path(self.tmp.name)/'a'/record['gds']).read_bytes()
            self.assertEqual(a, (Path(self.tmp.name)/'b'/record['gds']).read_bytes(), record['gds'])

    def test_kit_part_does_not_depend_on_the_core(self):
        kit = [r for r in self.full_a['records'] if r['kind'] == 'kit_cell']
        self.assertEqual(self.kit_only['records'], kit)
        self.assertFalse(self.kit_only['core_windows'])
        self.assertEqual(strip(self.kit_only), strip(self.full_a))

    def test_every_record_has_a_geometry_hash(self):
        self.assertTrue(all(len(r['geometry_sha256']) == 64 for r in self.full_a['records']))
        self.assertTrue(all(r['variant'] == 0 or r['op'] != 'original' for r in self.full_a['records']))

    @unittest.skipUnless(os.environ.get('SSC_TEST_NSPL_KIT'), 'set SSC_TEST_NSPL_KIT to compare with the golden')
    def test_kit_part_matches_the_golden(self):
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        manifest = mutate_v2.run_generate(os.environ['SSC_TEST_NSPL_KIT'], Path(self.tmp.name)/'kit-real')
        want = {m['gds']: m['geometry_sha256'] for m in golden['mutations'] if m['kind'] == 'kit_cell'}
        self.assertEqual({r['gds']: r['geometry_sha256'] for r in manifest['records']}, want)


if __name__ == '__main__':
    unittest.main()
