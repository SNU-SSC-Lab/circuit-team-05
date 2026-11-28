"""Run real KLayout negative fixtures; no PDK or fabricated pass reports."""
import argparse
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', SSC_FIXTURES=str(out))
    subprocess.run(['klayout', '-b', '-r', str(HERE/'fixtures.py')], env=env, check=True, timeout=60)
    results = {}
    for name in ['clean', 'stacked', 'narrow', 'hierarchy']:
        report = out/(name+'.json')
        env.update(SSC_GDS=str(out/(name+'.gds')), SSC_TOP='fixture', SSC_DRC_OUT=str(report))
        with (out/(name+'.log')).open('w') as stream:
            run = subprocess.run(['klayout', '-b', '-r', str(HERE/'drc.py')], env=env,
                                 stdout=stream, stderr=subprocess.STDOUT, timeout=60)
        data = json.loads(report.read_text())
        expected = name == 'clean'
        if (run.returncode == 0) != expected or (data['errors'] == 0) != expected:
            raise ValueError('DRC fixture verdict wrong: '+name)
        if name == 'stacked' and not data['rules']['9.VIA1.S.overlap']['errors']:
            raise ValueError('stacked cuts escaped the specific inter-cut rule')
        results[name] = {'expected_pass': expected, 'errors': data['errors'], 'exit_code': run.returncode}
    for name in ['connected', 'open', 'internal-short']:
        report = out/(name+'.json')
        env.update(SSC_CORE_GDS=str(out/'core.gds'), SSC_CORE_TOP='core',
                   SSC_CHIP_GDS=str(out/(name+'.gds')), SSC_CHIP_ASSEMBLY=str(out/(name+'-assembly.json')),
                   SSC_CHIP_CHECK_OUT=str(report))
        with (out/(name+'.log')).open('w') as stream:
            run = subprocess.run(['klayout', '-b', '-r', str(HERE/'chip_check.py')], env=env,
                                 stdout=stream, stderr=subprocess.STDOUT, timeout=60)
        data = json.loads(report.read_text())
        expected = name == 'connected'
        if (run.returncode == 0) != expected or (data['status'] == 'pass') != expected:
            raise ValueError('connectivity fixture verdict wrong: '+name)
        if name == 'internal-short' and not data['merged_core_components']:
            raise ValueError('unobserved internal short escaped component comparison')
        results[name] = {'expected_pass': expected, 'exit_code': run.returncode}
    (out/'selftest.json').write_text(json.dumps(results, indent=2)+'\n')
    print('7 real geometry fixtures passed (2 positive, 5 intentional violations).')

if __name__ == '__main__':
    main()
