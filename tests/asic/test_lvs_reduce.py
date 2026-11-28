"""Kit-deck reductions before Netgen LVS must merge only what Calibre merges.

The Netgen cases run the real comparison (lvs_reduce + verification/asic/netgen_setup.tcl)
and skip where Netgen is not installed. Each accepted rewrite has a wrong-circuit twin
that must still fail.
"""
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'scripts/asic'))
import lvs_reduce
import run_physical

SETUP = ROOT/'verification/asic/netgen_setup.tcl'

# Shapes of the kit cells our Netgen path used to reject (layout side as KLayout writes it).
INV_FINGERS = """.SUBCKT INVX2 A VDD Y VSS
M$1 Y A VDD VDD pmos4 L=0.5U W=12U AS=22.2P AD=21P PS=25.4U PD=25U
M$3 Y A VSS VSS nmos4 L=0.5U W=6U AS=11.1P AD=10.5P PS=16.4U PD=16U
.ENDS INVX2
"""
INV_CDL = """.SUBCKT INVX2 A Y VDD VSS
MM0 Y A VSS VSS nmos4 W=3u L=0.5u m=2
MM1 Y A VDD VDD pmos4 W=6u L=0.5u m=2
.ENDS INVX2
"""
NOR_LAYOUT = """.SUBCKT NOR2X1 B A VDD Y VSS
M$1 \\$6 A Y VDD pmos4 L=0.5U W=9U
M$2 VDD B \\$6 VDD pmos4 L=0.5U W=9U
M$3 Y A VSS VSS nmos4 L=0.5U W=3U
M$4 VSS B Y VSS nmos4 L=0.5U W=3U
.ENDS NOR2X1
"""
NOR_CDL = """.SUBCKT NOR2X1 A B Y VDD VSS
MM2 Y B VSS VSS nmos4 W=3u L=0.5u m=1
MM1 Y A VSS VSS nmos4 W=3u L=0.5u m=1
MM3 net05 A VDD VDD pmos4 W=9u L=0.5u m=1
MM0 Y B net05 VDD pmos4 W=9u L=0.5u m=1
.ENDS NOR2X1
"""
TBUF_LAYOUT = """.SUBCKT TBUFX2 EN A Y VDD VSS
M$1 \\$1 EN VDD VDD pmos4 L=0.5U W=6U
M$2 \\$8 A VDD VDD pmos4 L=0.5U W=9U
M$3 Y \\$1 \\$8 VDD pmos4 L=0.5U W=9U
M$4 \\$7 \\$1 Y VDD pmos4 L=0.5U W=9U
M$5 VDD A \\$7 VDD pmos4 L=0.5U W=9U
M$6 VSS EN \\$1 VSS nmos4 L=0.5U W=3U
M$7 \\$10 A VSS VSS nmos4 L=0.5U W=6U
M$8 Y EN \\$10 VSS nmos4 L=0.5U W=6U
M$9 \\$9 EN Y VSS nmos4 L=0.5U W=6U
M$10 VSS A \\$9 VSS nmos4 L=0.5U W=6U
.ENDS TBUFX2
"""
TBUF_CDL = """.SUBCKT TBUFX2 A EN Y VDD VSS
MM5 Y EN net43 VSS nmos4 W=6u L=0.5u m=2
MM7 net43 A VSS VSS nmos4 W=6u L=0.5u m=2
MM0 ENB EN VSS VSS nmos4 W=3u L=0.5u m=1
MM6 net51 A VDD VDD pmos4 W=9u L=0.5u m=2
MM4 Y ENB net51 VDD pmos4 W=9u L=0.5u m=2
MM1 ENB EN VDD VDD pmos4 W=6u L=0.5u m=1
.ENDS TBUFX2
"""
AOI22_CDL = """.SUBCKT AOI22X1 A B C D Y VDD VSS
MM0 Y A n1 VSS nmos4 W=6u L=0.5u m=1
MM1 n1 B VSS VSS nmos4 W=6u L=0.5u m=1
MM2 Y C n2 VSS nmos4 W=6u L=0.5u m=1
MM3 n2 D VSS VSS nmos4 W=6u L=0.5u m=1
MM4 p1 A VDD VDD pmos4 W=9u L=0.5u m=1
MM5 p1 B VDD VDD pmos4 W=9u L=0.5u m=1
MM6 Y C p1 VDD pmos4 W=9u L=0.5u m=1
MM7 Y D p1 VDD pmos4 W=9u L=0.5u m=1
.ENDS AOI22X1
"""


