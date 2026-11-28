"""Rewrite both LVS netlists the same way the kit Calibre LVS deck compares them.

Netgen alone does not do three things the kit deck turns on. This module does
them on each netlist before Netgen reads it, with the same rules on both sides:

1. ``LVS REDUCE PARALLEL MOS YES``: ``m=n`` is n parallel devices, and parallel
   MOS of one model with the same gate, bulk, source/drain pair and L become one
   device whose W is the sum. Devices with different L are left apart.
2. ``LVS RECOGNIZE GATES ALL``: Calibre turns a series MOS chain into one gate
   object whose inputs are swappable (the report shows ``_smn2v``, ``_sup2v``
   ...). Netgen cannot swap them, so a chain is written as a star: a link device
   ``<model>_chain`` between the two chain ends whose gate is a new private
   node, and one ``<model>_chain_gate`` device per original transistor on that
   node, carrying that transistor's gate net, W and L. Order inside the chain is
   lost; everything else (ends, bulk, which gate has which W/L) is kept.
3. ``LVS REDUCE SPLIT GATES YES``: identical chains between the same two ends
   are one chain with each W multiplied by their count.

A chain is a path of two or more transistors of one model and bulk, joined by
nets that touch nothing else: exactly two source/drain pins, no gate, no bulk,
not a subcircuit port, not a global net, not used by any other line. Chains
whose gates repeat, whose two ends are the same net, or that close a loop are
left untouched. Only W and L are traced (deck ``TRACE PROPERTY ... W``/``L``);
AS/AD/PS/PD are dropped. Any other device parameter is an error.
"""
import argparse
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

SCALE = {'f': Decimal('1e-15'), 'p': Decimal('1e-12'), 'n': Decimal('1e-9'), 'u': Decimal('1e-6'),
         'm': Decimal('1e-3'), 'k': Decimal('1e3'), 'meg': Decimal('1e6'), 'g': Decimal('1e9'),
         't': Decimal('1e12')}
MICRON = Decimal('1e-6')
DROPPED = {'AS', 'AD', 'PS', 'PD'}
SUFFIXES = ('_chain', '_chain_gate')


