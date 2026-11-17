"""Record the code, contracts, tool results and coverage actually tested."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('lint', 'unit', 'integration', 'regression', 'coverage')


def main():
    output = ROOT/'.policy-tmp/results'
    output.mkdir(parents=True, exist_ok=True)
    event_path = os.getenv('GITHUB_EVENT_PATH')
    event = json.loads(Path(event_path).read_text(encoding='utf-8')) if event_path else {}
    pr = event.get('pull_request', {})
    metadata = {
        'tested_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'base': pr.get('base', {}).get('sha'), 'head': pr.get('head', {}).get('sha'),
        'event': os.getenv('GITHUB_EVENT_NAME', 'local'), 'run_url': None,
        'contract_sha256': {}, 'results': {},
    }
    if os.getenv('GITHUB_RUN_ID'):
        metadata['run_url'] = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    for path in [*sorted((ROOT/'docs/rfcs').glob('*.md')), ROOT/'verification/designs/ternary8.json']:
        content = path.read_bytes().replace(b'\r\n', b'\n')
        metadata['contract_sha256'][path.relative_to(ROOT).as_posix()] = hashlib.sha256(content).hexdigest()
    lines = ['## RTL results', '', f"Tested commit: `{metadata['tested_commit']}`", '',
             '| Suite | Result | Seconds |', '| --- | --- | ---: |']
    for name in NAMES:
        path = output/f'rtl-{name}/summary.json'
        result = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'status': 'not_run'}
        metadata['results'][f'rtl-{name}'] = result
        seconds = f"{result['wall_seconds']:.2f}" if 'wall_seconds' in result else '-'
        lines.append(f"| rtl-{name} | {result['status']} | {seconds} |")
    coverage = metadata['results']['rtl-coverage'].get('result', {}).get('rtl_line_coverage')
    if coverage:
        lines.extend(['', f"RTL line points: {coverage['hit']}/{coverage['found']} ({coverage['percent']:.2f}%). No coverage exclusions."])
        for path, counts in coverage['files'].items():
            if counts['uncovered_lines']:
                lines.append(f"Uncovered: `{Path(path).name}` lines {counts['uncovered_lines']}")
    lines.extend(['', 'ASIC synthesis, P&R, STA, DRC/LVS and board tests: not run by this workflow.', ''])
    text = '\n'.join(lines)
    (output/'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output/'report.md').write_text(text, encoding='utf-8')
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(text)
    print(text)


if __name__ == '__main__':
    main()
