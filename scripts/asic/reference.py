"""Independent LVS reference: final mapped connections + original vendor CDL.

No layout-derived netlist or geometry is read by this converter.
"""
import argparse
import json
from pathlib import Path
import re
import shutil


def convert(data, cdl, top):
    if top not in data.get('modules', {}):
        raise ValueError('mapped top missing')
    module = data['modules'][top]
    definitions = {m[1]: m[2].split() for m in
                   re.finditer(r'^\.SUBCKT\s+(\S+)\s+([^\r\n]+)', cdl, re.M | re.I)}
    ports, names = [], {}
    for port, entry in module['ports'].items():
        bits = entry['bits']
        offset = entry.get('offset', 0)
        for index, bit in enumerate(bits):
            name = port if len(bits) == 1 else f'{port}[{index+offset}]'
            if name in ['VDD', 'VSS']:
                continue
            ports.append(name)
            if bit in names and names[bit] != name:
                raise ValueError('aliased top ports require an explicit wrapper')
            names[bit] = name

    def node(bit):
        if bit in ['0', '1', 'x', 'z']:
            raise ValueError('unmapped logic constant in a cell connection')
        return names.get(bit, f'__net_{bit}')

    result = ['* Reference built from mapped netlist + original cell CDL',
              '.include "cells.spice"', '.SUBCKT '+top+' '+' '.join(ports+['VDD', 'VSS'])]
    instances = set()
    for instance, cell in module['cells'].items():
        master = cell['type']
        if master not in definitions:
            raise ValueError('no independent CDL for '+master)
        pins = definitions[master]
        used = cell['connections']
        expected = set(pins) - {'VDD', 'VSS'}
        if set(used) - expected:
            raise ValueError(f'CDL/netlist pin mismatch: {instance}: {set(used)} != {expected}')
        identifier = re.sub(r'[^\w]', '_', instance)
        if identifier in instances:
            raise ValueError('SPICE instance name collision')
        connections = []
        for pin in pins:
            if pin in ['VDD', 'VSS']:
                connections.append(pin)
            else:
                if pin not in used or not used[pin]:
                    direction = data['modules'].get(master, {}).get('ports', {}).get(pin, {}).get('direction')
                    if direction != 'output':
                        raise ValueError(f'unconnected cell input: {instance}.{pin}')
                    # CTS inserts load-balancing buffers with floating outputs.
                    # Preserve their transistors, using one private node per pin.
                    connections.append(f'__floating_{identifier}_{pin}')
                    continue
                if len(used[pin]) != 1:
                    raise ValueError('non-scalar standard cell pin: '+pin)
                connections.append(node(used[pin][0]))
        instances.add(identifier)
        result.append('X'+identifier+' '+' '.join(connections)+' '+master)
    if not instances:
        raise ValueError('empty mapped design')
    result.append('.ENDS '+top)
    return '\n'.join(result)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--cdl', type=Path, required=True)
    parser.add_argument('--top', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    content = convert(json.loads(args.json.read_text()), args.cdl.read_text(), args.top)
    shutil.copyfile(args.cdl, args.out.parent/'cells.spice')
    args.out.write_text(content)


if __name__ == '__main__':
    main()