def number(text):
    match = re.fullmatch(r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(meg|[fpnumkgt])?', text, re.I)
    if not match:
        raise ValueError('unsupported SPICE number: '+text)
    try:
        value = Decimal(match[1])
    except InvalidOperation as error:
        raise ValueError('unsupported SPICE number: '+text) from error
    return value * SCALE[match[2].lower()] if match[2] else value


def micron(value):
    text = format((value / MICRON).normalize(), 'f')
    return text+'u'


def logical_lines(path, seen=None):
    """Lines with '+' continuations joined and .include files inlined."""
    path = Path(path).resolve()
    seen = set() if seen is None else seen
    if path in seen:
        raise ValueError('recursive .include: '+str(path))
    seen = seen | {path}
    lines = []
    for raw in path.read_text(encoding='utf-8', errors='strict').splitlines():
        line = raw.strip()
        if line.startswith('+'):
            if not lines:
                raise ValueError('continuation line without a statement')
            lines[-1] += ' '+line[1:].strip()
            continue
        lines.append(line)
    result = []
    for line in lines:
        include = re.fullmatch(r'\.include\s+["\']?([^"\']+)["\']?', line, re.I)
        if include:
            result += logical_lines(path.parent/include[1], seen)
        else:
            result.append(line)
    return result


class Subckt:
    def __init__(self, header):
        self.header = header
        self.ports = set(header.split()[2:])
        self.mos = []
        self.other = []
        self.fixed = set()


def parse(lines):
    """Return (statements outside subcircuits, subcircuits in order)."""
    outside, cells, current, global_nets = [], [], None, set()
    for line in lines:
        if not line or line.startswith('*'):
            continue
        words = line.split()
        key = words[0].lower()
        if key == '.subckt':
            if current is not None or len(words) < 2:
                raise ValueError('bad .SUBCKT: '+line)
            if any('=' in word for word in words):
                raise ValueError('.SUBCKT parameters are not supported: '+line)
            current = Subckt(line)
        elif key == '.ends':
            if current is None:
                raise ValueError('.ENDS without .SUBCKT')
            cells.append(current)
            current = None
        elif key == '.global':
            global_nets |= set(words[1:])
            outside.append(line)
        elif key == '.end':
            continue
        elif key.startswith('.'):
            raise ValueError('unsupported SPICE statement: '+line)
        elif current is None:
            raise ValueError('device outside a subcircuit: '+line)
        elif key[0] == 'm':
            current.mos.append(mos(words))
        else:
            # Subcircuit calls and any non-MOS device are kept verbatim and
            # every net they name is fixed (never a chain-internal net).
            current.other.append(line)
            current.fixed |= {w for w in words[1:] if '=' not in w}
    if current is not None:
        raise ValueError('missing .ENDS')
    for cell in cells:
        cell.fixed |= global_nets
    return outside, cells


def mos(words):
    if len(words) < 6:
        raise ValueError('short MOS line: '+' '.join(words))
    name, d, g, s, b, model = words[:6]
    if model.lower().endswith(SUFFIXES):
        raise ValueError('model name reserved for reduced chains: '+model)
    values = {}
    for word in words[6:]:
        if '=' not in word:
            raise ValueError('unsupported MOS parameter: '+word)
        key, value = word.split('=', 1)
        key = key.upper()
        if key in values:
            raise ValueError('duplicate MOS parameter: '+word)
        values[key] = value
    unknown = set(values) - {'W', 'L', 'M'} - DROPPED
    if unknown or 'W' not in values or 'L' not in values:
        raise ValueError('MOS needs W and L and only M/AS/AD/PS/PD besides: '+' '.join(words))
    m = number(values.get('M', '1'))
    if m != m.to_integral_value() or m < 1:
        raise ValueError('m must be a positive integer: '+' '.join(words))
    w, length = number(values['W']), number(values['L'])
    if w <= 0 or length <= 0:
        raise ValueError('W and L must be positive: '+' '.join(words))
    return {'name': name, 'd': d, 'g': g, 's': s, 'b': b, 'model': model, 'w': w * m, 'l': length}


def merge_parallel(devices):
    """REDUCE PARALLEL MOS: same model, gate, bulk, S/D pair and L -> W summed."""
    merged, order = {}, []
    for device in devices:
        key = (device['model'], device['g'], device['b'], device['l'], frozenset((device['d'], device['s'])))
        if key in merged:
            merged[key]['w'] += device['w']
        else:
            merged[key] = dict(device)
            order.append(key)
    return [merged[key] for key in order]


def chains(cell, devices):
    """Series chains as lists of (device index) with their two end nets."""
    uses = {}
    for index, device in enumerate(devices):
        for role in ('d', 's'):
            uses.setdefault(device[role], []).append(index)
    blocked = set(cell.ports) | cell.fixed
    blocked |= {device[role] for device in devices for role in ('g', 'b')}
    internal = {}
    for net, users in uses.items():
        if net in blocked or len(users) != 2 or users[0] == users[1]:
            continue
        first, second = devices[users[0]], devices[users[1]]
        if (first['model'], first['b']) != (second['model'], second['b']):
            continue
        internal[net] = users
    links = {}
    for net, (first, second) in internal.items():
        links.setdefault(first, []).append((net, second))
        links.setdefault(second, []).append((net, first))
    found, done = [], set()
    for start in sorted(links):
        if start in done or len(links[start]) != 1:
            continue
        path, nets, previous, current = [start], set(), None, start
        while True:
            done.add(current)
            step = [(net, other) for net, other in links[current] if net not in nets]
            if not step:
                break
            net, other = step[0]
            nets.add(net)
            path.append(other)
            current = other
        ends = [end_net(devices[path[0]], nets), end_net(devices[path[-1]], nets)]
        gates = [devices[i]['g'] for i in path]
        if len(set(gates)) != len(gates) or ends[0] == ends[1]:
            continue
        found.append((path, ends))
    # Devices only in loops (no end device) are never visited and stay as-is.
    return found


def end_net(device, internal):
    outer = [net for net in (device['d'], device['s']) if net not in internal]
    if len(outer) != 1:
        raise ValueError('chain end is not a single net')
    return outer[0]


def reduce_cell(cell):
    devices = merge_parallel(cell.mos)
    found = chains(cell, devices)
    in_chain = {i for path, _ends in found for i in path}
    plain = [d for i, d in enumerate(devices) if i not in in_chain]
    groups, order = {}, []
    for path, ends in found:
        first = devices[path[0]]
        members = tuple(sorted((devices[i]['g'], devices[i]['l'], devices[i]['w']) for i in path))
        key = (first['model'], first['b'], frozenset(ends), members)
        if key in groups:
            groups[key]['count'] += 1
        else:
            groups[key] = {'model': first['model'], 'b': first['b'], 'ends': ends,
                           'members': members, 'name': first['name'], 'count': 1}
            order.append(key)
    names = {d['name'] for d in cell.mos} | {line.split()[0] for line in cell.other}
    nets = set(cell.ports) | cell.fixed | {d[r] for d in cell.mos for r in ('d', 'g', 's', 'b')}
    lines = [cell.header]
    for device in plain:
        lines.append(f"{device['name']} {device['d']} {device['g']} {device['s']} {device['b']} "
                     f"{device['model']} W={micron(device['w'])} L={micron(device['l'])}")
    for number_, key in enumerate(order, 1):
        chain = groups[key]
        node = fresh(f'chain{number_}', nets)
        link = fresh(f'Mchain{number_}', names)
        lines.append(f"{link} {chain['ends'][0]} {node} {chain['ends'][1]} {chain['b']} {chain['model']}_chain")
        for index, (gate, length, width) in enumerate(chain['members'], 1):
            element = fresh(f'{link}_{index}', names)
            lines.append(f"{element} {node} {gate} {node} {chain['b']} {chain['model']}_chain_gate "
                         f"W={micron(width * chain['count'])} L={micron(length)}")
    lines += cell.other
    lines.append('.ENDS')
    return lines, {'mos_in': len(cell.mos), 'mos_after_parallel': len(devices),
                   'chains': sum(g['count'] for g in groups.values()), 'chain_groups': len(order)}


def fresh(base, used):
    name, n = base, 1
    while name in used:
        n += 1
        name = f'{base}_{n}'
    used.add(name)
    return name


def reduce_netlist(source, target):
    outside, cells = parse(logical_lines(source))
    lines = ['* Reduced for Netgen LVS by scripts/asic/lvs_reduce.py (kit Calibre deck semantics)']
    lines += outside
    summary = {}
    for cell in cells:
        name = cell.header.split()[1]
        if name in summary:
            raise ValueError('duplicate .SUBCKT: '+name)
        cell_lines, summary[name] = reduce_cell(cell)
        lines += cell_lines + ['']
    Path(target).write_text('\n'.join(lines)+'\n', encoding='utf-8', newline='\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    for name, counts in reduce_netlist(args.source, args.target).items():
        print(name, counts)


if __name__ == '__main__':
    main()
