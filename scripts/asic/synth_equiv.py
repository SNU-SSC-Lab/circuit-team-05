"""Formal check that a gate netlist does what the RTL does (SPEC 0019, table row `synth`).

Gold is the team RTL, flattened. Gate is a netlist of kit cells, each cell being its Liberty
function (read_liberty), as in pdk.gate_model. Yosys proves equivalence by register correspondence:
equiv_make pairs signals of the same name, equiv_simple and equiv_induct prove every pair, and the
check passes only when every pair is proven (equiv_status -assert) and no output bit was left out.
The proof assumes paired registers start equal, which every register's synchronous reset gives.

Registers are paired by name. Yosys and OpenROAD keep the RTL names on flop outputs (`\\u_tx.result_shift [3]`).
Genus names the flop instance instead (`\\u_tx_result_shift_reg[3]`) and may name its output anything
(`\\u_weights_WEIGHTS[2]_108`, `term_negate`); for such a netlist the gate copy gets alias wires that
carry the gold name (`\\u_tx.result_shift [3]` = flop output). Aliases only add names; no cell changes.

A wrong pairing cannot make the check pass: every output port is a pair, and a pair of unrelated
signals stays unproven. --cell-models compares the kit's Verilog models of the combinational cells the
netlist uses with their Liberty functions.

The netlist under check is never copied into the repository; summary.json keeps its sha256.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pdk  # noqa: E402

INSTANCE = re.compile(r'^\s*(\w+)\s+(\\\S+|[A-Za-z_]\w*)\s*\((.*?)\)\s*;', re.M | re.S)
GENUS_REG = re.compile(r'^(?P<path>.+?)_reg(?:\[(?P<index>\d+)\])?$')
SKIPPED = re.compile(r'Skipping signal bit (\S+)_gate(?: \[(\d+)\])?: undriven on gate side')
STATUS = re.compile(r'Found (\d+) \$equiv cells in \S+:\s*\n\s*Of those cells (\d+) are proven and (\d+) are unproven')
SEQ = 5


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def flop_cells(liberty_text):
    """Names of the Liberty cells that have an ff group (the kit's flip-flops)."""
    cells = [(m.start(), m.group(1)) for m in re.finditer(r'\bcell\s*\(\s*"?(\w+)"?\s*\)', liberty_text)]
    flops = set()
    for m in re.finditer(r'\bff\s*\(', liberty_text):
        owner = [name for start, name in cells if start < m.start()]
        if owner:
            flops.add(owner[-1])
    return flops


def flop_outputs(netlist_text, flops):
    """[(instance, Q expression)] of every flop instance; instance names without the Verilog escape."""
    found = []
    for cell, instance, body in INSTANCE.findall(netlist_text):
        if cell not in flops:
            continue
        q = re.search(r'\.Q\s*\(\s*(.*?)\s*\)\s*(?:,|$)', body, re.S)
        if q and q.group(1):
            found.append((instance.lstrip('\\'), ' '.join(q.group(1).split())))
    return found


def gold_wires(gold_json, top):
    """{dotted name: (offset, width, upto)} of the flattened gold's public wires."""
    nets = json.loads(Path(gold_json).read_text(encoding='utf-8'))['modules'][top]['netnames']
    return {name: (int(n.get('offset', 0)), len(n['bits']), bool(n.get('upto', 0)))
            for name, n in nets.items() if not n.get('hide_name')}


def aliases(outputs, wires):
    """Alias lines for flops named <path>_reg[<i>] (Genus): gold wire bit <path>[<i>] = flop output.

    <path> uses "_" where the gold uses "."; a gold name maps only when exactly one gold wire matches.
    Returns (verilog lines, {gold name: [bits]}, [instances left unpaired])."""
    by_flat = {}
    for name in wires:
        by_flat.setdefault(name.replace('.', '_'), []).append(name)
    bits, unpaired = {}, []
    for instance, q in outputs:
        m = GENUS_REG.match(instance)
        names = by_flat.get(m.group('path'), []) if m else []
        if len(names) != 1:
            unpaired.append(instance)
            continue
        offset, width, _ = wires[names[0]]
        index = int(m.group('index')) if m.group('index') is not None else None
        if (width != 1) if index is None else not offset <= index < offset+width:
            unpaired.append(instance)
            continue
        bits.setdefault(names[0], []).append((index, q))
    lines = []
    for name, pairs in sorted(bits.items()):
        offset, width, upto = wires[name]
        span = '' if pairs[0][0] is None else (f'[{offset}:{offset+width-1}] ' if upto else f'[{offset+width-1}:{offset}] ')
        lines.append(f'  wire {span}\\{name} ;')
        for index, q in sorted(pairs, key=lambda p: -1 if p[0] is None else p[0]):
            target = f'\\{name} ' + ('' if index is None else f'[{index}]')
            lines.append(f'  assign {target} = {q} ;')
    return lines, {name: sorted(i for i, _ in pairs if i is not None) for name, pairs in bits.items()}, unpaired


def with_aliases(netlist_text, top, lines):
    """The netlist text with alias lines added at the end of module `top`."""
    start = re.search(r'\bmodule\s+\\?' + re.escape(top) + r'\b', netlist_text)
    if not start:
        raise ValueError(f'module {top} not found in netlist')
    end = netlist_text.find('endmodule', start.end())
    if end < 0:
        raise ValueError(f'module {top} has no endmodule')
    block = '  // synth_equiv.py: register name aliases (no cell changes)\n' + '\n'.join(lines) + '\n'
    return netlist_text[:end] + block + netlist_text[end:]


def run_yosys(lines, work, name):
    code, err = pdk.yosys(lines, work, name)
    return code, err, (work/f'{name}.log').read_text(encoding='utf-8', errors='replace')


def gold_lines(sources, top):
    return ['read_verilog -sv ' + ' '.join(pdk.q(s) for s in sources), f'hierarchy -check -top {top}',
            'proc', 'flatten', 'opt_clean']


def gate_lines(liberty, netlist, top):
    return [f'read_liberty {pdk.q(liberty)}', f'read_verilog {pdk.q(netlist)}', f'hierarchy -check -top {top}',
            'flatten', 'opt_clean']


def fsm_encodings(synth_log):
    """encfile text (fsm_recode format) from the FSM_RECODE lines of a Yosys synthesis log, or ''."""
    out, current = [], None
    for line in Path(synth_log).read_text(encoding='utf-8', errors='replace').splitlines():
        start = re.match(r"Recoding FSM `\$fsm\$\\(.+?)\$\d+' from module `\\?(\S+?)'", line)
        if start:
            current = start.groups()
            out.append(f'.fsm {current[1]} {current[0]}')
            continue
        mapping = re.match(r'\s+([01]+) -> ([01-]+)\s*$', line)
        if current and mapping:
            out.append(f'.map {mapping.group(1)} {mapping.group(2)}')
        elif current and line.strip() and not line.strip().startswith('mapping '):
            current = None
    return '\n'.join(out) + '\n' if out else ''


def equivalence(sources, top, liberty, netlist, work, gate_extra=(), encfile=None):
    """Register-correspondence proof (equiv_*). Returns the result dict."""
    make = 'equiv_make' + (f' -encfile {pdk.q(encfile)}' if encfile else '') + ' gold gate equiv'
    lines = gold_lines(sources, top) + ['rename -top gold', 'design -stash gold'] + \
        gate_lines(liberty, netlist, top) + list(gate_extra) + ['rename -top gate', 'design -stash gate',
        'design -copy-from gold -as gold gold', 'design -copy-from gate -as gate gate', make, 'hierarchy -top equiv', f'equiv_simple -seq {SEQ}',
        f'equiv_induct -seq {SEQ}', f'tee -o {pdk.q(work/"equiv_status.txt")} equiv_status', 'equiv_status -assert']
    code, err, log = run_yosys(lines, work, 'equiv')
    status = (work/'equiv_status.txt').read_text(encoding='utf-8') if (work/'equiv_status.txt').is_file() else ''
    counts = STATUS.search(status)
    unproven = re.findall(r'Unproven \$equiv \S+: (\S+)_gold(?: \[(\d+)\])?', status)
    skipped = [f'{n}[{i}]' if i else n for n, i in SKIPPED.findall(log)]
    return {'exit': code, 'detail': err[-400:] if code else '',
            'cells': int(counts.group(1)) if counts else None, 'proven': int(counts.group(2)) if counts else None,
            'unproven': [f'{n.lstrip(chr(92))}[{i}]' if i else n.lstrip(chr(92)) for n, i in unproven],
            'skipped_gold_bits': skipped}


def cell_models(models, liberty, cells, flops, work):
    """Kit Verilog model == Liberty function, for each combinational cell type in `cells`."""
    results = {}
    for cell in sorted(cells):
        if cell in flops:
            results[cell] = 'not_compared: sequential (the kit Verilog model samples D at the falling edge '\
                            'and copies it at the rising edge; the Liberty ff is used)'
            continue
        lines = [f'read_verilog {pdk.q(models)}', f'hierarchy -top {cell}', 'proc', 'flatten',
                 f'rename {cell} gold', 'design -stash gold', f'read_liberty {pdk.q(liberty)}',
                 f'hierarchy -top {cell}', f'rename {cell} gate', 'design -stash gate',
                 'design -copy-from gold -as gold gold', 'design -copy-from gate -as gate gate',
                 'equiv_make gold gate equiv', 'hierarchy -top equiv', 'equiv_simple', 'equiv_status -assert']
        code, _, _ = run_yosys(lines, work, f'cell-{cell}')
        results[cell] = 'equivalent' if code == 0 else 'different'
    return results


def check(netlist, liberty, out, sources=None, top=None, models=None, synth_log=None):
    out = Path(out)
    if out.exists():
        raise ValueError(f'{out} exists; choose a new folder')
    out.mkdir(parents=True)
    top = top or pdk.DESIGN['top']
    sources = [Path(s) for s in (sources or pdk.sources())]
    lib_text = Path(liberty).read_text(encoding='utf-8', errors='replace')
    flops = flop_cells(lib_text)
    text = Path(netlist).read_text(encoding='utf-8', errors='replace')
    version = subprocess.run(['yosys', '-V'], capture_output=True, text=True).stdout.strip()
    result = {'netlist': {'name': Path(netlist).name, 'sha256': sha256(netlist)},
              'liberty_sha256': sha256(liberty), 'kit_liberty': sha256(liberty) == pdk.PDK['digital']['liberty_sha256'],
              'rtl': {'top': top, 'sha256': {s.name: sha256(s) for s in sources}},
              'yosys': version, 'cell_model': 'Liberty function (read_liberty)',
              'assumption': 'paired registers start equal (all registers have a synchronous reset)'}
    code, err, _ = run_yosys([f'read_liberty -lib {pdk.q(liberty)}'] + gate_lines(liberty, netlist, top)[1:3] +
                             [f'tee -q -o {pdk.q(out/"gate_stat.json")} stat -json',
                              f'write_json {pdk.q(out/"gate_ports.json")}'], out, 'gate_stat')
    if code:
        result.update(status='fail', detail='netlist does not read on the kit cells: '+err[-400:])
    else:
        design = json.loads((out/'gate_stat.json').read_text(encoding='utf-8'))['design']
        by_type = design.get('num_cells_by_type', {})
        gate_ports = json.loads((out/'gate_ports.json').read_text(encoding='utf-8'))['modules'][top]['ports']
        result['netlist'].update(cells=design.get('num_cells'), by_type=dict(sorted(by_type.items())),
                                 flops=sum(n for c, n in by_type.items() if c in flops))
        code, err, _ = run_yosys(gold_lines(sources, top) + [f'write_json {pdk.q(out/"gold.json")}'], out, 'gold')
        if code:
            raise RuntimeError('RTL did not read: '+err[-400:])
        outputs = flop_outputs(text, flops)
        lines, paired, unpaired = aliases(outputs, gold_wires(out/'gold.json', top))
        gate = Path(netlist)
        if lines:
            gate = out/'gate_aliased.v'
            gate.write_text(with_aliases(text, top, lines), encoding='utf-8')
        result['register_names'] = {'flops': len(outputs), 'aliased': sum(max(len(b), 1) for b in paired.values()),
                                    'unpaired_instances': unpaired,
                                    'naming': 'instance names (<path>_reg[<i>]) → aliases' if lines else
                                              'flop outputs carry RTL names'}
        ports = json.loads((out/'gold.json').read_text(encoding='utf-8'))['modules'][top]['ports']
        # Power pins written by P&R (inout VDD/VSS in OpenROAD's final.v) are not RTL ports: drop the port
        # status only. A logic cell that used one would see an undriven net and stay unproven.
        extra = sorted(n for n, p in gate_ports.items() if n not in ports and p['direction'] == 'inout')
        result['gate_only_inout_ports'] = extra
        encfile = None
        if synth_log:
            enc = fsm_encodings(synth_log)
            result['fsm_encodings'] = enc.splitlines()
            if enc:
                encfile = out/'fsm.enc'
                encfile.write_text(enc, encoding='utf-8')
        result['equiv'] = equivalence(sources, top, liberty, gate, out,
                                      [f'delete -port w:{n}' for n in extra], encfile)
        lost = [b for b in result['equiv']['skipped_gold_bits'] if b.split('[')[0] in ports]
        result['equiv']['ports_left_out'] = lost
        if models:
            result['cell_models'] = {'sha256': sha256(models),
                                     'cells': cell_models(models, liberty, set(by_type), flops, out)}
        equiv = result['equiv']
        proved = equiv['exit'] == 0 and not equiv['unproven'] and not lost and equiv['cells']
        models_ok = all(v != 'different' for v in result.get('cell_models', {}).get('cells', {}).values())
        result['status'] = 'pass' if proved and models_ok else 'fail'
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=1)+'\n', encoding='utf-8')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--netlist', type=Path, required=True, help='gate netlist of kit cells')
    parser.add_argument('--liberty', type=Path, required=True, help='kit Liberty (cell functions)')
    parser.add_argument('--out', type=Path, required=True, help='new folder for logs and summary.json')
    parser.add_argument('--rtl', type=Path, nargs='+', help='RTL sources (default: verification/designs/ternary8.json)')
    parser.add_argument('--top', help='top module (default: the design top)')
    parser.add_argument('--cell-models', type=Path, help="kit Verilog cell models to compare with the Liberty")
    parser.add_argument('--synth-log', type=Path,
                        help='Yosys log of the synthesis that made the netlist: its FSM_RECODE state encodings '
                             'go to equiv_make -encfile')
    args = parser.parse_args(argv)
    result = check(args.netlist, args.liberty, args.out, args.rtl, args.top, args.cell_models, args.synth_log)
    equiv = result.get('equiv', {})
    print(f"{result['netlist']['name']}: {result['status']} ({equiv.get('proven')}/{equiv.get('cells')} pairs proven)")
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
