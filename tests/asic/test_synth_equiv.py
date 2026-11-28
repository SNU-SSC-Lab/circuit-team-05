"""RTL <-> gate netlist equivalence (scripts/asic/synth_equiv.py).

The parsing tests need no tool. The Yosys tests prove a tiny design against a hand-written
Genus-style netlist (flop instances named <path>_reg[<i>], outputs on arbitrary nets) and check
that a one-gate change, a wrong reset, an undriven output, a falling-edge or wrongly clocked or
asynchronous flop, an output dropped from the port list and a register that one reset cycle does not
define are all rejected (2026-11-28 review C1, I1, I2). They skip where
Yosys is not installed. The real netlists (Yosys with a recoded FSM, Genus) are checked at the
checkpoint (verification/reliability/golden/synth-20261128/).
"""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'scripts/asic'))
import synth_equiv  # noqa: E402

LIBERTY = """library(tiny) {
  cell(INVX1) { area : 1; pin(A) { direction : input; } pin(Y) { direction : output; function : "!A"; } }
  cell(AND2X1) { area : 1; pin(A) { direction : input; } pin(B) { direction : input; }
    pin(Y) { direction : output; function : "(A&B)"; } }
  cell(XOR2X1) { area : 1; pin(A) { direction : input; } pin(B) { direction : input; }
    pin(Y) { direction : output; function : "(A^B)"; } }
  cell(DFFPOSX1) { area : 1; ff(IQ, IQN) { clocked_on : "CLK"; next_state : "D"; }
    pin(CLK) { direction : input; clock : true; } pin(D) { direction : input; }
    pin(Q) { direction : output; function : "IQ"; } }
  cell(DFFNEGX1) { area : 1; ff(IQ, IQN) { clocked_on : "!CLK"; next_state : "D"; }
    pin(CLK) { direction : input; clock : true; } pin(D) { direction : input; }
    pin(Q) { direction : output; function : "IQ"; } }
  cell(DFFSRX1) { area : 1; ff(IQ, IQN) { clocked_on : "CLK"; next_state : "D"; clear : "!R"; preset : "!S"; }
    pin(CLK) { direction : input; clock : true; } pin(D) { direction : input; } pin(R) { direction : input; }
    pin(S) { direction : input; } pin(Q) { direction : output; function : "IQ"; } }
}
"""
RTL = """module t(input CLK, input RST_N, input EN, output Q);
  wire [1:0] count;
  counter u_cnt (.CLK(CLK), .RST_N(RST_N), .EN(EN), .C(count));
  assign Q = count[1];
endmodule
module counter(input CLK, input RST_N, input EN, output reg [1:0] C);
  always @(posedge CLK) if (!RST_N) C <= 2'd0; else if (EN) C <= C + 2'd1;
endmodule
"""
# Genus style: flat, flop instances named after the RTL register, flop outputs on any net.
GATE = """module t(CLK, RST_N, EN, Q);
  input CLK, RST_N, EN;
  output Q;
  wire n0, n1, n2, d0, d1;
  wire \\u_cnt_C[0]_7 ;
  XOR2X1 g1(.A (\\u_cnt_C[0]_7 ), .B (EN), .Y (n0));
  AND2X1 g2(.A (RST_N), .B (n0), .Y (d0));
  AND2X1 g3(.A (\\u_cnt_C[0]_7 ), .B (EN), .Y (n1));
  XOR2X1 g4(.A (Q), .B (n1), .Y (n2));
  AND2X1 g5(.A (RST_N), .B (n2), .Y (d1));
  DFFPOSX1 \\u_cnt_C_reg[0] (.CLK (CLK), .D (d0), .Q
       (\\u_cnt_C[0]_7 ));
  DFFPOSX1 \\u_cnt_C_reg[1] (.CLK (CLK), .D (d1), .Q (Q));
endmodule
"""
# A register without reset that only loads when EN is high: equal next-state functions, but one reset
# cycle does not make the two copies equal (the start condition fails, the induction alone would not).
HOLD_RTL = """module t(input CLK, input RST_N, input EN, input D, output Q);
  reg q;
  always @(posedge CLK) if (EN) q <= D;
  assign Q = q & RST_N;
endmodule
"""
HOLD_GATE = """module t(CLK, RST_N, EN, D, Q);
  input CLK, RST_N, EN, D;
  output Q;
  wire q, a, b, ne, d;
  AND2X1 g1(.A (EN), .B (D), .Y (a));
  INVX1 g2(.A (EN), .Y (ne));
  AND2X1 g3(.A (ne), .B (q), .Y (b));
  XOR2X1 g4(.A (a), .B (b), .Y (d));
  DFFPOSX1 q_reg(.CLK (CLK), .D (d), .Q (q));
  AND2X1 g5(.A (q), .B (RST_N), .Y (Q));
endmodule
"""
SYNTH_LOG = """13.9.6. Executing FSM_RECODE pass (re-assigning FSM state encoding).
Recoding FSM `$fsm$\\u_controller.state$310' from module `\\v_ternary8_top' using `auto' encoding:
  mapping auto encoding to `one-hot` for this FSM.
  00 -> ---1
  10 -> --1-
  01 -> -1--
  11 -> 1---

13.9.7. Executing FSM_INFO pass (dumping all available information on FSM cells).
"""


