"""RTL <-> gate netlist equivalence (scripts/asic/synth_equiv.py).

The parsing tests need no tool. The Yosys tests prove a tiny design against a hand-written
Genus-style netlist (flop instances named <path>_reg[<i>], outputs on arbitrary nets) and check
that a one-gate change, a wrong reset and an undriven output are all rejected. They skip where
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
        self.assertEqual(synth_equiv.flop_cells(LIBERTY), {'DFFPOSX1'})

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
    def run_check(self, gate, synth_log=None):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp/'cells.lib').write_text(LIBERTY, encoding='utf-8')
            (tmp/'rtl.v').write_text(RTL, encoding='utf-8')
            (tmp/'gate.v').write_text(gate, encoding='utf-8')
            log = None
            if synth_log:
                log = tmp/'synth.log'
                log.write_text(synth_log, encoding='utf-8')
            result = synth_equiv.check(tmp/'gate.v', tmp/'cells.lib', tmp/'out', [tmp/'rtl.v'], 't', None, log)
            self.assertEqual(json.loads((tmp/'out/summary.json').read_text(encoding='utf-8'))['status'],
                             result['status'])
            return result

    def test_genus_style_netlist_is_proven(self):
        result = self.run_check(GATE)
        self.assertEqual(result['status'], 'pass', result)
        self.assertEqual(result['register_names']['aliased'], 2)
        self.assertEqual(result['equiv']['unproven'], [])
        self.assertEqual(result['netlist']['flops'], 2)

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

    def test_unused_fsm_log_changes_nothing(self):
        self.assertEqual(self.run_check(GATE, 'nothing recoded\n')['status'], 'pass')


if __name__ == '__main__':
    unittest.main()
