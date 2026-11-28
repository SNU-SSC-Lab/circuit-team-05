"""Verify all checks in the pinned NSPL deck; never infer process approval."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
try:
    from .drc_ports import PORTS
    from .drc_antenna import ANT_SOURCE, ANT_SOURCE_SHA, RULES as ANTENNA
except ImportError:
    from drc_ports import PORTS
    from drc_antenna import ANT_SOURCE, ANT_SOURCE_SHA, RULES as ANTENNA

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT/'verification/asic/drc-rules.json'
CALIBRE = 'Calibre/DRC/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal'
ASSURA = 'Assura/DRC/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.rul'
SOURCE_SHA = '6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f'
ASSURA_SHA = '09ce215f4034ad9aa9709157fe3d61a2ba508b0407a89da6cfc7faa6f6581109'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def strip_comments(text, line_comment='//'):
    """Keep positions/newlines while masking comments and quoted braces."""
    result = list(text)
    i = 0
    while i < len(text):
        if text.startswith(line_comment, i) or text[i] == '@':
            end = text.find('\n', i)
            end = len(text) if end < 0 else end
        elif text.startswith('/*', i):
            end = text.find('*/', i+2)
            if end < 0:
                raise ValueError('unterminated block comment')
            end += 2
        elif text[i] == '"':
            # Preserve strings so reference labels remain available. Only
            # braces in strings are masked for the SVRF brace scanner.
            i += 1
            while i < len(text):
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == '"':
                    break
                if text[i] in '{}':
                    result[i] = ' '
                i += 1
            if i >= len(text):
                raise ValueError('unterminated quoted text')
            i += 1
            continue
        else:
            i += 1
            continue
        for j in range(i, end):
            if text[j] != '\n':
                result[j] = ' '
        i = end
    return ''.join(result)

def parse_checks(text, indented=False):
    """Checks `NAME { ... }` of an SVRF deck. indented: a header may follow spaces (the ANT deck indents
    ANT_02_3 and ANT_03_3); the DRC deck is parsed without, as its catalog was made."""
    clean = strip_comments(text)
    header = re.compile(r'(?m)^[ \t]*([A-Za-z0-9_][A-Za-z0-9_.]*)\s*\{' if indented else
                        r'(?m)^([A-Za-z0-9_][A-Za-z0-9_.]*)\s*\{')
    result = {}
    previous_end = 0
    for match in header.finditer(clean):
        if match.start() < previous_end:
            continue
        name = match[1]
        end, depth = match.end(), 1
        while end < len(clean) and depth:
            depth += (clean[end] == '{') - (clean[end] == '}')
            end += 1
        if depth:
            raise ValueError('unterminated check: '+name)
        if name in result:
            raise ValueError('duplicate check: '+name)
        raw = text[match.start():end]
        result[name] = {'source_line': text.count('\n', 0, match.start())+1,
                        'body_sha256': sha(raw.encode()),
                        'description': ' '.join(x.strip() for x in re.findall(r'@\s*([^\n]+)', raw)),
                        'body': clean[match.end():end-1].strip()}
        previous_end = end
    return result

def disabled_checks(text):
    # Only contiguous // lines headed by a check name are considered.
    lines = text.splitlines(keepends=True)
    result = {}
    for i, line in enumerate(lines):
        match = re.match(r'^\s*//\s*([A-Za-z0-9_][A-Za-z0-9_.]*)\s*\{', line)
        if not match:
            continue
        chunk = []
        for current in lines[i:]:
            if not re.match(r'^\s*//', current):
                break
            chunk.append(re.sub(r'^\s*//\s?', '', current))
            if '}' in current:
                break
        parsed = parse_checks(''.join(chunk))
        if match[1] not in parsed:
            raise ValueError('cannot parse disabled check: '+match[1])
        item = parsed[match[1]]
        item['source_line'] = i+1
        result[match[1]] = item
    return result

def assura_labels(text):
    clean = strip_comments(text, ';')
    labels = set(re.findall(r'"([0-9]+\.[A-Za-z0-9_.]+):', clean))
    labels |= {'OFFGRID_'+name.strip() for _, _, name in re.findall(
        r'offGrid\((\w+)\s+([\d.]+)\s+"off grid on layer ([^"]+)"\)', clean)}
    return labels

def compare_rules(actual, disabled, catalog, ports=None):
    expected = {r['id']: r for r in catalog['rules']}
    if len(expected) != len(catalog['rules']) or set(expected) != set(actual):
        raise ValueError('active DRC catalog missing, extra or duplicate checks')
    if set(catalog['disabled_rules']) != set(disabled):
        raise ValueError('disabled DRC catalog differs from source')
    for name, value in actual.items():
        for key in ['body_sha256', 'source_line']:
            if expected[name][key] != value[key]:
                raise ValueError('catalog/source mismatch: '+name+' '+key)
    for name, value in disabled.items():
        if catalog['disabled_rules'][name]['body_sha256'] != value['body_sha256']:
            raise ValueError('disabled check changed: '+name)
    ported = {name for name, rule in expected.items() if rule['implementation'] == 'geometry_port'}
    if ported != set(PORTS if ports is None else ports):
        raise ValueError('catalog executable-check set differs from geometry implementation')
    return catalog

def compare_antenna(actual, catalog, implemented=None):
    """ANT deck RULECHECKs against drc-rules.json `antenna_rules` and drc_antenna.RULES (same checks, lines)."""
    rules = catalog.get('antenna_rules', [])
    expected = {r['id']: r for r in rules}
    if len(expected) != len(rules) or set(expected) != set(actual):
        raise ValueError('antenna catalog missing, extra or duplicate checks')
    for name, value in actual.items():
        for key in ['body_sha256', 'source_line']:
            if expected[name][key] != value[key]:
                raise ValueError('antenna catalog/source mismatch: '+name+' '+key)
    implemented = ANTENNA if implemented is None else implemented
    ported = {name for name, rule in expected.items() if rule['implementation'] == 'antenna_port'}
    if ported != set(implemented):
        raise ValueError('catalog antenna-check set differs from drc_antenna.py')
    for name in ported:
        if implemented[name]['line'] != expected[name]['source_line']:
            raise ValueError('drc_antenna.py cites another deck line for '+name)
    return catalog

def validate(pdk, catalog=None):
    catalog = catalog or json.loads(CATALOG.read_text(encoding='utf-8'))
    source = (Path(pdk)/CALIBRE).read_bytes()
    assura = (Path(pdk)/ASSURA).read_bytes()
    if sha(source) != catalog['sources']['calibre']['sha256'] or sha(source) != SOURCE_SHA:
        raise ValueError('unreviewed Calibre DRC source')
    if sha(assura) != catalog['sources']['assura']['sha256'] or sha(assura) != ASSURA_SHA:
        raise ValueError('unreviewed Assura DRC source')
    compare_rules(parse_checks(source.decode()), disabled_checks(source.decode()), catalog)
    antenna = (Path(pdk)/ANT_SOURCE).read_bytes()
    if sha(antenna) != catalog['sources']['calibre_ant']['sha256'] or sha(antenna) != ANT_SOURCE_SHA:
        raise ValueError('unreviewed Calibre ANT source')
    compare_antenna(parse_checks(antenna.decode(), indented=True), catalog)
    labels = assura_labels(assura.decode())
    for rule in catalog['rules']:
        if rule['assura_label'] != (rule['id'] in labels):
            raise ValueError('Assura label correspondence changed: '+rule['id'])
    if set(catalog['assura_unmatched_ids']) != labels-{r['id'] for r in catalog['rules']}:
        raise ValueError('Assura-only label inventory changed')
    return catalog

def markdown(catalog):
    counts = Counter(r['implementation'] for r in catalog['rules'])
    lines = ['# 공개 NSPL DRC 규칙 대조표', '',
             '원본 전체를 목록화한 결과다. 구현·시험 수는 공정 정확도나 제출 승인 비율이 아니다.', '',
             f'활성 {len(catalog["rules"])}개 / 원본 비활성 {len(catalog["disabled_rules"])}개 / 상태 {dict(counts)}', '',
             '| 원본 규칙 | 줄 | 이전 routing 검사 | 확장 검사 | Assura 동일 ID | 공개 변환본 동일 ID | 부족한 조건·다음 작업 |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for rule in catalog['rules']:
        # Same states as reliability.rule_state (SPEC 0019): unported -> ported -> verified.
        state = ('미구현' if rule['implementation'] != 'geometry_port' else
                 '기하 검사·Calibre 일치(verified)' if rule.get('golden_compared') else '기하 검사·Calibre 대조 전(ported)')
        lines.append(f'| {rule["id"]} | {rule["source_line"]} | {rule["legacy_coverage"]} | {state} | '
                     f'{rule["assura_label"]} | {rule["converted_label"]} | {rule["remaining"]} |')
    lines += ['', '## 키트 ANT deck', '', f'`{ANT_SOURCE}` RULECHECK {len(catalog.get("antenna_rules", []))}개. '
              'KLayout 구현은 `scripts/asic/drc_antenna.py`(deck 문장 그대로 넷마다 비율 계산).', '',
              '| 원본 검사 | 줄 | 구현 | 설명 |', '| --- | --- | --- | --- |']
    for rule in catalog.get('antenna_rules', []):
        state = ('미구현' if rule['implementation'] != 'antenna_port' else
                 'antenna 검사·Calibre 일치(verified)' if rule.get('golden_compared') else 'antenna 검사·Calibre 대조 전(ported)')
        lines.append(f'| {rule["id"]} | {rule["source_line"]} | {state} | {rule["remaining"]} |')
    lines += ['', '원본 비활성: '+', '.join(catalog['disabled_rules']), '',
              'Assura에서만 같은 이름이 잡힌 항목: '+', '.join(catalog['assura_unmatched_ids']), '',
              '공개 변환본에서 다른 이름을 쓴 항목: '+', '.join(catalog['converted_unmatched_ids']), '',
              '아직 옮기지 않은 전역 입력 플래그: '+', '.join(catalog['global_flags_unported']), '',
              '동일 ID는 이름 대조이며 같은 식·조건의 증거가 아니다. 변환본에서 ID를 나누거나 바꾼 경우도 있다. '
              'Calibre 결과와의 대조는 verification/reliability/(신뢰성 대응표)에 있다: verified DRC 규칙은 fixture와 '
              '실제 형상 변형본에서, verified ANT 검사는 fixture에서 KLayout 판정이 Calibre golden과 같다. Assura 결과와의 대조는 하지 않았다. '
              'verified도 공정 전체 DRC 통과나 제출 승인이 아니다.', '']
    return '\n'.join(lines)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    catalog = validate(args.pdk)
    (args.out/'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (args.out/'rules.md').write_text(markdown(catalog), encoding='utf-8')
    print(f'{len(catalog["rules"])} active checks and {len(catalog["antenna_rules"])} ANT RULECHECKs exactly matched '
          'the pinned sources.')

if __name__ == '__main__':
    main()