class ParseTests(unittest.TestCase):
    def test_flop_cells_come_from_ff_groups(self):
        self.assertEqual(synth_equiv.flop_cells(LIBERTY), {'DFFPOSX1', 'DFFNEGX1', 'DFFSRX1'})
        seq = synth_equiv.sequential_cells(LIBERTY)
        self.assertEqual((seq['DFFPOSX1']['clocked_on'], seq['DFFPOSX1']['async']), ('CLK', False))
        self.assertEqual(seq['DFFNEGX1']['clocked_on'], '!CLK')
        self.assertTrue(seq['DFFSRX1']['async'])

    def test_flop_outputs_read_escaped_names(self):
        outputs = synth_equiv.flop_outputs(GATE, {'DFFPOSX1'})
        self.assertEqual(outputs, [('u_cnt_C_reg[0]', '\\u_cnt_C[0]_7'), ('u_cnt_C_reg[1]', 'Q')])

    def test_aliases_name_flop_outputs_like_the_gold(self):
        wires = {'u_cnt.C': (0, 2, False), 'count': (0, 2, False), 'Q': (0, 1, False)}
        lines, paired, unpaired = synth_equiv.aliases(synth_equiv.flop_outputs(GATE, {'DFFPOSX1'}), wires)
        self.assertEqual(paired, {'u_cnt.C': [0, 1]})
        self.assertEqual(unpaired, [])
        self.assertEqual(lines, ['  wire [1:0] \\u_cnt.C ;', '  assign \\u_cnt.C [0] = \\u_cnt_C[0]_7 ;',
                                 '  assign \\u_cnt.C [1] = Q ;'])

    def test_ambiguous_or_unknown_names_stay_unpaired(self):
        wires = {'a.b': (0, 1, False), 'a_b': (0, 1, False)}
        _, paired, unpaired = synth_equiv.aliases([('a_b_reg', 'x'), ('zz_reg[3]', 'y'), ('_12_', 'z')], wires)
        self.assertEqual((paired, unpaired), ({}, ['a_b_reg', 'zz_reg[3]', '_12_']))

    def test_fsm_encodings_from_a_yosys_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp)/'synth.log'
            log.write_text(SYNTH_LOG, encoding='utf-8')
            self.assertEqual(synth_equiv.fsm_encodings(log).splitlines(), [
                '.fsm v_ternary8_top u_controller.state', '.map 00 ---1', '.map 10 --1-', '.map 01 -1--',
                '.map 11 1---'])
            log.write_text('no fsm here\n', encoding='utf-8')
            self.assertEqual(synth_equiv.fsm_encodings(log), '')


