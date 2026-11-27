"""Readable reports with implementation results and qualification gaps apart."""
from html import escape
from pathlib import Path

MARK = {'pass': '통과', 'fail': '실패', 'unsupported': '미확인', 'not_run': '미실행', 'incomplete': '미완료'}


def render(result, out):
    out = Path(out)
    checks = result['checks']
    rows, html_rows = [], []
    for name, check in checks.items():
        status = MARK.get(check['status'], check['status'])
        seconds = str(check.get('wall_seconds', '-'))
        detail = check.get('detail', '')
        if 'errors' in check:
            detail += f' 오류 마커 {check["errors"]}개'
        if 'devices' in check:
            detail += f' 추출 소자 {check["devices"]}개'
        if 'slacks_ns' in check:
            detail += f' setup/hold slack {check["slacks_ns"]} ns; TT 추정 RC'
        if 'clock_sinks' in check:
            detail += f' clock sink {check["clock_sinks"]}/{check["expected_flops"]}'
        log = check.get('log', check.get('report', ''))
        rows.append(f'| {name} | {status} | {seconds} | {detail} |')
        link = f'<a href="{escape(log, quote=True)}">로그</a>' if log else ''
        html_rows.append('<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in [name, status, seconds, detail])+f'<td>{link}</td></tr>')
    title = '5팀 RTL → GDS 구현 실험'
    notice = '실험 결과입니다. 공정 RC 보정·전체 DRC·GPIO LVS/타이밍·핀맵 검토가 완료되지 않아 제작 제출 준비는 미완료입니다.'
    synth = checks.get('asic-synth', {})
    gate = checks.get('asic-gate', {})
    facts = (f'대상: {result["target"]} · 상태: {MARK.get(result["status"], result["status"])} · '
             f'전체 시간: {result.get("wall_seconds", "-")}초\n\n'
             f'합성: {synth.get("cells", "-")}셀 / {synth.get("flops", "-")}FF / {synth.get("area_um2", "-")} µm²\n\n'
             f'배선 후 기능 회귀: {gate.get("jobs", "-")}작업 / {gate.get("status", "not_run")}')
    if result.get('mode'):
        allowed = ', '.join(result.get('allowed_unsupported', [])) or '없음'
        facts += f'\n\n종료 코드 판정: {result["mode"]} · 미확인(unsupported)으로 남아도 되는 검사: {allowed}'
    text = f'# {title}\n\n**{notice}**\n\n{facts}\n\n'
    text += '| 검사 | 상태 | 시간(초) | 설명 |\n| --- | --- | --- | --- |\n'+'\n'.join(rows)+'\n'
    text += '\n커밋: `'+result['commit']+'` · 미커밋 변경: '+str(result.get('dirty_checkout', False))+'\n'
    text += '\n도구: '+', '.join(f'{k}: {v}' for k, v in result.get('tools', {}).items())+'\n'
    if result.get('error'):
        text += '\n실행 오류: '+result['error']+'\n'
    (out/'summary.md').write_text(text, encoding='utf-8')
    images = []
    for name in [result['top']+'.png', 'ternary8_sop28.png']:
        if (out/name).is_file():
            images.append(f'<figure><img src="{name}" alt="{escape(name)}"><figcaption>{escape(name)}</figcaption></figure>')
    links = []
    for path in sorted(out.iterdir()):
        if path.is_file() and path.suffix in ['.gds', '.json', '.log', '.spice']:
            links.append(f'<li><a href="{escape(path.name, quote=True)}">{escape(path.name)}</a></li>')
    html = ('<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+title+'</title>'
            '<style>body{font:15px system-ui,sans-serif;max-width:1200px;margin:32px auto;padding:0 20px;color:#17202a}'
            'table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid #ccd2d9;padding:8px;text-align:left}'
            '.notice{background:#fff2c9;padding:16px}img{max-width:100%;height:auto}figure{margin:24px 0}pre{white-space:pre-wrap}</style>'
            f'<h1>{title}</h1><p class="notice">{notice}</p><pre>{escape(facts)}</pre>'
            '<table><thead><tr><th>검사</th><th>상태</th><th>초</th><th>설명</th><th>근거</th></tr></thead><tbody>'
            +''.join(html_rows)+'</tbody></table>'+''.join(images)+'<h2>파일</h2><ul>'+''.join(links)+'</ul>'
            +('<h2>실행 오류</h2><pre>'+escape(result['error'])+'</pre>' if result.get('error') else '')
            +'</html>')
    (out/'report.html').write_text(html, encoding='utf-8')
