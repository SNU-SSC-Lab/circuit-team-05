"""Checks of what this team commits after RTL (verification/pdk/flow.toml). No PDK needed. SPEC 0015.

Ported from SNU-SSC-Lab/circuit-integration harness/flow.py at 60c7acc (check_layout stays there).

files    Only the allowed file types under mychip/ (no GDS, no tool databases). Copies of PDK files
         anywhere in the repository are listed (by git blob id, so nothing is downloaded) but do not
         fail: the PDK is public.
signoff  mychip/3-signoff: the DRC summary is clean, the LVS report matches, both are for the
         chip's top cell, and the GDS hash is a SHA-256. Missing until the folder has files.

The netlists in mychip/1-synth and mychip/2-pnr need the PDK; scripts/pdk.py checks them.
"""
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'verification' / 'pdk'
FLOW = tomllib.loads((CONFIG / 'flow.toml').read_text(encoding='utf-8'))


def pdk_blobs():
    path = CONFIG / FLOW['leak']['blob_list']
    return {line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()}


def tree(repo):
    """[(blob id, path)] of every file at HEAD, from git trees only."""
    run = subprocess.run(['git', '-C', str(repo), 'ls-tree', '-r', '-z', 'HEAD'], capture_output=True)
    if run.returncode != 0:
        return None
    entries = []
    for item in run.stdout.decode('utf-8', 'replace').split('\0'):
        if not item:
            continue
        meta, path = item.split('\t', 1)
        _mode, kind, oid = meta.split()
        if kind == 'blob':
            entries.append((oid, path))
    return entries


def check_files(repo, blobs=None):
    entries = tree(repo)
    if entries is None:
        return {'status': 'missing', 'detail': 'not a git checkout'}
    blobs = pdk_blobs() if blobs is None else blobs
    names = re.compile(FLOW['leak']['name_pattern'], re.I)
    folder = FLOW['folder'] + '/'
    allowed = tuple(FLOW['allowed'])
    # The PDK is public, so copies of it are reported, not failed.
    copies = [path for oid, path in entries if oid in blobs or names.search(path.rsplit('/', 1)[-1])]
    problems = [f'not allowed under {folder}: {path} (allowed: {" ".join(allowed)})' for _, path in entries
                if path.startswith(folder) and not path.lower().endswith(allowed)]
    # A stage counts once it holds a real result, not just the skeleton's .gitkeep or a README.
    placeholders = ('.gitkeep', '.gitignore', '.md')
    stages = sorted({path[len(folder):].split('/', 1)[0] for _, path in entries
                     if path.startswith(folder) and '/' in path[len(folder):]
                     and not path.lower().endswith(placeholders)})
    return {'status': 'fail' if problems else 'pass', 'problems': problems[:20], 'files': len(entries),
            'mychip': stages, 'pdk_copies': copies}


# Clean / matching verdicts of the two sign-off tools the guide accepts (p. 8).
DRC_TOTAL = re.compile(r'TOTAL\s+(?:DRC\s+)?RESULTS\s+GENERATED\s*[:=]\s*(\d+)', re.I)
DRC_CLEAN = re.compile(r'No\s+(?:DRC\s+)?errors?\s+(?:were\s+)?found|Total\s+(?:DRC\s+)?errors?\s*[:=]\s*0\b', re.I)
LVS_MATCH = re.compile(r'(?<!IN)\bCORRECT\b|Schematic\s+and\s+Layout\s+Match', re.I)
LVS_MISMATCH = re.compile(r'\bINCORRECT\b|do(?:es)?\s+not\s+match', re.I)


def signoff_paths(repo, top):
    stage = FLOW['stages']['signoff']
    base = Path(repo) / FLOW['folder'] / stage['dir']
    return {key: base / stage[key].format(top=top) for key in ('drc', 'lvs', 'gds_sha256')}


def check_signoff(repo, top):
    repo = Path(repo)
    paths = signoff_paths(repo, top)
    present = {k: p for k, p in paths.items() if p.is_file()}
    rel = {k: p.relative_to(repo).as_posix() for k, p in paths.items()}
    if not present:
        return {'status': 'missing', 'detail': f"no sign-off files yet ({rel['drc']}, {rel['lvs']}, {rel['gds_sha256']})"}
    problems = [f'missing {rel[k]}' for k in paths if k not in present]
    result = {}
    if 'drc' in present:
        text = present['drc'].read_text(encoding='utf-8', errors='replace')
        totals = [int(n) for n in DRC_TOTAL.findall(text)]
        if totals:
            result['drc_results'] = sum(totals)
            if sum(totals) != 0:
                problems.append(f"DRC: {sum(totals)} results ({rel['drc']})")
        elif not DRC_CLEAN.search(text):
            problems.append(f"DRC: no clean verdict found in {rel['drc']} "
                            "(Calibre 'TOTAL DRC Results Generated: 0' or Assura 'No errors found')")
        if top.lower() not in text.lower():
            problems.append(f'DRC report does not name the top cell {top}')
    if 'lvs' in present:
        text = present['lvs'].read_text(encoding='utf-8', errors='replace')
        if LVS_MISMATCH.search(text) or not LVS_MATCH.search(text):
            problems.append(f"LVS: no match verdict in {rel['lvs']} (Calibre 'CORRECT' or Assura 'Schematic and Layout Match')")
        if top.lower() not in text.lower():
            problems.append(f'LVS report does not name the top cell {top}')
    if 'gds_sha256' in present:
        first = present['gds_sha256'].read_text(encoding='utf-8', errors='replace').split()
        if not first or not re.fullmatch(r'[0-9a-fA-F]{64}', first[0]):
            problems.append(f"{rel['gds_sha256']} must start with the 64-hex SHA-256 of the GDS")
        else:
            result['gds_sha256'] = first[0].lower()
    status = 'fail' if any(not p.startswith('missing ') for p in problems) else 'missing' if problems else 'pass'
    return {'status': status, 'problems': problems, **result}


def stage_netlists(repo, top):
    """{stage: (netlist, spef or None)} for 1-synth and 2-pnr, where the netlist exists."""
    found = {}
    for name in ('synth', 'pnr'):
        stage = FLOW['stages'][name]
        base = Path(repo) / FLOW['folder'] / stage['dir']
        netlist = base / stage['netlist'].format(top=top)
        if netlist.is_file():
            spef = base / stage['spef'].format(top=top) if 'spef' in stage else None
            found[name] = (netlist, spef if spef and spef.is_file() else None)
    return found


def team_sdc(repo, top):
    path = Path(repo) / FLOW['folder'] / FLOW['constraints'].format(top=top)
    return path if path.is_file() else None