@unittest.skipUnless(shutil.which('yosys'), 'Yosys not installed')
class ProofTests(unittest.TestCase):
    def run_check(self, gate, synth_log=None, rtl=RTL):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp/'cells.lib').write_text(LIBERTY, encoding='utf-8')
            (tmp/'rtl.v').write_text(rtl, encoding='utf-8')
            (tmp/'gate.v').write_text(gate, encoding='utf-8')
            log = None
            if synth_log:
                log = tmp/'synth.log'
                log.write_text(synth_log, encoding='utf-8')
            result = synth_equiv.check(tmp/'gate.v', tmp/'cells.lib', tmp/'out', [tmp/'rtl.v'], 't', None, log,
                                       require_kit=False)
            self.assertEqual(json.loads((tmp/'out/summary.json').read_text(encoding='utf-8'))['status'],
                             result['status'])
            return result

    def test_genus_style_netlist_is_proven(self):
        result = self.run_check(GATE)
        self.assertEqual(result['status'], 'pass', result)
        self.assertEqual(result['register_names']['aliased'], 2)
        self.assertEqual(result['equiv']['unproven'], [])
        self.assertEqual(result['netlist']['flops'], 2)
        self.assertEqual((result['ports']['status'], result['clocks']['status']), ('pass', 'pass'))
        self.assertEqual(result['base_case']['status'], 'pass')
        self.assertEqual(result['clocks']['gate_flops'], 2)

    def test_one_wrong_gate_fails(self):
        wrong = GATE.replace('XOR2X1 g4(.A (Q), .B (n1), .Y (n2));', 'AND2X1 g4(.A (Q), .B (n1), .Y (n2));')
        self.assertNotEqual(wrong, GATE)
        result = self.run_check(wrong)
        self.assertEqual(result['status'], 'fail')
        self.assertTrue(result['equiv']['unproven'])

    def test_wrong_reset_fails(self):
        wrong = GATE.replace('AND2X1 g2(.A (RST_N), .B (n0), .Y (d0));', 'XOR2X1 g2(.A (RST_N), .B (n0), .Y (d0));')
        self.assertEqual(self.run_check(wrong)['status'], 'fail')

    def test_undriven_output_fails(self):
        undriven = GATE.replace('.Q (Q));', '.Q (q1));').replace('wire n0,', 'wire q1, n0,').replace(
            'XOR2X1 g4(.A (Q),', 'XOR2X1 g4(.A (q1),')
        result = self.run_check(undriven)
        self.assertEqual(result['status'], 'fail')
        # an output port is always a pair; undriven on the gate side it cannot be proven
        self.assertIn('Q', result['equiv']['unproven'] + result['equiv']['ports_left_out'])

    # Clock structure (2026-11-28 review C1): the SAT models do not see clock pins, the structure check does.
    def test_falling_edge_flop_fails(self):
        wrong = GATE.replace('DFFPOSX1 \\u_cnt_C_reg[1]', 'DFFNEGX1 \\u_cnt_C_reg[1]')
        self.assertNotEqual(wrong, GATE)
        result = self.run_check(wrong)
        self.assertEqual(result['status'], 'fail')
        self.assertTrue(any('rising edge' in p for p in result['clocks']['problems']), result['clocks'])

    def test_flop_clocked_by_a_data_input_fails(self):
        for net in ('EN', 'RST_N'):
            wrong = GATE.replace('DFFPOSX1 \\u_cnt_C_reg[1] (.CLK (CLK),', f'DFFPOSX1 \\u_cnt_C_reg[1] (.CLK ({net}),')
            self.assertNotEqual(wrong, GATE)
            result = self.run_check(wrong)
            self.assertEqual(result['status'], 'fail', net)
            self.assertTrue(any('not the clock port' in p for p in result['clocks']['problems']), net)

    def test_async_flop_fails(self):
        wrong = GATE.replace('DFFPOSX1 \\u_cnt_C_reg[1] (.CLK (CLK), .D (d1), .Q (Q));',
                             'DFFSRX1 \\u_cnt_C_reg[1] (.CLK (CLK), .D (d1), .R (RST_N), .S (EN), .Q (Q));')
        self.assertNotEqual(wrong, GATE)
        result = self.run_check(wrong)
        self.assertEqual(result['status'], 'fail')
        self.assertTrue(any('asynchronous' in p for p in result['clocks']['problems']))

    # Ports (review I2): an output dropped from the port list but kept as a net must fail.
    def test_output_dropped_from_port_list_fails(self):
        dropped = GATE.replace('module t(CLK, RST_N, EN, Q);', 'module t(CLK, RST_N, EN);').replace(
            '  output Q;\n', '  wire Q;\n')
        self.assertNotEqual(dropped, GATE)
        result = self.run_check(dropped)
        self.assertEqual(result['status'], 'fail')
        self.assertIn('port Q only in RTL', result['ports']['problems'])

    # Start condition (review I1): induction alone passes, one reset cycle does not make the copies equal.
    def test_register_without_reset_fails_the_start_condition(self):
        result = self.run_check(HOLD_GATE, rtl=HOLD_RTL)
        self.assertEqual(result['equiv']['unproven'], [])
        self.assertEqual(result['base_case']['status'], 'fail')
        self.assertEqual(result['status'], 'fail')

    def test_unused_fsm_log_changes_nothing(self):
        self.assertEqual(self.run_check(GATE, 'nothing recoded\n')['status'], 'pass')


class FlowCheckTests(unittest.TestCase):
    def test_a_broken_check_fails_the_gate(self):
        sys.path.insert(0, str(ROOT/'scripts'))
        from asic.flow import CORE_CHECKS, synth_equivalence
        self.assertIn('asic-synth-equiv', CORE_CHECKS)
        with tempfile.TemporaryDirectory() as tmp:
            result = synth_equivalence(Path(tmp)/'missing.v', Path(tmp)/'missing.lib', Path(tmp))
        self.assertEqual(result['status'], 'fail')
        self.assertIn('Error', result['detail'])


if __name__ == '__main__':
    unittest.main()
