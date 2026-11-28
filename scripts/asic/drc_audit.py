"""Validate the whole source inventory and audit one GDS using geometry ports."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from drc_catalog import validate, markdown, sha, CATALOG
from drc_ports import PORTS

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk', type=Path, required=True)
    parser.add_argument('--gds', type=Path, required=True)
    parser.add_argument('--top', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result = {'status': 'fail', 'qualified_process_drc': False, 'top': args.top}
    try:
        catalog = validate(args.pdk)
        inputs = [Path(__file__).with_name(name) for name in
                  ['drc.py', 'drc_geometry.py', 'drc_ports.py', 'drc_catalog.py']]+[CATALOG]
        result['implementation_hashes'] = {p.name: sha(p.read_bytes()) for p in inputs}
        result['source_hashes'] = {name: value['sha256'] for name,value in catalog['sources'].items()}
        (out/'rules.md').write_text(markdown(catalog), encoding='utf-8')
        before = sha(args.gds.read_bytes())
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', SSC_DRC_PROFILE='expanded',
                   SSC_GDS=str(args.gds.resolve()), SSC_TOP=args.top, SSC_DRC_OUT=str(out/'geometry.json'))
        result['klayout'] = subprocess.check_output(['klayout', '-v'], env=env, text=True, timeout=20).strip()
        with (out/'geometry.log').open('w') as log:
            run = subprocess.run(['klayout', '-b', '-r', str(Path(__file__).with_name('drc.py'))],
                                 env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        geometry = json.loads((out/'geometry.json').read_text())
        if set(geometry['rules']) != set(PORTS) or geometry['top'] != args.top:
            raise ValueError('missing geometry check or wrong GDS top')
        if sha(args.gds.read_bytes()) != before:
            raise ValueError('GDS changed during the audit')
        if any(sha(p.read_bytes()) != result['implementation_hashes'][p.name] for p in inputs):
            raise ValueError('DRC implementation changed during the audit')
        result.update(status='fail' if geometry['errors'] or run.returncode else 'incomplete',
                      gds_sha256=before, errors=geometry['errors'], tool_exit_code=run.returncode,
                      active_source_rules=len(catalog['rules']), geometry_ports=len(PORTS),
                      unported=len(catalog['rules'])-len(PORTS), golden_compared=False)
    except Exception as error:
        result['error'] = str(error)
    result['wall_seconds'] = round(time.monotonic()-started, 3)
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    text = '# NSPL 확장 기하 검사: '+args.top+'\n\n'
    text += '**공정 전체 DRC 미완료 · 원본 도구 교차 대조 미실행**\n\n'
    text += f'상태: {result["status"]} · 시간: {result["wall_seconds"]}초\n\n'
    text += f'활성 원본: {result.get("active_source_rules", "-")}개 · 구현 기하 검사: {len(PORTS)}개 · '
    text += f'오류 마커: {result.get("errors", "-")}개\n\n'
    if result.get('error'):
        text += '실행 오류: '+result['error']+'\n'
    elif result['errors']:
        text += '| 규칙 | 마커 수 |\n| --- | --- |\n'
        text += '\n'.join(f'| {name} | {value["errors"]} |' for name,value in geometry['rules'].items() if value['errors'])+'\n'
    text += '\n정확한 범위·좌표는 geometry.json, 미구현·원본 대조는 rules.md를 확인한다.\n'
    (out/'summary.md').write_text(text, encoding='utf-8')
    print(json.dumps(result), flush=True)
    return int(result['status'] == 'fail')

if __name__ == '__main__':
    raise SystemExit(main())