def reduce_text(text):
    with tempfile.TemporaryDirectory() as folder:
        source, target = Path(folder)/'in.spice', Path(folder)/'out.spice'
        source.write_text(text, encoding='utf-8')
        summary = lvs_reduce.reduce_netlist(source, target)
        return target.read_text(encoding='utf-8'), summary


def device_lines(text):
    return [line for line in text.splitlines() if line.startswith('M')]


class NumberTests(unittest.TestCase):
    def test_suffixes_and_exact_sums(self):
        self.assertEqual(lvs_reduce.number('0.5U'), Decimal('0.5e-6'))
        self.assertEqual(lvs_reduce.number('3u') * 3, lvs_reduce.number('9u'))
        self.assertEqual(lvs_reduce.number('1meg'), Decimal('1e6'))
        self.assertEqual(lvs_reduce.micron(Decimal('1.2e-5')), '12u')
        self.assertEqual(lvs_reduce.micron(Decimal('5e-7')), '0.5u')
        for bad in ['3x', 'u', '', '1e', '3uu']:
            with self.assertRaises(ValueError):
                lvs_reduce.number(bad)


class ReduceTests(unittest.TestCase):
    def test_m_factor_is_parallel_width(self):
        text, summary = reduce_text(INV_CDL)
        self.assertIn('MM0 Y A VSS VSS nmos4 W=6u L=0.5u', text)
        self.assertIn('MM1 Y A VDD VDD pmos4 W=12u L=0.5u', text)
        self.assertEqual(summary['INVX2']['chains'], 0)

    def test_parallel_merge_needs_same_gate_bulk_ends_and_length(self):
        base = ('.SUBCKT P A B Y VDD VSS\nM1 Y A VSS VSS nmos4 W=3u L=0.5u\n{}\n'
                'M9 Y B VDD VDD pmos4 W=3u L=0.5u\n.ENDS\n')
        merged, _ = reduce_text(base.format('M2 VSS A Y VSS nmos4 W=3u L=0.5u'))
        self.assertIn('M1 Y A VSS VSS nmos4 W=6u L=0.5u', merged)
        self.assertEqual(len(device_lines(merged)), 2)
        for other in ['M2 Y A VSS VSS nmos4 W=3u L=0.6u', 'M2 Y B VSS VSS nmos4 W=3u L=0.5u',
                      'M2 Y A VSS VDD nmos4 W=3u L=0.5u', 'M2 Y A VDD VSS nmos4 W=3u L=0.5u',
                      'M2 Y A VSS VSS pmos4 W=3u L=0.5u']:
            kept, _ = reduce_text(base.format(other))
            self.assertEqual(len(device_lines(kept)), 3, other)

    def test_series_chain_becomes_order_free_star(self):
        text, summary = reduce_text(NOR_CDL)
        self.assertEqual(summary['NOR2X1']['chains'], 1)
        lines = device_lines(text)
        self.assertIn('Mchain1 VDD chain1 Y VDD pmos4_chain', lines)
        self.assertIn('Mchain1_1 chain1 A chain1 VDD pmos4_chain_gate W=9u L=0.5u', lines)
        self.assertIn('Mchain1_2 chain1 B chain1 VDD pmos4_chain_gate W=9u L=0.5u', lines)
        self.assertNotIn('net05', text)
        reversed_text, _ = reduce_text(NOR_CDL.replace('MM3 net05 A', 'MM3 net05 B')
                                       .replace('MM0 Y B net05', 'MM0 Y A net05'))
        self.assertEqual(sorted(device_lines(reversed_text)), sorted(lines))

    def test_each_gate_keeps_its_own_width(self):
        text, _ = reduce_text(NOR_CDL.replace('MM3 net05 A VDD VDD pmos4 W=9u', 'MM3 net05 A VDD VDD pmos4 W=8u'))
        self.assertIn('pmos4_chain_gate W=8u', text)
        self.assertIn('pmos4_chain_gate W=9u', text)

    def test_midpoint_used_elsewhere_is_not_a_chain(self):
        cases = {
            'port': NOR_CDL.replace('.SUBCKT NOR2X1 A B Y VDD VSS', '.SUBCKT NOR2X1 A B Y VDD VSS net05'),
            'gate': NOR_CDL.replace('MM2 Y B VSS', 'MM2 Y net05 VSS'),
            'bulk': NOR_CDL.replace('MM2 Y B VSS VSS', 'MM2 Y B VSS net05'),
            'third device': NOR_CDL.replace('MM2 Y B VSS', 'MM2 net05 B VSS'),
            'subcircuit pin': NOR_CDL.replace('.ENDS NOR2X1', 'X1 net05 Y BUF\n.ENDS NOR2X1'),
            'other device': NOR_CDL.replace('.ENDS NOR2X1', 'C1 net05 VSS 1f\n.ENDS NOR2X1'),
            'mixed model': NOR_CDL.replace('MM0 Y B net05 VDD pmos4', 'MM0 Y B net05 VDD nmos4'),
            'mixed bulk': NOR_CDL.replace('MM0 Y B net05 VDD pmos4', 'MM0 Y B net05 VSS pmos4'),
            'repeated gate': NOR_CDL.replace('MM0 Y B net05', 'MM0 Y A net05'),
            'same ends': NOR_CDL.replace('MM0 Y B net05 VDD', 'MM0 VDD B net05 VDD'),
        }
        for name, text in cases.items():
            reduced, summary = reduce_text(text)
            self.assertEqual(summary['NOR2X1']['chains'], 0, name)
            self.assertIn('net05', reduced, name)

    def test_global_net_is_never_internal(self):
        reduced, summary = reduce_text('.GLOBAL net05\n'+NOR_CDL)
        self.assertEqual(summary['NOR2X1']['chains'], 0)
        self.assertTrue(reduced.splitlines()[1].startswith('.GLOBAL'))

    def test_loop_is_left_alone(self):
        text = ('.SUBCKT R A B VDD VSS\nM1 n1 A n2 VSS nmos4 W=3u L=0.5u\n'
                'M2 n2 B n1 VSS nmos4 W=3u L=0.5u\nM3 n1 B VDD VDD pmos4 W=3u L=0.5u\n.ENDS\n')
        reduced, summary = reduce_text(text)
        self.assertEqual(summary['R']['chains'], 0)
        self.assertEqual(len(device_lines(reduced)), 3)

    def test_three_high_chain(self):
        text = ('.SUBCKT N3 A B C Y VDD VSS\nM1 Y A n1 VSS nmos4 W=6u L=0.5u\n'
                'M2 n1 B n2 VSS nmos4 W=6u L=0.5u\nM3 n2 C VSS VSS nmos4 W=6u L=0.5u\n.ENDS\n')
        reduced, summary = reduce_text(text)
        self.assertEqual(summary['N3'], {'mos_in': 3, 'mos_after_parallel': 3, 'chains': 1, 'chain_groups': 1})
        self.assertEqual(len([line for line in device_lines(reduced) if 'chain_gate' in line]), 3)

    def test_split_gates_merge_only_identical_chains(self):
        text, summary = reduce_text(TBUF_LAYOUT)
        self.assertEqual(summary['TBUFX2']['chains'], 4)
        self.assertEqual(summary['TBUFX2']['chain_groups'], 2)
        self.assertIn('nmos4_chain_gate W=12u', text)
        self.assertIn('pmos4_chain_gate W=18u', text)
        uneven = TBUF_LAYOUT.replace('M$10 VSS A \\$9 VSS nmos4 L=0.5U W=6U', 'M$10 VSS A \\$9 VSS nmos4 L=0.5U W=5U')
        _, summary = reduce_text(uneven)
        self.assertEqual(summary['TBUFX2']['chain_groups'], 3)

    def test_includes_and_continuations(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder/'cells.spice').write_text(INV_CDL, encoding='utf-8')
            (folder/'top.spice').write_text('.include "cells.spice"\n.SUBCKT TOP A Y\n+ VDD VSS\n'
                                            'X1 A Y VDD VSS INVX2\n.ENDS TOP\n', encoding='utf-8')
            summary = lvs_reduce.reduce_netlist(folder/'top.spice', folder/'out.spice')
            out = (folder/'out.spice').read_text(encoding='utf-8')
        self.assertEqual(list(summary), ['INVX2', 'TOP'])
        self.assertIn('.SUBCKT TOP A Y VDD VSS', out)
        self.assertIn('X1 A Y VDD VSS INVX2', out)

    def test_unsupported_input_fails(self):
        for text in [NOR_CDL.replace('m=1', 'nf=2', 1),
                     NOR_CDL.replace('W=3u L=0.5u m=1', 'L=0.5u m=1', 1),
                     NOR_CDL.replace('m=1', 'm=1.5', 1),
                     NOR_CDL.replace('m=1', 'm=0', 1),
                     NOR_CDL.replace('nmos4 W=3u', 'nmos4_chain W=3u', 1),
                     NOR_CDL.replace('.ENDS NOR2X1', ''),
                     '.param x=1\n'+NOR_CDL,
                     'M1 a b c d nmos4 W=1u L=1u\n']:
            with self.assertRaises(ValueError):
                reduce_text(text)


