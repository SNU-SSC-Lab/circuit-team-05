#!/usr/bin/env python3
"""Magic DRC / Netgen LVS runner and scmos tool self-test. SPEC 0016.

No process kit is supplied. Real inputs and their hashes belong in an external
TOML manifest; see docs/verification/magic-netgen-guide.md.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / '.policy-tmp' / 'physical'
FILE_KEYS = ('layout', 'schematic', 'magicrc', 'technology', 'netgen_setup')
TOKEN = re.compile(r'[A-Za-z_][A-Za-z0-9_.$-]*\Z')

MAGIC_SCRIPT = r'''
if {[catch {
    if {[tech name] ne $::env(SSC_TECH_NAME)} {error "wrong technology name"}
    if {[file normalize [tech filename]] ne [file normalize $::env(SSC_TECH_FILE)]} {
        error "wrong technology file"
    }
    if {$::env(SSC_DRC_STYLE) ne ""} {drc style $::env(SSC_DRC_STYLE)}
    drc off
    set top $::env(SSC_TOP)
    set layout $::env(SSC_LAYOUT)
    if {[string tolower [file extension $layout]] eq ".mag"} {
        load $layout -force
    } else {
        if {$::env(SSC_GDS_STYLE) ne ""} {cif istyle $::env(SSC_GDS_STYLE)}
        gds read $layout
    }
    if {[lsearch -exact [cellname list allcells] $top] < 0} {error "top cell not found"}
    load $top
    if {[tech name] ne $::env(SSC_TECH_NAME) ||
        [file normalize [tech filename]] ne [file normalize $::env(SSC_TECH_FILE)]} {
        error "technology changed while loading layout"
    }
    select top cell
    expand
    box select
    set bbox [box values]
    lassign $bbox x1 y1 x2 y2
    if {$x2 <= $x1 || $y2 <= $y1} {error "empty layout"}
    set meta [open magic-meta.txt w]
    puts $meta "technology=[tech name]"
    puts $meta "technology_file=[tech filename]"
    puts $meta "drc_style=[drc list style]"
    puts $meta "gds_input_style=[cif istyle]"
    puts $meta "bbox=$bbox"
    close $meta
    drc ignore none
    drc on
    drc check
    drc catchup
    set count [drc listall count total]
    set result [open drc-count.txt w]
    puts $result $count
    close $result
    set result [open drc-detail.txt w]
    puts $result [drc listall count]
    foreach {reason rects} [drc listall why] {
        puts $result $reason
        foreach rect $rects {puts $result "  $rect"}
    }
    close $result
    extract path .
    extract all
    ext2spice lvs
    ext2spice subcircuit top on
    ext2spice -o layout.spice
    set result [open magic-complete.txt w]
    puts $result complete
    close $result
} detail]} {
    puts stderr "SSC_MAGIC_ERROR: $detail"
}
quit -noprompt
'''

NETGEN_SCRIPT = r'''
if {[catch {
    lvs [list $::env(SSC_EXTRACTED) $::env(SSC_TOP)] \
        [list $::env(SSC_SCHEMATIC) $::env(SSC_TOP)] \
        $::env(SSC_SETUP) lvs.log -json
    set result [open netgen-complete.txt w]
    puts $result complete
    close $result
} detail]} {
    puts stderr "SSC_NETGEN_ERROR: $detail"
}
'''


def write(path, value):
    path.write_text(value, encoding='utf-8')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def fresh(path):
    """Never read output left by a preceding invocation. Never remove user files."""
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise ValueError(f'결과 폴더가 비어 있지 않습니다. 새 경로를 쓰세요: {path}')
    return path


def executable(name):
    override = os.environ.get('SSC_' + name.upper())
    found = shutil.which(override or name)
    if name == 'netgen' and not override:
        found = shutil.which('netgen-lvs') or found
    if not found:
        raise ValueError(f'{name} 실행 파일이 없습니다. 상세 사용서의 설치 절차를 확인하세요.')
    return found


def run(command, cwd, log, env=None, timeout=300):
    started = time.monotonic()
    with log.open('w', encoding='utf-8') as output:
        try:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=output,
                                    stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            raise ValueError(f'{log.name}: {timeout}초 제한을 넘었습니다.') from error
    if result.returncode:
        raise ValueError(f'{log.name}: 종료 코드 {result.returncode}')
    return round(time.monotonic() - started, 3)


def load_manifest(path):
    path = Path(path).resolve()
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    design = data['design']
    for key in ('top', 'technology_name'):
        if not isinstance(design.get(key), str) or not TOKEN.fullmatch(design[key]):
            raise ValueError(f'design.{key}: 비어 있거나 지원하지 않는 이름')
    files = {}
    hashes = {}
    for key in FILE_KEYS:
        value = data['files'][key]
        if not isinstance(value, str) or not value:
            raise ValueError(f'files.{key}: 경로를 채우세요.')
        file = (path.parent / value).resolve()
        if not file.is_file() or file.stat().st_size == 0:
            raise ValueError(f'files.{key}: 비어 있거나 없는 파일: {file}')
        expected = data['sha256'][key]
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError(f'sha256.{key}: 소문자 SHA-256 64자 필요')
        actual = digest(file)
        if expected != actual:
            raise ValueError(f'sha256.{key}: 입력 파일이 기록한 해시와 다릅니다.')
        files[key], hashes[key] = file, actual
    if files['layout'].suffix.lower() not in ('.gds', '.mag'):
        raise ValueError('layout은 압축하지 않은 .gds 또는 .mag 파일이어야 합니다.')
    if files['layout'].suffix.lower() == '.mag' and files['layout'].stem != design['top']:
        raise ValueError('.mag 파일 이름은 design.top과 같아야 합니다.')
    if len(set(files.values())) != len(files):
        raise ValueError('각 입력은 서로 다른 파일이어야 합니다.')
    # Additional kit dependencies (included Tcl/CDL, layer maps, child .mag files)
    # must be enumerated by the operator; the runner cannot discover arbitrary Tcl IO.
    dependencies = []
    for item in data.get('dependencies', []):
        file = (path.parent / item['path']).resolve()
        if not file.is_file() or digest(file) != item['sha256']:
            raise ValueError(f'추가 의존 파일 누락 또는 해시 불일치: {file}')
        dependencies.append({'path': str(file), 'sha256': item['sha256']})
    timeout = design.get('timeout_seconds', 300)
    if type(timeout) is not int or not 1 <= timeout <= 7200:
        raise ValueError('timeout_seconds: 1~7200 정수 필요')
    return design, files, hashes, dependencies


def spice_has_devices(path, top):
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    if not re.search(r'^\s*\.subckt\s+' + re.escape(top) + r'(?:\s|$)', text, re.I | re.M):
        return False
    # A zero-device / all-metal circuit can produce a misleading LVS match.
    return bool(re.search(r'^\s*[mMqQdDrRcCxX]\S*\s+\S+', text, re.M))


def lvs_verdict(report, cells, top):
    """Fail on missing / incomplete results, property errors and black boxes."""
    # Ubuntu 24.04 ships 1.5.133: no "Final result:" header; the final
    # nonempty report line is the verdict. Never accept a subcell match.
    if 'Final result:' in report:
        final = report.rsplit('Final result:', 1)[1]
    else:
        lines = [line.strip() for line in report.splitlines() if line.strip()]
        final = lines[-1] if lines else ''
    # Netgen 1.5.323 appends a line containing only '.' after its verdict.
    # Accept that exact terminator, never arbitrary text after success.
    final = re.sub(r'\n\s*\.\s*$', '', final).strip()
    if final.strip() != 'Circuits match uniquely.':
        return False
    if re.search(r'property errors|do not match|mismatch|black.?box|undefined', report, re.I):
        return False
    if not isinstance(cells, list) or not cells:
        return False
    found_top = False
    for cell in cells:
        if not isinstance(cell, dict) or not all(k in cell for k in ('name', 'devices', 'nets', 'pins')):
            return False
        if any(cell.get(k) for k in ('badnets', 'badelements', 'properties')):
            return False
        nets, devices, pins = cell['nets'], cell['devices'], cell['pins']
        if len(nets) != 2 or nets[0] != nets[1] or len(devices) != 2 or len(pins) != 2:
            return False
        if not pins[0] or not pins[1]:
            return False
        if Counter(str(p).lower() for p in pins[0]) != Counter(str(p).lower() for p in pins[1]):
            return False
        counts = [sum(int(count) for _name, count in side) for side in devices]
        if counts[0] != counts[1]:
            return False
        if [str(n).lower() for n in cell['name']] == [top.lower(), top.lower()]:
            found_top = counts[0] > 0 and nets[0] > 0
    return found_top


def inspect(manifest, out):
    started = time.monotonic()
    result = {'status': 'fail', 'drc': 'not_run', 'lvs': 'not_run',
              'scope': 'supplied_inputs', 'official_signoff': False}
    try:
        design, files, hashes, dependencies = load_manifest(manifest)
        top = design['top']
        result.update(top=top, inputs={k: {'path': str(p), 'sha256': hashes[k]}
                                      for k, p in files.items()}, dependencies=dependencies,
                      manifest_sha256=digest(manifest))
        if not spice_has_devices(files['schematic'], top):
            raise ValueError('기준 회로에 지정한 .subckt top 또는 소자가 없습니다.')
        magic, netgen = executable('magic'), executable('netgen')
        run([magic, '--version'], out, out / 'magic-version.txt')
        run([netgen, '-batch'], out, out / 'netgen-version.txt')
        version = (out / 'netgen-version.txt').read_text(encoding='utf-8', errors='replace')
        if not re.search(r'Netgen\s+1\.5\.', version):
            raise ValueError('전자회로 LVS용 Netgen 1.5가 아닙니다.')
        result['tools'] = {'magic': magic, 'netgen': netgen,
                           'magic_version': (out / 'magic-version.txt').read_text().strip(),
                           'netgen_version': version.strip()}
        env = dict(os.environ, SSC_TOP=top, SSC_TECH_NAME=design['technology_name'],
                   SSC_TECH_FILE=str(files['technology']), SSC_LAYOUT=str(files['layout']),
                   SSC_DRC_STYLE=design.get('drc_style', ''),
                   SSC_GDS_STYLE=design.get('gds_input_style', ''))
        write(out / 'magic.tcl', MAGIC_SCRIPT)
        result['magic_seconds'] = run([magic, '-dnull', '-noconsole', '-rcfile',
                                      str(files['magicrc']), '-T', str(files['technology']),
                                      str(out / 'magic.tcl')], out, out / 'magic.log', env,
                                     design.get('timeout_seconds', 300))
        magic_log = (out / 'magic.log').read_text(encoding='utf-8', errors='replace')
        if not (out / 'magic-complete.txt').is_file():
            raise ValueError('Magic이 완료 표시를 남기지 않았습니다. magic.log를 확인하세요.')
        if re.search(r'SSC_MAGIC_ERROR|^Error\b|unknown.*(?:layer|cell|command)|'
                     r'undefined|not found|couldn.t|cannot (?:read|open)|unrecognized', magic_log, re.I | re.M):
            raise ValueError('Magic 읽기/명령 오류. magic.log를 확인하세요.')
        count = int((out / 'drc-count.txt').read_text(encoding='utf-8').strip())
        if count < 0:
            raise ValueError('DRC 오류 수가 음수입니다.')
        result.update(drc='pass' if count == 0 else 'fail', drc_error_tiles=count)
        if not spice_has_devices(out / 'layout.spice', top):
            raise ValueError('추출 회로에 top 또는 소자가 없습니다. 레이어·추출 규칙을 확인하세요.')
        env.update(SSC_EXTRACTED=str(out / 'layout.spice'), SSC_SCHEMATIC=str(files['schematic']),
                   SSC_SETUP=str(files['netgen_setup']))
        write(out / 'netgen.tcl', NETGEN_SCRIPT)
        result['lvs'] = 'fail'
        result['netgen_seconds'] = run([netgen, '-batch', 'source', str(out / 'netgen.tcl')],
                                      out, out / 'netgen.log', env,
                                      design.get('timeout_seconds', 300))
        if not (out / 'netgen-complete.txt').is_file():
            raise ValueError('Netgen이 완료 표시를 남기지 않았습니다. netgen.log를 확인하세요.')
        report = (out / 'lvs.log').read_text(encoding='utf-8', errors='replace')
        console = (out / 'netgen.log').read_text(encoding='utf-8', errors='replace')
        cells = json.loads((out / 'lvs.json').read_text(encoding='utf-8'))
        match = lvs_verdict(report, cells, top)
        if re.search(r'SSC_NETGEN_ERROR|black.?box|undefined|unknown subcircuit|'
                     r'cannot (?:read|open)|no such file|^Error\b', console, re.I | re.M):
            match = False
        result['lvs'] = 'pass' if match else 'fail'
        for key, file in files.items():
            if digest(file) != hashes[key]:
                raise ValueError(f'검사 도중 입력 파일 변경: {key}')
        result['status'] = 'pass' if result['drc'] == result['lvs'] == 'pass' else 'fail'
    except (ValueError, OSError, KeyError, IndexError, TypeError, subprocess.SubprocessError) as error:
        result['status'] = 'fail'
        result['error'] = str(error)
    result['seconds'] = round(time.monotonic() - started, 3)
    write(out / 'result.json', json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def demo_inputs(folder, magic):
    folder.mkdir()
    # Own practice geometry: one nfet, 8 lambda wide and 2 lambda long.
    # It is NOT an NSPL/ETRI test cell or a model for the project circuit.
    create = r'''
drc off
load demo -force
box values 0 0 14 8
paint ndiff
box values 6 -4 8 12
paint poly
box values 1 2 3 4
label S center ndiff
port make 1
box values 10 2 12 4
label D center ndiff
port make 2
box values 6 9 8 11
label G center poly
port make 3
save demo
gds write demo.gds
set f [open technology-path.txt w]
puts $f [tech filename]
close $f
quit -noprompt
'''
    write(folder / 'create.tcl', create)
    write(folder / 'magicrc', '# Deliberately empty: built-in scmos, practice only.\n')
    run([magic, '-dnull', '-noconsole', '-rcfile', str(folder / 'magicrc'), '-T', 'scmos',
         str(folder / 'create.tcl')], folder, folder / 'create.log')
    technology = Path((folder / 'technology-path.txt').read_text().strip())
    write(folder / 'reference.spice', '* Independently specified practice nfet\n'
          '.global Vdd Gnd\n.subckt demo S D G\nM1 D G S Gnd nfet w=8u l=2u\n.ends demo\n')
    write(folder / 'netgen-setup.tcl', 'permute default\nproperty default\n'
          'property {-circuit1 nfet} remove ad pd as ps\n'
          'property {-circuit2 nfet} remove ad pd as ps\n')
    files = dict(layout=folder / 'demo.mag', schematic=folder / 'reference.spice',
                 magicrc=folder / 'magicrc', technology=technology,
                 netgen_setup=folder / 'netgen-setup.tcl')
    return files


def demo_manifest(folder, files, top='demo'):
    manifest = folder / 'run.toml'
    lines = ['[design]', f'top = "{top}"', 'technology_name = "scmos"', '', '[files]']
    lines += [f'{k} = {json.dumps(str(p))}' for k, p in files.items()]
    lines += ['', '[sha256]'] + [f'{k} = "{digest(p)}"' for k, p in files.items()]
    write(manifest, '\n'.join(lines) + '\n')
    return manifest


def selftest(out):
    started = time.monotonic()
    magic = executable('magic')
    files = demo_inputs(out / 'inputs', magic)
    rows = []

    def case(name, values, expected, top='demo'):
        folder = fresh(out / name)
        manifest = demo_manifest(folder, values, top)
        actual = inspect(manifest, folder)
        okay = all(actual.get(k) == v for k, v in expected.items())
        rows.append({'name': name, 'status': 'pass' if okay else 'fail',
                     'expected': expected, 'actual': actual})

    case('clean', files, dict(status='pass', drc='pass', lvs='pass'))
    bad_ref = out / 'inputs' / 'wrong.spice'
    write(bad_ref, files['schematic'].read_text().replace('D G S Gnd', 'D S S Gnd'))
    case('lvs-mismatch', dict(files, schematic=bad_ref), dict(status='fail', drc='pass', lvs='fail'))
    bad_property = out / 'inputs' / 'wrong-width.spice'
    write(bad_property, files['schematic'].read_text().replace('w=8u', 'w=7u'))
    case('lvs-property', dict(files, schematic=bad_property), dict(status='fail', drc='pass', lvs='fail'))
    # scmos' generic GDS round-trip does not preserve these ports / well identity.
    # It must not be accepted just because geometry was successfully imported.
    case('gds-missing-ports', dict(files, layout=out / 'inputs' / 'demo.gds'),
         dict(status='fail', drc='pass', lvs='fail'))
    bad_width = out / 'inputs' / 'badwidth.mag'
    write(bad_width, 'magic\ntech scmos\ntimestamp 0\n<< metal1 >>\nrect 0 0 1 20\n<< end >>\n')
    # Put the error in a child of a top that also contains the valid nfet.
    hierarchy = out / 'inputs' / 'demo.mag'
    text = hierarchy.read_text()
    # A separate parent keeps the clean layout and its recorded hash unchanged.
    child_folder = out / 'inputs' / 'hierarchy'
    child_folder.mkdir()
    shutil.copyfile(bad_width, child_folder / bad_width.name)
    hierarchy = child_folder / 'demo.mag'
    write(hierarchy, text.replace('<< end >>', 'use badwidth child0\n'
          'timestamp 0\ntransform 1 0 30 0 1 0\nbox 0 0 1 20\n<< end >>'))
    case('hierarchy-drc', dict(files, layout=hierarchy), dict(status='fail', drc='fail', lvs='pass'))
    case('missing-top', files, dict(status='fail', drc='not_run', lvs='not_run'), top='absent')
    status = 'pass' if all(row['status'] == 'pass' for row in rows) else 'fail'
    result = {'status': status, 'scope': 'scmos_tool_selftest', 'official_signoff': False,
              'project_drc': 'not_run', 'project_lvs': 'not_run', 'tests': rows,
              'seconds': round(time.monotonic() - started, 3)}
    write(out / 'result.json', json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def report(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    labels = {'pass': '통과', 'fail': '실패', 'not_run': '미실행'}
    lines = ['## Magic / Netgen 검사', '', '| 항목 | 결과 |', '| --- | --- |']
    if data['scope'] == 'scmos_tool_selftest':
        for row in data['tests']:
            lines.append(f"| 도구 자체 시험: {row['name']} | {labels[row['status']]} |")
        lines += ['| **실제 5팀 DRC** | **미실행: 실제 GDS·공정 설정 없음** |',
                  '| **실제 5팀 LVS** | **미실행: 기준 회로·공정 설정 없음** |', '',
                  'scmos 연습 회로 결과입니다. NSPL 공정 검사·공식 사인오프 결과가 아닙니다.']
    else:
        for key in ('drc', 'lvs'):
            lines.append(f'| {key.upper()} | {labels[data[key]]} |')
        lines += ['', f"대상 top: `{data.get('top', '미확인')}`. "
                  f"DRC 오류 타일: {data.get('drc_error_tiles', '미확인')}. "
                  f"소요 시간: {data.get('seconds', '?')}초. 공식 사인오프 판정 아님."]
    if data.get('error'):
        lines += ['', '실행 오류: ' + data['error']]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('selftest', 'check'):
        command = sub.add_parser(action)
        command.add_argument('--out', type=Path, default=DEFAULT_OUT / action)
        if action == 'check':
            command.add_argument('--manifest', type=Path, required=True)
    sub.add_parser('report').add_argument('--result', type=Path, default=DEFAULT_OUT / 'selftest/result.json')
    args = parser.parse_args()
    if args.action == 'report':
        print(report(args.result))
        return 0
    out = fresh(args.out)
    try:
        result = selftest(out) if args.action == 'selftest' else inspect(args.manifest, out)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result = {'status': 'fail', 'scope': 'scmos_tool_selftest', 'tests': [],
                  'project_drc': 'not_run', 'project_lvs': 'not_run', 'error': str(error)}
        write(out / 'result.json', json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(report(out / 'result.json'))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'실행 실패: {error}', file=sys.stderr)
        sys.exit(1)
