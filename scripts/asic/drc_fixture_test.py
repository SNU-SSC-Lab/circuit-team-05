"""KLayout batch test: target each rule, including exact numeric boundaries."""
import json
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pya
from drc_cases import cases
from drc_geometry import check
from drc_ports import PORTS
import reliability

def main():
    out = Path(os.environ['SSC_DRC_TEST_OUT'])
    # A JSON round trip gives plain lists and dicts: the builder below sees exactly what case_sha256
    # hashes, so a list or dict subclass in drc_cases.py cannot show the hash one shape and KLayout another.
    fixtures = json.loads(json.dumps(cases()))
    if {case['rule'] for case in fixtures} != set(PORTS):
        raise ValueError('a geometry port has no fixture or a fixture names an unknown check')
    by_rule, records, failures = {}, [], []
    started = time.monotonic()
    for index, case in enumerate(fixtures):
        layout = pya.Layout()
        layout.dbu = case['dbu']
        top = layout.create_cell('fixture')
        cell = layout.create_cell('leaf') if case['hierarchy'] else top
        for layer, shape in case['shapes']:
            shapes = cell.shapes(layout.layer(layer, 0))
            if isinstance(shape[0], list):
                shapes.insert(pya.DPolygon([pya.DPoint(*p) for p in shape]))
            else:
                shapes.insert(pya.DBox(*shape))
        if case['hierarchy']:
            middle = layout.create_cell('middle')
            middle.insert(pya.DCellInstArray(cell.cell_index(), pya.DCplxTrans(1, 90, True, 30, 40)))
            top.insert(pya.DCellInstArray(middle.cell_index(), pya.DTrans()))
        name = re.sub(r'[^A-Za-z0-9_.-]', '_', f'{index:04}-{case["rule"]}-{case["label"]}')
        path = out/(name+'.gds')
        top.write(str(path))
        # Test the saved GDS, not just the in-memory construction.
        saved = pya.Layout()
        saved.read(str(path))
        record = {k:v for k,v in case.items() if k != 'shapes'}
        record['gds'] = path.name
        record['case_sha256'] = reliability.case_sha256(case)
        try:
            result = check(saved, saved.cell('fixture'), [case['rule']])
            value = result['rules'][case['rule']]
            record.update(value)
            passed = (value['errors'] > 0) == case['fail'] and not case['raises']
            if case['hierarchy'] and value['errors']:
                # Rotation/mirroring plus translation must reach report coordinates.
                passed &= all(box[0] > 20 and box[1] > 30 for box in value['first_boxes_um'])
        except ValueError as error:
            record['error'] = str(error)
            passed = case['raises'] and 'dbu cannot represent' in str(error)
        record['test_status'] = 'pass' if passed else 'fail'
        by_rule.setdefault(case['rule'], []).append(record)
        records.append(record)
        if not passed:
            failures.append(name)
            print('UNEXPECTED', name, json.dumps(record), flush=True)
    for rule, items in by_rule.items():
        if not any(item['fail'] for item in items) or not any(not item['fail'] for item in items):
            raise ValueError('each port needs both positive and negative fixtures: '+rule)
    result = {'status': 'fail' if failures else 'pass', 'fixtures': len(records),
              'ported_rules': len(by_rule), 'failed_fixtures': failures,
              'wall_seconds': round(time.monotonic()-started, 3),
              # Calibre agreement lives in verification/reliability (reliability.py check), not here;
              # record the rule states drc-rules.json declares for the rules these fixtures test.
              'rule_states': reliability.state_counts(
                  json.loads(reliability.RULES_JSON.read_text(encoding='utf-8')), set(by_rule)),
              'records': records}
    (out/'selftest.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'records'}), flush=True)
    if failures:
        raise ValueError('DRC fixture failures: '+', '.join(failures))

main()
