"""Post-route functional comparison of the fixed 8-bit comparison circuit."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pdk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netlist', type=Path, required=True)
    parser.add_argument('--rtl', type=Path, required=True)
    parser.add_argument('--lib', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.netlist, args.rtl = args.netlist.resolve(), args.rtl.resolve()
    args.lib, args.out = args.lib.resolve(), args.out.resolve()
    model = pdk.gate_model(args.netlist, 'shift_reg_8bit', args.lib, args.out)
    content, count = re.subn(r'\bmodule shift_reg_8bit\b', 'module shift_reg_8bit_gate', model.read_text())
    if count != 1:
        raise ValueError('unexpected functional model')
    model.write_text(content)
    bench = args.out/'tb.v'
    bench.write_text('''module tb;
reg clk=0, rst_n=0, din=0;
wire [7:0] rtl, gate;
integer index, seed=7045;
shift_reg_8bit r(.clk(clk), .rst_n(rst_n), .din(din), .dout(rtl));
shift_reg_8bit_gate g(.clk(clk), .rst_n(rst_n), .din(din), .dout(gate));
always #5 clk=~clk;
initial begin
  repeat(4) @(negedge clk);
  rst_n=1;
  for(index=0;index<1000;index=index+1) begin
    @(negedge clk);
    din=$random(seed);
    rst_n=(index%97 != 0);
    @(posedge clk); #1;
    if(rtl !== gate) $fatal(1,"postroute mismatch index=%d RTL=%b gate=%b",index,rtl,gate);
  end
  $display("POSTROUTE checks=1000 mismatches=0");
  $finish;
end
endmodule
''')
    executable = args.out/'simulation.vvp'
    subprocess.run(['iverilog', '-g2012', '-s', 'tb', '-o', str(executable),
                    str(bench), str(args.rtl), str(model)], check=True)
    subprocess.run(['vvp', str(executable)], check=True)


if __name__ == '__main__':
    main()