def netgen():
    try:
        return run_physical.executable('netgen')
    except ValueError:
        return None


@unittest.skipUnless(netgen(), 'Netgen is not installed')
class NetgenTests(unittest.TestCase):
    def compare(self, layout, source, top):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder/'layout.spice').write_text(layout, encoding='utf-8')
            (folder/'source.spice').write_text(source, encoding='utf-8')
            lvs_reduce.reduce_netlist(folder/'layout.spice', folder/'layout.reduced.spice')
            lvs_reduce.reduce_netlist(folder/'source.spice', folder/'source.reduced.spice')
            (folder/'run.tcl').write_text(run_physical.NETGEN_SCRIPT, encoding='utf-8')
            env = dict(os.environ, SSC_TOP=top, SSC_EXTRACTED=str(folder/'layout.reduced.spice'),
                       SSC_SCHEMATIC=str(folder/'source.reduced.spice'), SSC_SETUP=str(SETUP))
            subprocess.run([netgen(), '-batch', 'source', str(folder/'run.tcl')], cwd=folder, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=120, check=True)
            self.assertTrue((folder/'netgen-complete.txt').is_file())
            report = (folder/'lvs.log').read_text(encoding='utf-8', errors='replace')
            return run_physical.lvs_verdict(report, json.loads((folder/'lvs.json').read_text()), top)

    def test_kit_shapes_match(self):
        self.assertTrue(self.compare(INV_FINGERS, INV_CDL, 'INVX2'))
        self.assertTrue(self.compare(NOR_LAYOUT, NOR_CDL, 'NOR2X1'))
        self.assertTrue(self.compare(TBUF_LAYOUT, TBUF_CDL, 'TBUFX2'))
        self.assertTrue(self.compare(AOI22_CDL, AOI22_CDL.replace('MM0 Y A n1', 'MM0 Y B n1')
                                     .replace('MM1 n1 B VSS', 'MM1 n1 A VSS'), 'AOI22X1'))

    def test_wrong_width_or_length_fails(self):
        for source in [INV_CDL.replace('W=3u L=0.5u m=2', 'W=3u L=0.5u m=3'),
                       INV_CDL.replace('W=3u L=0.5u m=2', 'W=2.9u L=0.5u m=2'),
                       INV_CDL.replace('W=3u L=0.5u m=2', 'W=3u L=0.6u m=2')]:
            self.assertFalse(self.compare(INV_FINGERS, source, 'INVX2'), source)
        for source in [NOR_CDL.replace('MM3 net05 A VDD VDD pmos4 W=9u', 'MM3 net05 A VDD VDD pmos4 W=8u'),
                       NOR_CDL.replace('MM0 Y B net05 VDD pmos4 W=9u L=0.5u', 'MM0 Y B net05 VDD pmos4 W=9u L=0.6u')]:
            self.assertFalse(self.compare(NOR_LAYOUT, source, 'NOR2X1'), source)
        self.assertFalse(self.compare(TBUF_LAYOUT, TBUF_CDL.replace('MM5 Y EN net43 VSS nmos4 W=6u',
                                                                    'MM5 Y EN net43 VSS nmos4 W=5u'), 'TBUFX2'))

    def test_widths_are_exact_like_the_deck(self):
        # 9.04u vs 9u is 0.44 %: inside Netgen's default 1 %, outside the deck's TRACE PROPERTY 0.
        self.assertFalse(self.compare(NOR_LAYOUT, NOR_CDL.replace('MM3 net05 A VDD VDD pmos4 W=9u',
                                                                  'MM3 net05 A VDD VDD pmos4 W=9.04u'), 'NOR2X1'))
        self.assertFalse(self.compare(NOR_LAYOUT, NOR_CDL.replace('MM2 Y B VSS VSS nmos4 W=3u',
                                                                  'MM2 Y B VSS VSS nmos4 W=3.01u'), 'NOR2X1'))

    def test_width_moved_between_chain_inputs_fails(self):
        layout = NOR_LAYOUT.replace('M$1 \\$6 A Y VDD pmos4 L=0.5U W=9U', 'M$1 \\$6 A Y VDD pmos4 L=0.5U W=8U')
        source = NOR_CDL.replace('MM0 Y B net05 VDD pmos4 W=9u', 'MM0 Y B net05 VDD pmos4 W=8u')
        self.assertFalse(self.compare(layout, source, 'NOR2X1'))

    def test_wrong_gate_connection_fails(self):
        swapped = AOI22_CDL.replace('MM1 n1 B VSS', 'MM1 n1 C VSS').replace('MM2 Y C n2', 'MM2 Y B n2')
        self.assertFalse(self.compare(AOI22_CDL, swapped, 'AOI22X1'))
        self.assertFalse(self.compare(NOR_LAYOUT, NOR_CDL.replace('MM2 Y B VSS', 'MM2 Y A VSS'), 'NOR2X1'))

    def test_order_matters_when_midpoint_is_shared(self):
        # The midpoint also feeds a gate, so the two transistors are not a free chain.
        layout = NOR_CDL.replace('MM2 Y B VSS VSS nmos4 W=3u', 'MM2 Y net05 VSS VSS nmos4 W=3u')
        source = (layout.replace('MM3 net05 A VDD', 'MM3 net05 B VDD')
                  .replace('MM0 Y B net05', 'MM0 Y A net05'))
        self.assertTrue(self.compare(layout, layout, 'NOR2X1'))
        self.assertFalse(self.compare(layout, source, 'NOR2X1'))


if __name__ == '__main__':
    unittest.main()
