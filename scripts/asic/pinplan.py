"""Proposed SOP28 plan; no approval or pin-budget waiver is inferred."""
import tomllib


def make_plan(path, width, height):
    config = tomllib.loads(path.read_text())
    if width > 1016 or height > 1016:
        raise ValueError('core does not fit the GPIO inner area; revise the floorplan')
    ox, oy = round((1900-width)/2, 3), round((1900-height)/2, 3)
    signals = {number: name for name, number in config['signal_pads'].items()}
    if len(signals) != 13 or len(set(signals.values())) != 13:
        raise ValueError('expected 13 unique package signal pins')
    pads, pins = [], []
    for number in range(1, 29):
        if number <= 7:
            side, px, py = 'left', 140, 1355-135*(number-1)
        elif number <= 14:
            side, px, py = 'bottom', 545+135*(number-8), 140
        elif number <= 21:
            side, px, py = 'right', 1760, 545+135*(number-15)
        else:
            side, px, py = 'top', 1355-135*(number-22), 1760
        signal = signals.get(number)
        net = signal or ('VDD' if number in config['vdd_pads'] else 'VSS')
        master = ('PIC' if signal and signal not in ['IN_READY', 'OUT_VALID'] and not signal.startswith('OUT[')
                  else 'POB4') if signal else ('PVDD' if net == 'VDD' else 'PVSS')
        local_x = {'PIC': 114.6, 'POB4': 6.75, 'PVDD': 58.75, 'PVSS': 57.5}[master]
        if side == 'left':
            gx, gy = 441.5, py+60-local_x
        elif side == 'right':
            gx, gy = 1458.5, py-60+local_x
        elif side == 'bottom':
            gx, gy = px-60+local_x, 441.5
        else:
            gx, gy = px-60+local_x, 1458.5
        row = {'number': number, 'side': side, 'pad': [px, py], 'net': net,
               'master': master, 'gpio': [round(gx, 3), round(gy, 3)]}
        if signal:
            if side == 'left':
                point, layer, size = [3, gy-oy], 'MET3', [6, 1.2]
            elif side == 'right':
                point, layer, size = [width-3, gy-oy], 'MET3', [6, 1.2]
            elif side == 'bottom':
                point, layer, size = [gx-ox, 3], 'MET2', [1, 6]
            else:
                raise ValueError('top-side signal routing not planned')
            if not (0 <= point[0] <= width and 0 <= point[1] <= height):
                raise ValueError('proposed package signal is outside the core boundary')
            row['core'] = [round(point[0]+ox, 3), round(point[1]+oy, 3)]
            pins.append({'name': signal, 'layer': layer,
                         'point': [round(p, 3) for p in point], 'size': size})
        pads.append(row)
    return {'status': config['status'], 'core_origin': [ox, oy], 'core_size': [width, height],
            'used_pins': 28, 'guide_used_pin_limit': config['guide_used_pin_limit'],
            'pin_budget_review_required': True, 'pads': pads, 'core_pins': pins}


def tcl(plan):
    return '\n'.join('place_pin -pin_name {'+p['name']+'} -layer '+p['layer']
                     +' -location {'+' '.join(map(str, p['point']))+'} -pin_size {'
                     +' '.join(map(str, p['size']))+'}' for p in plan['core_pins'])+'\n'
