"""The flow's SDC names the data inputs explicitly (scripts/pdk.py sdc_data_inputs, input_ports).

OpenSTA's `delete_from_list` is skipped by Tempus (SPEC 0019, sdc-portability), so line 2 of
constraints.sdc lists every input but the clock with a plain `get_ports`. input_ports needs Yosys.
"""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'scripts/asic'))
import pdk  # noqa: E402

LIBERTY = """library(tiny) {
  cell(BUFX2) { area : 1; pin(A) { direction : input; } pin(Y) { direction : output; function : "A"; } }
}
"""
# Genus writes every port in one module header; OpenROAD adds inout power pins.
NETLIST = """module top(CLK, RST_N, IN, IN_VALID, OUT, VDD, VSS);
  input CLK, RST_N, IN_VALID;
  input [3:0] IN;
  output OUT;
  inout VDD, VSS;
  BUFX2 b(.A (IN_VALID), .Y (OUT));
endmodule
"""


class SdcLineTests(unittest.TestCase):
    def test_line_lists_every_input_but_the_clock(self):
        line = pdk.sdc_data_inputs(['CLK', 'IN[0]', 'IN[1]', 'IN_VALID', 'RST_N'])
        self.assertEqual(line, 'set data_in [get_ports {IN[0] IN[1] IN_VALID RST_N}]')
        self.assertNotIn('delete_from_list', line)
        self.assertNotIn('remove_from_collection', line)

    def test_missing_clock_or_no_data_input_is_an_error(self):
        with self.assertRaises(ValueError):
            pdk.sdc_data_inputs(['RST_N', 'IN[0]'])
        with self.assertRaises(ValueError):
            pdk.sdc_data_inputs(['CLK'])

    def test_names_that_would_need_escaping_are_refused(self):
        with self.assertRaises(ValueError):
            pdk.sdc_data_inputs(['CLK', 'a.b'])

    def test_flow_and_pdk_scripts_have_no_opensta_only_command(self):
        for path in (ROOT/'scripts/asic/flow.py', ROOT/'scripts/pdk.py'):
            self.assertNotIn('delete_from_list [', path.read_text(encoding='utf-8'), path.name)


@unittest.skipUnless(shutil.which('yosys'), 'Yosys not installed')
class InputPortTests(unittest.TestCase):
    def test_ports_from_a_netlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp/'cells.lib').write_text(LIBERTY, encoding='utf-8')
            (tmp/'top.v').write_text(NETLIST, encoding='utf-8')
            ports = pdk.input_ports(tmp/'top.v', 'top', tmp/'cells.lib', tmp/'work')
        # inout power pins are not inputs; buses are bit-blasted in index order
        self.assertEqual(ports, ['CLK', 'IN[0]', 'IN[1]', 'IN[2]', 'IN[3]', 'IN_VALID', 'RST_N'])
        self.assertEqual(pdk.sdc_data_inputs(ports),
                         'set data_in [get_ports {IN[0] IN[1] IN[2] IN[3] IN_VALID RST_N}]')


if __name__ == '__main__':
    unittest.main()
