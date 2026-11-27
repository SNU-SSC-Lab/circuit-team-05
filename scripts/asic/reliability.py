"""Reliability table helpers shared by KLayout's Python and normal Python (stdlib only)."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
RULES_JSON = ROOT/'verification/asic/drc-rules.json'
META_KEYS = ('calibre_version', 'deck_sha256', 'fixture_tarball_sha256', 'generator_commit', 'run_date')
# Fields drc_fixture_test.py copies from a case into its selftest record.
CASE_FIELDS = ('rule', 'label', 'fail', 'hierarchy', 'dbu', 'raises')
VERDICT_KO = {'match': '일치', 'mismatch': '불일치', 'no_golden': '근거 없음', 'excluded': '제외'}
TABLE_KO = {'match': '일치', 'mismatch': '불일치', 'no_evidence': '근거 없음(미검증)'}


def rule_state(rule):
    """DRC rule state in drc-rules.json: unported -> ported -> verified (SPEC 0019 3절)."""
    if rule['implementation'] == 'unported':
        return 'unported'
    return 'verified' if rule.get('golden_compared') else 'ported'


def verified_rules(catalog):
    return sorted(rule['id'] for rule in catalog['rules'] if rule_state(rule) == 'verified')


def case_sha256(case):
    """Hash a fixture definition; GDS bytes carry timestamps, so golden uses this instead."""
    # json.dumps writes tuples as lists, so tuple and list shapes hash the same.
    text = json.dumps(case, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def fixture_name(index, case):
    """GDS stem that drc_fixture_test.py writes for cases()[index]."""
    return re.sub(r'[^A-Za-z0-9_.-]', '_', f'{index:04}-{case["rule"]}-{case["label"]}')


def _cases_by_gds():
    from drc_cases import cases
    by_gds = {}
    for index, case in enumerate(cases()):
        name = fixture_name(index, case)+'.gds'
        if name in by_gds:
            raise ValueError('two fixtures share the file name '+name)
        by_gds[name] = case
    return by_gds


def _other_rules(text):
    result = {}
    for item in filter(None, text.split(';')):
        name, count = item.rsplit(':', 1)
        result[name] = int(count)
    return result


def _refused_reason(log):
    if not log.is_file():
        raise ValueError(f'{log.name}: Calibre refused this fixture but its log is missing')
    for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
        if line.startswith('ERROR:'):
            return line[len('ERROR:'):].strip()
    raise ValueError(f'{log.name}: Calibre refused this fixture but the log has no ERROR line')


def import_calibre(counts_csv, selftest, meta, logs=None):
    """Build the golden document from one Calibre batch (one run per fixture GDS)."""
    counts_csv, selftest = Path(counts_csv), Path(selftest)
    missing = [key for key in META_KEYS if not meta.get(key)]
    if missing:
        raise ValueError('golden meta is missing '+', '.join(missing))
    import drc_catalog
    if meta['deck_sha256'] != drc_catalog.SOURCE_SHA:
        raise ValueError('deck_sha256 is not the deck drc_catalog.SOURCE_SHA names')
    logs = Path(logs) if logs else counts_csv.parent/'results'
    records = {}
    for record in json.loads(selftest.read_text(encoding='utf-8'))['records']:
        if record['gds'] in records:
            raise ValueError('selftest.json lists twice: '+record['gds'])
        records[record['gds']] = record
    # selftest.json from before case_sha256 existed: hash the same definitions by fixture name.
    by_gds = _cases_by_gds() if any('case_sha256' not in r for r in records.values()) else None
    with counts_csv.open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    fixtures, seen = [], set()
    for row in rows:
        gds = row['gds']
        if gds in seen:
            raise ValueError('Calibre counts list twice: '+gds)
        seen.add(gds)
        record = records.get(gds)
        if record is None:
            raise ValueError(gds+': Calibre ran a fixture that selftest.json does not have')
        if record['rule'] != row['target_rule']:
            raise ValueError(f'{gds}: target rule {row["target_rule"]} but selftest says {record["rule"]}')
        if 'case_sha256' in record:
            digest = record['case_sha256']
        else:
            case = by_gds.get(gds)
            if case is None:
                raise ValueError(gds+': no drc_cases fixture has this file name')
            if any(case[key] != record.get(key) for key in CASE_FIELDS):
                raise ValueError(gds+': selftest record does not match the drc_cases fixture of that name')
            digest = case_sha256(case)
        entry = {'gds': gds, 'rule': row['target_rule'], 'case_sha256': digest}
        if int(row['calibre_exit']) != 0:
            entry.update(calibre='refused', target_count=None, other_rules={},
                         refused_reason=_refused_reason(logs/(Path(gds).stem+'.calibre.log')))
        else:
            count = int(row['target_rule_count'])
            # other_rules keeps 1.PWL.bad1 too: a bare test cell has no PWELL tap.
            entry.update(calibre='fired' if count > 0 else 'clean', target_count=count,
                         other_rules=_other_rules(row['other_rules_fired']), refused_reason=None)
        fixtures.append(entry)
    if seen != set(records):
        raise ValueError('fixtures without a Calibre result: '+', '.join(sorted(set(records)-seen)))
    meta = dict(meta, case_sha256_from='drc_cases' if by_gds else 'selftest')
    return {'meta': meta, 'fixtures': fixtures}


def compare(golden, selftest):
    """Compare only whether the target rule fired; counts and other rules are report-only."""
    index = {}
    for entry in golden['fixtures']:
        old = index.setdefault(entry['case_sha256'], entry)
        if old['calibre'] != entry['calibre']:
            raise ValueError('golden files disagree on fixture '+entry['case_sha256'])
    fixtures, by_rule = [], {}
    for record in selftest['records']:
        entry = index.get(record.get('case_sha256'))
        item = {'gds': record['gds'], 'rule': record['rule'], 'klayout_errors': record.get('errors')}
        if entry is None or entry['rule'] != record['rule']:
            item['verdict'] = 'no_golden'
        else:
            item.update(calibre=entry['calibre'], calibre_target_count=entry.get('target_count'))
            if entry['calibre'] == 'refused':
                item.update(verdict='excluded', reason=entry.get('refused_reason'))
            elif 'errors' not in record:  # KLayout rejected an input that Calibre judged
                item['verdict'] = 'mismatch'
            else:
                item['verdict'] = 'match' if (record['errors'] > 0) == (entry['calibre'] == 'fired') else 'mismatch'
        fixtures.append(item)
        by_rule.setdefault(record['rule'], []).append(item['verdict'])
    rules = {}
    for rule, verdicts in by_rule.items():
        if 'mismatch' in verdicts:
            rules[rule] = 'mismatch'
        elif 'match' in verdicts and all(v in ('match', 'excluded') for v in verdicts):
            rules[rule] = 'match'  # excluded fixtures alone are not evidence
        else:
            rules[rule] = 'no_golden'
    return {'fixtures': fixtures, 'rules': rules}


def load_golden(directory):
    """Merge every fixture golden.json at or below directory (mutation golden files are check-mutations')."""
    directory = Path(directory)
    paths = sorted(directory.glob('**/golden.json'))
    sources, fixtures = [], []
    for path in paths:
        doc = json.loads(path.read_text(encoding='utf-8'))
        if 'mutations' in doc and 'fixtures' not in doc:
            continue
        sources.append(dict(doc['meta'], path=path.relative_to(directory).as_posix()))
        fixtures += doc['fixtures']
    if not sources:
        raise ValueError(f'no fixture golden.json under {directory}')
    return {'sources': sources, 'fixtures': fixtures}


def summary_markdown(result):
    gate = result['gate']
    lines = ['# DRC fixture 신뢰성 대조 (KLayout ↔ Calibre golden)', '',
             f'- 판정: **{"통과" if gate["status"] == "pass" else "실패"}** '
             f'(게이트 대상 `verified` 규칙 {len(gate["rules"])}개, 일치하지 않는 규칙 {len(gate["failing"])}개)',
             '- 기준: fixture마다 대상 규칙이 위반을 냈는지(있음/없음)만 비교한다. 마커 수와 대상 밖 규칙 발동은 기록만 한다.',
             '- 게이트는 `verification/asic/drc-rules.json`에서 `verified`인 규칙만 본다. '
             '그 밖의 규칙 판정은 아래 표에 기록만 한다.']
    for source in result['golden']:
        lines.append(f'- golden `{source["path"]}`: Calibre {source.get("calibre_version")}, '
                     f'deck sha256 `{source.get("deck_sha256")}`, 실행일 {source.get("run_date")}')
    lines += ['', '| 구분 | 규칙 수 | fixture 수 |', '| --- | --- | --- |']
    for verdict in ('match', 'mismatch', 'no_golden', 'excluded'):
        rules = sum(v == verdict for v in result['rules'].values()) if verdict != 'excluded' else '-'
        count = sum(f['verdict'] == verdict for f in result['fixtures'])
        lines.append(f'| {VERDICT_KO[verdict]} (`{verdict}`) | {rules} | {count} |')
    if gate['failing']:
        lines += ['', '## 일치하지 않는 규칙', '']
        for rule in gate['failing']:
            verdicts = [f['verdict'] for f in result['fixtures'] if f['rule'] == rule]
            why = (' (fixture 없음)' if not verdicts else
                   ' (Calibre가 거부한 제외 fixture만 있음)' if set(verdicts) == {'excluded'} else '')
            lines.append(f'- `{rule}`: {VERDICT_KO[result["rules"].get(rule, "no_golden")]}{why}')
    problems = [f for f in result['fixtures'] if f['verdict'] in ('mismatch', 'no_golden')]
    if problems:
        lines += ['', '## 불일치·근거 없음 fixture', '']
        lines += [f'- `{f["gds"]}` (`{f["rule"]}`): {VERDICT_KO[f["verdict"]]}, KLayout {f["klayout_errors"]}, '
                  f'Calibre {f.get("calibre", "golden 없음")}' for f in problems]
    excluded = [f for f in result['fixtures'] if f['verdict'] == 'excluded']
    if excluded:
        lines += ['', '## 제외된 fixture (Calibre가 입력을 거부)', '']
        lines += [f'- `{f["gds"]}` (`{f["rule"]}`): {f.get("reason")}' for f in excluded]
    counts = [f for f in result['fixtures'] if f['verdict'] == 'match' and f.get('calibre') == 'fired'
              and f['klayout_errors'] != f.get('calibre_target_count')]
    if counts:
        lines += ['', '## 마커 수 차이 (기록만, 판정에 쓰지 않음)', '']
        lines += [f'- `{f["gds"]}`: KLayout {f["klayout_errors"]}, Calibre {f["calibre_target_count"]}' for f in counts]
    return '\n'.join(lines)+'\n'


def check(selftest, golden_dir, out, rules_json=RULES_JSON):
    """Write result.json and summary.md; return 1 when a verified rule is not match."""
    golden = load_golden(golden_dir)
    result = compare(golden, json.loads(Path(selftest).read_text(encoding='utf-8')))
    # Only verified rules gate; a verified rule with no usable fixture reads as no_golden and fails.
    targets = verified_rules(json.loads(Path(rules_json).read_text(encoding='utf-8')))
    failing = [rule for rule in targets if result['rules'].get(rule, 'no_golden') != 'match']
    result['golden'] = golden['sources']
    result['gate'] = {'status': 'fail' if failing else 'pass', 'rules': targets, 'failing': failing}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    # LF on every platform so the same result gives the same bytes.
    (out/'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
    (out/'summary.md').write_text(summary_markdown(result), encoding='utf-8', newline='\n')
    return 1 if failing else 0


MUTATION_META_KEYS = ('calibre_version', 'deck_sha256', 'corpus_tarball_sha256', 'run_date')
MANIFEST_KEYS = ('gds', 'source', 'cell', 'variant', 'op', 'delta_um', 'layer', 'near_um')
EMPTY_REASON = 'empty top cell: the mutation removed every shape, and KLayout DRC refuses an empty top'
MUTATION_KO = {'match': '일치', 'mismatch': '불일치', 'excluded': '제외', 'geometry_changed': '형상 다름',
               'missing': 'GDS 없음', 'klayout_error': 'KLayout 결과 없음'}


def import_mutations(counts_csv, manifest, geometry, meta):
    """Mutation golden: one record per corpus GDS with its geometry hash and every rule Calibre fired.

    counts_csv: gds, rules_fired (rule:count;...), calibre_exit, run_ms, calibre_error (one Calibre run per GDS).
    manifest: the corpus manifest.json. geometry: `mutate.py hash` output for the exact GDS Calibre read."""
    missing = [key for key in MUTATION_META_KEYS if not meta.get(key)]
    if missing:
        raise ValueError('mutation golden meta is missing '+', '.join(missing))
    import drc_catalog
    if meta['deck_sha256'] != drc_catalog.SOURCE_SHA:
        raise ValueError('deck_sha256 is not the deck drc_catalog.SOURCE_SHA names')
    manifest = json.loads(Path(manifest).read_text(encoding='utf-8'))
    geometry = json.loads(Path(geometry).read_text(encoding='utf-8'))
    with Path(counts_csv).open(encoding='utf-8', newline='') as stream:
        rows = {}
        for row in csv.DictReader(stream):
            if row['gds'] in rows:
                raise ValueError('Calibre counts list twice: '+row['gds'])
            rows[row['gds']] = row
    names = [record['gds'] for record in manifest['records']]
    if len(set(names)) != len(names):
        raise ValueError('manifest lists a GDS twice')
    for label, found in (('Calibre counts', rows), ('geometry hashes', geometry)):
        if set(found) != set(names):
            extra, lost = sorted(set(found)-set(names)), sorted(set(names)-set(found))
            raise ValueError(f'{label} and manifest differ: not in manifest {extra[:5]}, missing {lost[:5]}')
    mutations = []
    for record in manifest['records']:
        row, shape = rows[record['gds']], geometry[record['gds']]
        entry = {key: record[key] for key in MANIFEST_KEYS if key in record}
        entry.update(geometry_sha256=shape['geometry_sha256'], polygons=shape['polygons'])
        if int(row['calibre_exit']) != 0:
            reason = row['calibre_error'].strip()
            if not reason:
                raise ValueError(record['gds']+': Calibre refused this GDS but gave no error')
            entry.update(calibre='refused', rules_fired={}, refused_reason=reason)
        else:
            entry.update(calibre='ok', rules_fired=_other_rules(row['rules_fired']), refused_reason=None)
        mutations.append(entry)
    meta = dict(meta, seed=manifest['seed'], per_cell=manifest['per_cell'],
                sources=list(dict.fromkeys(record['source'] for record in manifest['records'])),
                generator='scripts/asic/mutate.py', geometry_hash='mutate.geometry_sha256')
    return {'meta': meta, 'mutations': mutations}


def mutation_targets(golden, geometry):
    """GDS that KLayout must judge: Calibre accepted it, the geometry is the golden's and not empty."""
    return [m['gds'] for m in golden['mutations'] if m['calibre'] == 'ok' and m['gds'] in geometry
            and geometry[m['gds']]['geometry_sha256'] == m['geometry_sha256'] and geometry[m['gds']]['polygons']]


def compare_mutations(golden, geometry, klayout, verified):
    """Per GDS and verified rule: did KLayout fire (errors > 0) exactly when Calibre fired?

    geometry: {gds: {geometry_sha256, polygons}} of the corpus checked; klayout: {gds: drc.py `rules`}."""
    counts = dict(both=0, none=0, klayout_only=0, calibre_only=0)
    items, disagreements = [], []
    for record in golden['mutations']:
        gds, shape = record['gds'], geometry.get(record['gds'])
        item = {'gds': gds, 'cell': record['cell'], 'op': record['op']}
        if record['calibre'] == 'refused':
            item.update(verdict='excluded', reason=record['refused_reason'])
        elif shape is None:
            item['verdict'] = 'missing'
        elif shape['geometry_sha256'] != record['geometry_sha256']:
            item.update(verdict='geometry_changed', geometry_sha256=shape['geometry_sha256'])
        elif not shape['polygons']:
            item.update(verdict='excluded', reason=EMPTY_REASON)
        elif klayout.get(gds) is None or any(rule not in klayout[gds] for rule in verified):
            item['verdict'] = 'klayout_error'
        else:
            item['verdict'] = 'match'
            for rule in verified:
                ours, theirs = klayout[gds][rule]['errors'], record['rules_fired'].get(rule, 0)
                key = ('both' if theirs else 'klayout_only') if ours else ('calibre_only' if theirs else 'none')
                counts[key] += 1
                if key in ('klayout_only', 'calibre_only'):
                    item['verdict'] = 'mismatch'
                    disagreements.append({'gds': gds, 'rule': rule, 'klayout': ours, 'calibre': theirs})
        items.append(item)
    compared = sum(item['verdict'] in ('match', 'mismatch') for item in items)
    failing = [item for item in items if item['verdict'] not in ('match', 'excluded')]
    status = 'fail' if failing or not verified or not compared else 'pass'
    return {'status': status, 'rules': list(verified), 'compared_gds': compared, 'counts': counts,
            'disagreements': disagreements, 'mutations': items}


def mutation_summary(result, meta):
    lines = ['# DRC 변형본 신뢰성 대조 (KLayout ↔ Calibre golden)', '',
             f'- 판정: **{"통과" if result["status"] == "pass" else "실패"}** '
             f'(`verified` 규칙 {len(result["rules"])}개 × 비교한 GDS {result["compared_gds"]}개)',
             '- 기준: 변형본 GDS마다 `verified` 규칙이 위반을 냈는지(있음/없음)만 Calibre와 비교한다. '
             '마커 수는 기록만 한다.',
             f'- golden: Calibre {meta.get("calibre_version")}, deck sha256 `{meta.get("deck_sha256")}`, '
             f'실행일 {meta.get("run_date")}, 변형본 seed {meta.get("seed")}, 셀당 {meta.get("per_cell")}개',
             '', '| 구분 | 판정 수 |', '| --- | --- |']
    names = dict(both='둘 다 위반', none='둘 다 위반 없음', klayout_only='KLayout만 위반', calibre_only='Calibre만 위반')
    lines += [f'| {names[key]} (`{key}`) | {count} |' for key, count in result['counts'].items()]
    lines += ['', '| GDS 판정 | 수 |', '| --- | --- |']
    for verdict, label in MUTATION_KO.items():
        lines.append(f'| {label} (`{verdict}`) | {sum(m["verdict"] == verdict for m in result["mutations"])} |')
    if not result['rules']:
        lines += ['', '`verified` 규칙이 없어 아무것도 확인하지 않았다. 게이트는 실패로 본다.']
    if result['disagreements']:
        lines += ['', '## 불일치', '', '| GDS | 규칙 | KLayout | Calibre |', '| --- | --- | --- | --- |']
        lines += [f'| `{d["gds"]}` | `{d["rule"]}` | {d["klayout"]} | {d["calibre"]} |' for d in result['disagreements']]
    broken = [m for m in result['mutations'] if m['verdict'] in ('geometry_changed', 'missing', 'klayout_error')]
    if broken:
        lines += ['', '## 비교하지 못한 GDS (실패)', '',
                  '형상 해시가 golden과 다르거나, GDS가 없거나, KLayout 결과가 없으면 근거와 같은 입력을 '
                  '검사했다고 볼 수 없어 실패로 센다.', '']
        lines += [f'- `{m["gds"]}`: {MUTATION_KO[m["verdict"]]}' for m in broken]
    excluded = [m for m in result['mutations'] if m['verdict'] == 'excluded']
    if excluded:
        lines += ['', '## 제외된 GDS', '']
        lines += [f'- `{m["gds"]}`: {m["reason"]}' for m in excluded]
    return '\n'.join(lines)+'\n'


def _mutation_geometry(gds_dir, out, klayout):
    import mutate
    return mutate.hash_folder(gds_dir, out, klayout)


def _drc_one(gds, gds_dir, out, klayout):
    stem = Path(gds).stem
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1', SSC_DRC_PROFILE='expanded',
               SSC_GDS=str(Path(gds_dir).resolve()/gds), SSC_TOP='mut', SSC_DRC_OUT=str(out/(stem+'.json')))
    with (out/(stem+'.log')).open('w', encoding='utf-8') as log:
        # drc.py exits non-zero whenever a rule fires; the JSON it writes is the result.
        subprocess.run([klayout, '-b', '-r', str(ROOT/'scripts/asic/drc.py')], env=env, stdout=log,
                       stderr=subprocess.STDOUT, timeout=600)
    path = out/(stem+'.json')
    return json.loads(path.read_text(encoding='utf-8'))['rules'] if path.is_file() else None


def _run_drc(gds_dir, targets, out, jobs, klayout):
    """{gds: drc.py rules or None}; one KLayout process per GDS, as Calibre ran one per GDS."""
    from concurrent.futures import ThreadPoolExecutor
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = pool.map(lambda gds: _drc_one(gds, gds_dir, out, klayout), targets)
        return dict(zip(targets, results))


def check_mutations(golden_path, out, kit=None, gds_dir=None, rules_json=RULES_JSON, jobs=None, klayout='klayout'):
    """Rebuild (or take) the mutation corpus, run KLayout DRC on it and compare with golden; 1 on any failure."""
    golden = json.loads(Path(golden_path).read_text(encoding='utf-8'))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if gds_dir is None:
        import mutate
        gds_dir = out/'gds'
        mutate.generate(kit, gds_dir, golden['meta']['seed'], golden['meta']['per_cell'], klayout)
    started = time.monotonic()
    geometry = _mutation_geometry(gds_dir, out/'geometry.json', klayout)
    targets = mutation_targets(golden, geometry)
    klayout_rules = _run_drc(gds_dir, targets, out/'klayout', jobs or os.cpu_count() or 1, klayout)
    verified = verified_rules(json.loads(Path(rules_json).read_text(encoding='utf-8')))
    result = compare_mutations(golden, geometry, klayout_rules, verified)
    result['wall_seconds'] = round(time.monotonic()-started, 1)
    (out/'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')
    (out/'summary.md').write_text(mutation_summary(result, golden['meta']), encoding='utf-8', newline='\n')
    return 0 if result['status'] == 'pass' else 1


def _cell(text):
    return str(text).replace('|', '\\|').replace('\n', ' ')


def render(table):
    """table.md body; table.json is the source and CI compares the two."""
    lines = ['# 신뢰성 대응표', '',
             '오픈소스 도구 판정과 상용 도구 판정을 단계별로 맞춰 본 근거다(SPEC 0019 2절). '
             '이 파일은 `table.json`에서 만든다. 손으로 고치지 말고 `table.json`을 고친 뒤 '
             '`python scripts/asic/reliability.py render --table verification/reliability/table.json '
             '--out verification/reliability/table.md`를 실행한다.', '',
             '- 판정: 일치(`match`) · 불일치(`mismatch`) · 근거 없음(`no_evidence`, 미검증 목록에 있음).',
             '- 근거 경로는 `verification/reliability/` 기준이다. 근거 없음 칸은 `unverified.json`의 항목 id를 적는다.',
             '- 수치 차이(마커 수·타이밍 등)는 기록만 하고 판정 조건으로 쓰지 않는다.', '',
             '| 단계 | 오픈소스 (PR마다) | 상용 기준 (기준점) | 판정 | 범위 | 현재 근거 | CI가 PR마다 확인하는 것 | 근거 파일·미검증 항목 | 갱신일 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for row in table['rows']:
        refs = [f'`{path}`' for path in row['evidence']] + [f'미검증 `{item}`' for item in row['unverified']]
        cells = [row['stage'], row['open_source'], row['commercial'], f'**{TABLE_KO[row["verdict"]]}**',
                 row['scope'], row['note'], row['pr_check'], '<br>'.join(refs), row['updated']]
        lines.append('| '+' | '.join(_cell(c) for c in cells)+' |')
    return '\n'.join(lines)+'\n'


def _case_commit(generator_commit):
    """Commit whose drc_cases.py hashed the fixtures; it must equal the generator's."""
    git = ['git', '-C', str(ROOT)]
    if subprocess.run(git+['diff', '--quiet', generator_commit, '--', 'scripts/asic/drc_cases.py']).returncode:
        raise ValueError(f'scripts/asic/drc_cases.py differs from {generator_commit}; hashes would not match the batch')
    return subprocess.run(git+['rev-parse', '--short', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    checker = commands.add_parser('check', help='compare a KLayout selftest.json with golden')
    checker.add_argument('--selftest', type=Path, required=True)
    checker.add_argument('--golden', type=Path, required=True)
    checker.add_argument('--out', type=Path, required=True)
    checker.add_argument('--rules', type=Path, default=RULES_JSON, help='drc-rules.json that names verified rules')
    renderer = commands.add_parser('render', help='write table.md from table.json')
    renderer.add_argument('--table', type=Path, required=True)
    renderer.add_argument('--out', type=Path, required=True)
    importer = commands.add_parser('import', help='write golden.json from one Calibre batch')
    importer.add_argument('--counts', type=Path, required=True)
    importer.add_argument('--selftest', type=Path, required=True)
    importer.add_argument('--logs', type=Path, help='refusal logs (default: results/ beside --counts)')
    importer.add_argument('--out', type=Path, required=True)
    for key in META_KEYS:
        importer.add_argument('--'+key.replace('_', '-'), required=True)
    mutations = commands.add_parser('check-mutations', help='KLayout DRC on the mutation corpus against its golden')
    mutations.add_argument('--golden', type=Path, required=True, help='drc-mutations-*/golden.json')
    corpus = mutations.add_mutually_exclusive_group(required=True)
    corpus.add_argument('--kit', type=Path, help='unpacked NSPL_05CMOS_PDK_260820 folder; rebuild the corpus')
    corpus.add_argument('--gds-dir', type=Path, help='an existing corpus folder')
    mutations.add_argument('--out', type=Path, required=True)
    mutations.add_argument('--rules', type=Path, default=RULES_JSON, help='drc-rules.json that names verified rules')
    mutations.add_argument('--jobs', type=int, help='parallel KLayout runs (default: CPU count)')
    mutations.add_argument('--klayout', default='klayout')
    mutation_importer = commands.add_parser('import-mutations', help='write the mutation golden.json from one Calibre batch')
    mutation_importer.add_argument('--counts', type=Path, required=True, help='gds,rules_fired,calibre_exit,run_ms,calibre_error')
    mutation_importer.add_argument('--manifest', type=Path, required=True, help='manifest.json of the corpus Calibre ran')
    mutation_importer.add_argument('--geometry', type=Path, required=True, help='mutate.py hash output for that corpus')
    mutation_importer.add_argument('--out', type=Path, required=True)
    for key in MUTATION_META_KEYS:
        mutation_importer.add_argument('--'+key.replace('_', '-'), required=True)
    args = parser.parse_args(argv)
    if args.command == 'check-mutations':
        code = check_mutations(args.golden, args.out, args.kit, args.gds_dir, args.rules, args.jobs, args.klayout)
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(errors='replace')
        print((args.out/'summary.md').read_text(encoding='utf-8'))
        return code
    if args.command == 'check':
        code = check(args.selftest, args.golden, args.out, args.rules)
        if hasattr(sys.stdout, 'reconfigure'):  # a non-UTF-8 console must not fail the check
            sys.stdout.reconfigure(errors='replace')
        print((args.out/'summary.md').read_text(encoding='utf-8'))
        return code
    if args.command == 'render':
        table = json.loads(args.table.read_text(encoding='utf-8'))
        args.out.write_text(render(table), encoding='utf-8', newline='\n')
        return 0
    if args.out.exists():
        parser.error(f'{args.out} exists; golden files are written once and never overwritten')
    if args.command == 'import-mutations':
        golden = import_mutations(args.counts, args.manifest, args.geometry,
                                  {key: getattr(args, key) for key in MUTATION_META_KEYS})
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(golden, indent=1)+'\n')
        return 0
    meta = {key: getattr(args, key) for key in META_KEYS}
    records = json.loads(args.selftest.read_text(encoding='utf-8'))['records']
    if any('case_sha256' not in record for record in records):
        meta['case_sha256_commit'] = _case_commit(meta['generator_commit'])
    golden = import_calibre(args.counts, args.selftest, meta, args.logs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(golden, indent=2)+'\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
