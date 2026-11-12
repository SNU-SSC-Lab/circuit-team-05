"""Measure CI suites sequentially without dropping failed or slow suites."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SUITES = ('pr-policy', 'policy-unit', 'rtl-lint', 'rtl-unit',
          'rtl-integration', 'rtl-regression', 'rtl-coverage')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suites', nargs='+', choices=SUITES, default=list(SUITES))
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--build-root', type=Path, default=ROOT/'.policy-tmp/rtl-build')
    parser.add_argument('--output', type=Path, default=ROOT/'.policy-tmp/benchmark')
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'started_utc': datetime.now(timezone.utc).isoformat(),
              'platform': platform.platform(), 'python': sys.version,
              'setup_seconds_included': False, 'runs': [], 'summary': {}}
    total_start = time.perf_counter()
    environment = dict(os.environ)
    environment['PATH'] = str(Path(sys.executable).parent)+os.pathsep+environment.get('PATH', '')
    for repeat in range(1, args.repeats+1):
        for suite in args.suites:
            folder = output/f'run-{repeat}'/suite
            folder.mkdir(parents=True, exist_ok=True)
            if suite == 'pr-policy':
                command = [sys.executable, 'scripts/ci_policy.py']
            elif suite == 'policy-unit':
                command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests/policy', '-v']
            else:
                command = [sys.executable, 'scripts/run_rtl.py', suite.removeprefix('rtl-'),
                           '--build-root', str(args.build_root.resolve()), '--output', str(folder)]
            start = time.perf_counter()
            result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True)
            elapsed = time.perf_counter()-start
            (folder/'command.log').write_text(result.stdout+result.stderr, encoding='utf-8')
            record = {'suite': suite, 'repeat': repeat, 'wall_seconds': elapsed,
                      'status': 'passed' if result.returncode == 0 else 'failed',
                      'exit_code': result.returncode, 'command': command}
            detail = folder/'summary.json'
            if detail.is_file():
                record['rtl_result'] = json.loads(detail.read_text(encoding='utf-8'))
            report['runs'].append(record)
            print(f'{suite}: {record["status"]} {elapsed:.3f}s', flush=True)
            # Save partial progress if a later suite is interrupted.
            (output/'benchmark.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for suite in args.suites:
        runs = [r for r in report['runs'] if r['suite'] == suite]
        values = [r['wall_seconds'] for r in runs]
        report['summary'][suite] = {'runs': len(runs), 'min_seconds': min(values),
                                   'median_seconds': statistics.median(values), 'max_seconds': max(values),
                                   'status': 'passed' if all(r['status'] == 'passed' for r in runs) else 'failed'}
    report['total_wall_seconds'] = time.perf_counter()-total_start
    (output/'benchmark.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return int(any(r['status'] != 'passed' for r in report['runs']))


if __name__ == '__main__':
    sys.exit(main())
