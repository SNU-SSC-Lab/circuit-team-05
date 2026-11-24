"""Tests of the mychip/ checks (scripts/mychip_flow.py) and sdc_period on throwaway git repositories.
No PDK content: the copy test plants an ordinary file and passes its blob id as if it were a PDK
file. Ported from SNU-SSC-Lab/circuit-integration harness/test_flow.py at 60c7acc (pytest ->
unittest; the layout tests stay there). SPEC 0015. No EDA tool needed.

    python -m unittest discover -s tests/pdk -v
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from mychip_flow import check_files, check_signoff, stage_netlists  # noqa: E402
from pdk import sdc_period  # noqa: E402

TOP = 'v_ternary8_top'
CALIBRE_DRC = f"""DRC RULE FILE NAME: drc.cal
LAYOUT PRIMARY: {TOP}
--- TOTAL RULECHECKS EXECUTED = 120
--- TOTAL RESULTS GENERATED = 0 (0)
"""
CALIBRE_LVS = f"""LAYOUT CELL NAME: {TOP}
                   OVERALL COMPARISON RESULTS
                  #       ###################       _   _
                 #        #                 #       *   *
            #   #         #     CORRECT     #         |
             # #          #                 #       \\___/
              #           ###################
"""
HASH = 'ab' * 32


def blob_id(path):
    return subprocess.run(['git', 'hash-object', '--no-filters', str(path)], capture_output=True, text=True, check=True).stdout.strip()


class FlowTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ssc-pdk-flow-')
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)

    def repo(self, files):
        for name, text in files.items():
            path = self.tmp / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode('utf-8'))  # LF on every OS: the blob id must match
        git = ['git', '-C', str(self.tmp), '-c', 'user.name=t', '-c', 'user.email=t@t',
               '-c', 'commit.gpgsign=false', '-c', 'core.autocrlf=false']
        subprocess.run(['git', 'init', '-q', str(self.tmp)], check=True)
        subprocess.run([*git, 'add', '-A'], check=True)
        subprocess.run([*git, 'commit', '-q', '-m', 'x'], check=True)
        return self.tmp

    def signoff(self, drc=None, lvs=None, sha=None):
        base = self.tmp / 'mychip/3-signoff'
        base.mkdir(parents=True, exist_ok=True)
        for name, text in (('drc.rpt', drc), ('lvs.rpt', lvs), (f'{TOP}.gds.sha256', sha)):
            if text is not None:
                (base / name).write_text(text, encoding='utf-8')
        return check_signoff(self.tmp, TOP)

    def test_clean_repository_passes(self):
        team = self.repo({'src/top.v': 'module top; endmodule\n', f'mychip/1-synth/{TOP}.v': 'module x; endmodule\n',
                          'mychip/1-synth/reports/area.rpt': 'area 1\n'})
        result = check_files(team, blobs=set())
        self.assertEqual((result['status'], result['mychip']), ('pass', ['1-synth']))

    def test_skeleton_alone_is_no_stage(self):
        team = self.repo({'mychip/README.md': 'guide\n', 'mychip/.gitignore': '*\n!*/\n!*.md\n!.gitignore\n!.gitkeep\n',
                          'mychip/constraints/.gitkeep': '', 'mychip/1-synth/reports/.gitkeep': ''})
        result = check_files(team, blobs=set())
        self.assertEqual((result['status'], result['mychip']), ('pass', []))

    def test_pdk_copy_is_listed_by_blob_id_not_failed(self):
        team = self.repo({'docs/notes/cells.lib': 'library(x) { }\n' * 100})
        result = check_files(team, blobs={blob_id(team / 'docs/notes/cells.lib')})
        self.assertEqual((result['status'], result['pdk_copies']), ('pass', ['docs/notes/cells.lib']))

    def test_pdk_file_name_is_listed(self):
        name = 'src/lib/NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T_std_tt.lib'
        team = self.repo({name: 'edited copy\n'})
        self.assertEqual(check_files(team, blobs=set())['pdk_copies'], [name])

    def test_team_report_named_after_the_kit_is_not_a_copy(self):
        team = self.repo({'docs/reports/nspl_genus_synthesis_20261116.md': 'report\n'})
        self.assertEqual(check_files(team, blobs=set())['pdk_copies'], [])

    def test_gds_under_mychip_fails(self):
        team = self.repo({f'mychip/3-signoff/{TOP}.gds': 'binary'})
        result = check_files(team, blobs=set())
        self.assertEqual(result['status'], 'fail')
        self.assertIn('not allowed under mychip/', result['problems'][0])

    def test_not_a_git_checkout_is_missing(self):
        self.assertEqual(check_files(self.tmp / 'nowhere', blobs=set())['status'], 'missing')

    def test_signoff_missing_until_files_exist(self):
        self.assertEqual(check_signoff(self.tmp, TOP)['status'], 'missing')

    def test_signoff_clean_calibre_passes(self):
        result = self.signoff(CALIBRE_DRC, CALIBRE_LVS, f'{HASH}  {TOP}.gds\n')
        self.assertEqual(result['status'], 'pass', result)
        self.assertEqual((result['gds_sha256'], result['drc_results']), (HASH, 0))

    def test_signoff_partial_is_missing_not_fail(self):
        self.assertEqual(self.signoff(drc=CALIBRE_DRC)['status'], 'missing')

    def test_signoff_problems_fail(self):
        cases = {
            'DRC errors': (CALIBRE_DRC.replace('= 0 (0)', '= 3 (3)'), CALIBRE_LVS, HASH),
            'LVS mismatch': (CALIBRE_DRC, CALIBRE_LVS.replace('  CORRECT  ', 'INCORRECT'), HASH),
            'report for another cell': (CALIBRE_DRC.replace(TOP, 'other_top'), CALIBRE_LVS, HASH),
            'bad hash file': (CALIBRE_DRC, CALIBRE_LVS, 'not-a-hash'),
            'no verdict at all': ('Rule check summary\n' + TOP, CALIBRE_LVS, HASH),
        }
        for name, (drc, lvs, sha) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.signoff(drc, lvs, sha + '\n')['status'], 'fail')

    def test_assura_verdicts(self):
        result = self.signoff(f'Cell {TOP}\nNo errors found.\n', f'Cell {TOP}\nSchematic and Layout Match\n', HASH)
        self.assertEqual(result['status'], 'pass')

    def test_stage_netlists_and_sdc(self):
        (self.tmp / 'mychip/2-pnr').mkdir(parents=True)
        (self.tmp / f'mychip/2-pnr/{TOP}.v').write_text('module x; endmodule\n')
        (self.tmp / f'mychip/2-pnr/{TOP}.spef').write_text('*SPEF\n')
        found = stage_netlists(self.tmp, TOP)
        self.assertEqual(list(found), ['pnr'])
        self.assertEqual(found['pnr'][1].name, f'{TOP}.spef')
        sdc = self.tmp / 'c.sdc'
        sdc.write_text('# create_clock -period 1\ncreate_clock -name CLK -period 120 [get_ports CLK]\n')
        self.assertEqual(sdc_period(sdc), 120.0)


if __name__ == '__main__':
    unittest.main()
