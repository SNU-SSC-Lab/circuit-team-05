"""RTL <-> gate netlist check (SPEC 0019, table row `synth`; flow check `asic-synth-equiv`).

Gold is the team RTL, flattened. Gate is a netlist of kit cells, each cell being its Liberty
function (read_liberty), as in pdk.gate_model. Four parts, all must pass:

1. Ports (structure): gold and gate have the same ports, same direction and width. Only inout
   ports that P&R adds (VDD/VSS in OpenROAD's final.v) are ignored.
2. Clocks (structure): every gold register is a rising-edge flop on the clock port with no
   asynchronous set/reset, and every gate flop is a Liberty ff clocked on the rising edge of its
   clock pin, without clear/preset, with that pin wired straight to the clock port. Latch cells fail.
   The SAT models of parts 3 and 4 treat every flop as "Q <- D each step" and do not see clocks,
   which is why this is checked separately.
3. Next-state functions (formal): equiv_make pairs signals of the same name, equiv_simple and
   equiv_induct prove every pair (equiv_status -assert). Output ports are always pairs.
4. Start condition (formal, bounded): from any initial state, one cycle with the reset held low
   makes every pair equal for the following cycles (SAT on equiv_miter). This is the base case the
   induction of part 3 needs.

Registers are paired by name. Yosys and OpenROAD keep the RTL names on flop outputs (`\\u_tx.result_shift [3]`).
Genus names the flop instance instead (`\\u_tx_result_shift_reg[3]`) and may name its output anything
(`\\u_weights_WEIGHTS[2]_108`, `term_negate`); for such a netlist the gate copy gets alias wires that
carry the gold name. Aliases only add names; no cell changes. A wrong pairing cannot make the check
pass: a pair of unrelated signals stays unproven. Yosys FSM recodings come from the synthesis log
(equiv_make -encfile). --cell-models compares the kit's Verilog models of the combinational cells the
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
BASE_STEPS = SEQ + 3       # reset cycle + more cycles than equiv_induct assumes
GOLD_FLOPS = {'$dff', '$dffe', '$sdff', '$sdffe', '$sdffce'}
GOLD_STATE = re.compile(r'dff|dlatch|latch|\$sr\b|\$_SR|\$ff$|\$_FF_|aldff', re.I)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _cells(liberty_text):
    return [(m.start(), m.group(1)) for m in re.finditer(r'\bcell\s*\(\s*"?(\w+)"?\s*\)', liberty_text)]


def sequential_cells(liberty_text):
    """{cell: {'kind': 'ff'|'latch', 'clocked_on': str, 'async': bool}} for cells with an ff or latch group."""
    cells, found = _cells(liberty_text), {}
    for m in re.finditer(r'\b(ff|latch)\s*\([^)]*\)\s*\{([^}]*)\}', liberty_text):
        owner = [name for start, name in cells if start < m.start()]
        if not owner:
            continue
        body = m.group(2)
        clock = re.search(r'\b(?:clocked_on|enable)\s*:\s*"?([^";]+?)"?\s*;', body)
        found[owner[-1]] = {'kind': m.group(1), 'clocked_on': clock.group(1).strip() if clock else '',
                            'async': bool(re.search(r'\b(clear|preset)\s*:', body))}
    return found


def flop_cells(liberty_text):
    """Names of the Liberty cells that have an ff group (the kit's flip-flops)."""
    return {name for name, info in sequential_cells(liberty_text).items() if info['kind'] == 'ff'}


def _pin(body, pin):
    m = re.search(r'\.' + re.escape(pin) + r'\s*\(\s*(.*?)\s*\)\s*(?:,|$)', body, re.S)
    return ' '.join(m.group(1).split()) if m and m.group(1) else None


def flop_outputs(netlist_text, flops):
    """[(instance, Q expression)] of every flop instance; instance names without the Verilog escape."""
    found = []
    for cell, instance, body in INSTANCE.findall(netlist_text):
        if cell in flops and (q := _pin(body, 'Q')):
            found.append((instance.lstrip('\\'), q))
    return found


def gate_clock_problems(netlist_text, sequential, clock):
    """Problems with the gate's sequential cells: wrong kind, edge, async pins, or clock not the clock port."""
    problems, flops = [], 0
    for cell, instance, body in INSTANCE.findall(netlist_text):
        info = sequential.get(cell)
        if info is None:
            continue
        name = instance.lstrip('\\')
        if info['kind'] != 'ff':
            problems.append(f'{name}: {cell} is a latch')
            continue
        flops += 1
        pin = info['clocked_on']
        if not re.fullmatch(r'\w+', pin):
            problems.append(f'{name}: {cell} is clocked on "{pin}", not a rising edge')
        elif info['async']:
            problems.append(f'{name}: {cell} has an asynchronous clear/preset')
        elif (net := _pin(body, pin)) not in (clock, '\\' + clock):
            problems.append(f'{name}: {cell}.{pin} on {net!r}, not the clock port {clock}')
    return problems, flops


def gold_clock_problems(gold, top, clock):
    """Problems with the RTL registers: only rising-edge flops on the clock port, no async set/reset."""
    module = gold['modules'][top]
    if clock not in module['ports']:
        return [f'RTL has no clock port {clock}'], 0
    clock_bits = module['ports'][clock]['bits']
    problems, flops = [], 0
    for name, cell in module['cells'].items():
        kind = cell['type']
        if kind in GOLD_FLOPS:
            flops += len(cell['connections'].get('Q', []))
            polarity = cell['parameters'].get('CLK_POLARITY', 1)
            polarity = int(polarity, 2) if isinstance(polarity, str) else int(polarity)
            if polarity != 1:
                problems.append(f'RTL register {name}: falling-edge clock')
            if cell['connections'].get('CLK') != clock_bits:
                problems.append(f'RTL register {name}: clock is not the port {clock}')
        elif GOLD_STATE.search(kind):
            problems.append(f'RTL register {name}: {kind} (not a synchronous flop)')
    return problems, flops


def port_problems(gold_ports, gate_ports, ignored=()):
    """Port name, direction and width differences between gold and gate (ignored: gate-only P&R inouts)."""
    problems = []
    for name in sorted((set(gold_ports) | set(gate_ports)) - set(ignored)):
        g, t = gold_ports.get(name), gate_ports.get(name)
        if g is None or t is None:
            problems.append(f'port {name} only in {"gate" if g is None else "RTL"}')
        elif (g['direction'], len(g['bits'])) != (t['direction'], len(t['bits'])):
            problems.append(f'port {name}: RTL {g["direction"]}[{len(g["bits"])}] vs gate {t["direction"]}[{len(t["bits"])}]')
    return problems


def gold_wires(gold_json, top):
    """{dotted name: (offset, width, upto)} of the flattened gold's public wires."""
    nets = json.loads(Path(gold_json).read_text(encoding='utf-8'))['modules'][top]['netnames']
    return {name: (int(n.get('offset', 0)), len(n['bits']), bool(n.get('upto', 0)))
            for name, n in nets.items() if not n.get('hide_name')}


def declared(netlist_text):
    """Names declared as wire/input/output/inout in the netlist (without the Verilog escape)."""
    names = set()
    for m in re.finditer(r'\b(?:wire|input|output|inout)\s+(?:\[[^\]]*\]\s*)?([^;]+);', netlist_text):
        names.update(n.strip().lstrip('\\') for n in m.group(1).split(','))
    return names


def aliases(outputs, wires, existing=frozenset()):
    """Alias lines for flops named <path>_reg[<i>] (Genus): gold wire bit <path>[<i>] = flop output.

    <path> uses "_" where the gold uses "."; a gold name maps only when exactly one gold wire matches.
    A flop whose output already is that bit needs no alias; a name already declared is not declared again.
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
        same = {name, '\\' + name} if pairs[0][0] is None else set()
        todo = [(i, q) for i, q in pairs
                if q.replace(' ', '').lstrip('\\') not in (same | {f'{name}[{i}]'})]
        if not todo:
            continue
        span = '' if pairs[0][0] is None else (f'[{offset}:{offset+width-1}] ' if upto else f'[{offset+width-1}:{offset}] ')
        if name not in existing:
            lines.append(f'  wire {span}\\{name} ;')
        for index, q in sorted(todo, key=lambda p: -1 if p[0] is None else p[0]):
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


def _paired(sources, top, liberty, netlist, gate_extra, encfile):
    make = 'equiv_make' + (f' -encfile {pdk.q(encfile)}' if encfile else '') + ' gold gate equiv'
    return gold_lines(sources, top) + ['rename -top gold', 'design -stash gold'] + \
        gate_lines(liberty, netlist, top) + list(gate_extra) + ['rename -top gate', 'design -stash gate',
        'design -copy-from gold -as gold gold', 'design -copy-from gate -as gate gate', make, 'hierarchy -top equiv']


def equivalence(sources, top, liberty, netlist, work, gate_extra=(), encfile=None):
    """Part 3: register-correspondence proof (equiv_*). Returns the result dict."""
    lines = _paired(sources, top, liberty, netlist, gate_extra, encfile) + [
        f'equiv_simple -seq {SEQ}', f'equiv_induct -seq {SEQ}',
        f'tee -o {pdk.q(work/"equiv_status.txt")} equiv_status', 'equiv_status -assert']
    code, err, log = run_yosys(lines, work, 'equiv')
    status = (work/'equiv_status.txt').read_text(encoding='utf-8') if (work/'equiv_status.txt').is_file() else ''
    counts = STATUS.search(status)
    unproven = re.findall(r'Unproven \$equiv \S+: (\S+)_gold(?: \[(\d+)\])?', status)
    skipped = [f'{n}[{i}]' if i else n for n, i in SKIPPED.findall(log)]
    return {'exit': code, 'detail': err[-400:] if code else '',
            'cells': int(counts.group(1)) if counts else None, 'proven': int(counts.group(2)) if counts else None,
            'unproven': [f'{n.lstrip(chr(92))}[{i}]' if i else n.lstrip(chr(92)) for n, i in unproven],
            'skipped_gold_bits': skipped}


def base_case(sources, top, liberty, netlist, work, reset, gate_extra=(), encfile=None, steps=BASE_STEPS):
    """Part 4: free initial state, reset low in cycle 1; every pair must agree in cycles 2..steps."""
    lines = _paired(sources, top, liberty, netlist, gate_extra, encfile) + [
        'equiv_miter -trigger -assert miter equiv', 'hierarchy -top miter', 'flatten', 'opt_clean',
        f'sat -verify -seq {steps} -set-at 1 {reset} 0 -prove-skip 1 -prove-asserts miter']
    code, err, _ = run_yosys(lines, work, 'base_case')
    return {'status': 'pass' if code == 0 else 'fail', 'steps': steps, 'reset': f'{reset}=0 in cycle 1',
            'initial_state': 'free', 'detail': err[-400:] if code else ''}


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


def check(netlist, liberty, out, sources=None, top=None, models=None, synth_log=None,
          clock='CLK', reset='RST_N', require_kit=True):
    out = Path(out)
    if out.exists():
        raise ValueError(f'{out} exists; choose a new folder')
    out.mkdir(parents=True)
    top = top or pdk.DESIGN['top']
    sources = [Path(s) for s in (sources or pdk.sources())]
    lib_text = Path(liberty).read_text(encoding='utf-8', errors='replace')
    sequential = sequential_cells(lib_text)
    flops = {name for name, info in sequential.items() if info['kind'] == 'ff'}
    text = Path(netlist).read_text(encoding='utf-8', errors='replace')
    version = subprocess.run(['yosys', '-V'], capture_output=True, text=True).stdout.strip()
    kit = sha256(liberty) == pdk.PDK['digital']['liberty_sha256']
    result = {'netlist': {'name': Path(netlist).name, 'sha256': sha256(netlist)},
              'liberty_sha256': sha256(liberty), 'kit_liberty': kit,
              'rtl': {'top': top, 'sha256': {s.name: sha256(s) for s in sources}},
              'yosys': version, 'cell_model': 'Liberty function (read_liberty)', 'clock': clock, 'reset': reset}
    problems = [] if kit or not require_kit else ['Liberty is not the kit file of verification/pdk/pdk.toml']

    def finish():
        result['problems'] = problems
        result['status'] = 'fail' if problems else 'pass'
        (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=1)+'\n', encoding='utf-8')
        return result

    code, err, _ = run_yosys([f'read_liberty -lib {pdk.q(liberty)}'] + gate_lines(liberty, netlist, top)[1:3] +
                             [f'tee -q -o {pdk.q(out/"gate_stat.json")} stat -json',
                              f'write_json {pdk.q(out/"gate_ports.json")}'], out, 'gate_stat')
    if code:
        problems.append('netlist does not read on the kit cells: '+err[-400:])
        return finish()
    design = json.loads((out/'gate_stat.json').read_text(encoding='utf-8'))['design']
    by_type = design.get('num_cells_by_type', {})
    gate_ports = json.loads((out/'gate_ports.json').read_text(encoding='utf-8'))['modules'][top]['ports']
    result['netlist'].update(cells=design.get('num_cells'), by_type=dict(sorted(by_type.items())),
                             flops=sum(n for c, n in by_type.items() if c in flops))
    code, err, _ = run_yosys(gold_lines(sources, top) + [f'write_json {pdk.q(out/"gold.json")}'], out, 'gold')
    if code:
        problems.append('RTL did not read: '+err[-400:])
        return finish()
    gold = json.loads((out/'gold.json').read_text(encoding='utf-8'))
    ports = gold['modules'][top]['ports']

    # 1. ports (P&R power pins are the only gate-only ports allowed)
    extra = sorted(n for n, p in gate_ports.items() if n not in ports and p['direction'] == 'inout')
    result['gate_only_inout_ports'] = extra
    result['ports'] = {'problems': port_problems(ports, gate_ports, extra)}
    result['ports']['status'] = 'fail' if result['ports']['problems'] else 'pass'
    problems += result['ports']['problems']
    if reset not in ports or ports[reset]['direction'] != 'input':
        problems.append(f'RTL has no reset input {reset}')

    # 2. clocks (structure; the SAT models below do not see clock pins)
    gold_problems, gold_flops = gold_clock_problems(gold, top, clock)
    gate_problems, gate_flops = gate_clock_problems(text, sequential, clock)
    result['clocks'] = {'status': 'fail' if gold_problems or gate_problems else 'pass',
                        'rtl_register_bits': gold_flops, 'gate_flops': gate_flops,
                        'problems': (gold_problems + gate_problems)[:40]}
    problems += result['clocks']['problems']

    # 3. next-state functions, 4. start condition
    outputs = flop_outputs(text, flops)
    lines, paired, unpaired = aliases(outputs, gold_wires(out/'gold.json', top), declared(text))
    gate = Path(netlist)
    if lines:
        gate = out/'gate_aliased.v'
        gate.write_text(with_aliases(text, top, lines), encoding='utf-8')
    result['register_names'] = {'flops': len(outputs), 'aliased': sum(max(len(b), 1) for b in paired.values()),
                                'unpaired_instances': unpaired if lines else [],
                                'naming': 'instance names (<path>_reg[<i>]) -> aliases' if lines else
                                          'flop outputs carry RTL names'}
    encfile = None
    if synth_log:
        enc = fsm_encodings(synth_log)
        result['fsm_encodings'] = enc.splitlines()
        if enc:
            encfile = out/'fsm.enc'
            encfile.write_text(enc, encoding='utf-8')
    strip = [f'delete -port w:{n}' for n in extra]
    equiv = result['equiv'] = equivalence(sources, top, liberty, gate, out, strip, encfile)
    equiv['ports_left_out'] = [b for b in equiv['skipped_gold_bits'] if b.split('[')[0] in ports]
    if equiv['exit'] or equiv['unproven'] or not equiv['cells']:
        problems.append(f"next-state proof: {equiv['proven']}/{equiv['cells']} pairs proven")
    if equiv['ports_left_out']:
        problems.append('output bits without a gate signal: ' + ', '.join(equiv['ports_left_out']))
    if reset in ports:
        result['base_case'] = base_case(sources, top, liberty, gate, out, reset, strip, encfile)
        if result['base_case']['status'] != 'pass':
            problems.append('start condition: pairs differ after a reset cycle')
    if models:
        result['cell_models'] = {'sha256': sha256(models),
                                 'cells': cell_models(models, liberty, set(by_type), flops, out)}
        problems += [f'kit Verilog model of {c} differs from its Liberty function'
                     for c, v in result['cell_models']['cells'].items() if v == 'different']
    return finish()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--netlist', type=Path, required=True, help='gate netlist of kit cells')
    parser.add_argument('--liberty', type=Path, required=True, help='kit Liberty (cell functions)')
    parser.add_argument('--out', type=Path, required=True, help='new folder for logs and summary.json')
    parser.add_argument('--rtl', type=Path, nargs='+', help='RTL sources (default: verification/designs/ternary8.json)')
    parser.add_argument('--top', help='top module (default: the design top)')
    parser.add_argument('--clock', default='CLK', help='clock input port')
    parser.add_argument('--reset', default='RST_N', help='active-low synchronous reset input port')
    parser.add_argument('--cell-models', type=Path, help="kit Verilog cell models to compare with the Liberty")
    parser.add_argument('--synth-log', type=Path,
                        help='Yosys log of the synthesis that made the netlist: its FSM_RECODE state encodings '
                             'go to equiv_make -encfile')
    parser.add_argument('--any-liberty', action='store_true', help='do not require the kit Liberty of pdk.toml')
    args = parser.parse_args(argv)
    result = check(args.netlist, args.liberty, args.out, args.rtl, args.top, args.cell_models, args.synth_log,
                   args.clock, args.reset, not args.any_liberty)
    equiv = result.get('equiv', {})
    print(f"{result['netlist']['name']}: {result['status']} ({equiv.get('proven')}/{equiv.get('cells')} pairs proven, "
          f"ports {result.get('ports', {}).get('status')}, clocks {result.get('clocks', {}).get('status')}, "
          f"start {result.get('base_case', {}).get('status')})")
    for problem in result['problems'][:20]:
        print('- ' + problem)
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
