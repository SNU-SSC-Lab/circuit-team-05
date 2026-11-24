"""NSPL 260820 inputs and audited, local-only LEF adaptations (SPEC 0017)."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

STEM = 'NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T'
LIB_SHA = '0c84f0d970d374ba5c9c4cf7aec22fec96e306f8be373bda9ef20ce2bb48de51'
LEF_SHA = '62c02ae7a9266091fe283187325a71be359c0e774526f6a440285c36f5af4654'
GDS_SHA = 'e42dc1fb4c9a31aaa669e8e4c3b93a4b0d6eea40a463f5eaef5dbd17b432618e'
TECH_SHA = '5a145336772553d3c5378a9490502796515fd59a2d99165a4b98b0c7c0c63f7a'
CDL_SHA = '281efca41e93e7f88cf59e18e64159f9772111cfee1f86647cbd6ac3703e9f11'
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(pdk, output, *, repair_contact=True):
    """Never change original files; verify geometry before moving OBS to CONT."""
    pdk, output = Path(pdk).resolve(), Path(output).resolve()
    digital = pdk / (STEM + '_PnR')
    if not digital.is_dir():
        raise ValueError(f'NSPL digital kit missing: {digital}')
    output.mkdir(parents=True, exist_ok=False)
    views = {'cells.lib': ('LIB', STEM + '_std_tt.lib'),
             'cells.lef': ('LEF', STEM + '_std.lef'),
             'technology.lef': ('LEF', STEM + '_tech.lef'),
             'cells.gds': ('GDS', STEM + '_std.gds'),
             'cells.cdl': ('CDL', STEM + '_std.cdl')}
    inputs = {}
    for name, (folder, filename) in views.items():
        source = digital / folder / filename
        inputs[name] = {'source': str(source), 'sha256': sha(source)}
        shutil.copyfile(source, output / name)
    for name, expected in [('cells.lib', LIB_SHA), ('cells.lef', LEF_SHA), ('cells.gds', GDS_SHA),
                            ('technology.lef', TECH_SHA), ('cells.cdl', CDL_SHA)]:
        if inputs[name]['sha256'] != expected:
            raise ValueError(f'unreviewed NSPL file: {name}')
    env = dict(os.environ, SSC_LEF=str(output/'cells.lef'), SSC_GDS=str(output/'cells.gds'),
               SSC_AUDIT_OUT=str(output/'lef-audit.json'), QT_QPA_PLATFORM='offscreen')
    with (output/'lef-audit.log').open('w') as log:
        subprocess.run(['klayout', '-b', '-r', str(HERE/'audit_lef.py')], env=env,
                       stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
    audit = json.loads((output/'lef-audit.json').read_text())
    cells = audit['cells']
    if len(cells) != 38 or not all(c['VIA1']['gds_comparison']['CONT']['equal'] for c in cells.values()):
        raise ValueError('LEF VIA1 obstruction != original GDS CONT; adaptation refused')
    lef = (output/'cells.lef').read_text()
    changes = []
    if repair_contact:
        def fix_obs(match):
            body, count = re.subn(r'\bLAYER VIA1\b', 'LAYER CONT', match[0])
            if count != 1:
                raise ValueError('unexpected number of obstruction layers')
            return body
        lef, count = re.subn(r'\n  OBS\n.*?\n  END', fix_obs, lef, flags=re.S)
        if count != 38:
            raise ValueError('expected 38 audited obstruction blocks')
        changes.append({'change': 'OBS VIA1 -> CONT', 'cells': count,
                        'reason': 'exact equality to original GDS CONT, no shape deletion'})
    for cell in ['FAX1', 'HAX1']:
        pattern = r'(^MACRO ' + cell + r'\n.*?^  PIN S\n\s+DIRECTION )INPUT'
        lef, count = re.subn(pattern, r'\g<1>OUTPUT', lef, flags=re.M | re.S)
        if count != 1:
            raise ValueError(f'{cell}.S direction not found exactly once')
    changes.append({'change': 'FAX1.S/HAX1.S direction OUTPUT',
                    'reason': 'sum outputs in Liberty/CDL; no geometry change'})
    (output/'cells.lef').write_text(lef)
    tech = (output/'technology.lef').read_text()
    for layer in ['NSD', 'PSD']:
        tech, count = re.subn(r'^LAYER '+layer+r'\n.*?^END '+layer+r'\n', '', tech, flags=re.M | re.S)
        if count != 1:
            raise ValueError(f'expected implant declaration {layer}')
    tech, count = re.subn(r'^VIARULE V01 GENERATE DEFAULT\n.*?^END V01\n', '', tech, flags=re.M | re.S)
    if count != 1:
        raise ValueError('expected nonrouting POLY1 contact generation rule')
    # Materialize the kit's generated routing vias for TritonRoute. Geometry
    # follows 0.8 um cuts + 0.6 um enclosure from V12/V23, not new rules.
    vias = []
    for name, low, cut, high in [('NSPL_V12', 'MET1', 'VIA1', 'MET2'),
                                  ('NSPL_V23', 'MET2', 'VIA2', 'MET3')]:
        vias.append(f'''VIA {name} DEFAULT
  LAYER {low} ;
    RECT -1 -1 1 1 ;
  LAYER {cut} ;
    RECT -0.4 -0.4 0.4 0.4 ;
  LAYER {high} ;
    RECT -1 -1 1 1 ;
END {name}
''')
    tech = tech.replace('END LIBRARY', '\n'.join(vias)+'\nEND LIBRARY')
    for layer, lower in [('VIA1', 'CONT'), ('VIA2', 'VIA1')]:
        pattern = r'(^LAYER '+layer+r'\n.*?)(^END '+layer+r'\n)'
        tech, count = re.subn(pattern, lambda m: m[1]+'  SPACING 0.6 LAYER '+lower+' ;\n'+m[2],
                              tech, flags=re.M | re.S)
        if count != 1:
            raise ValueError('missing routing cut layer: '+layer)
    (output/'technology.lef').write_text(tech)
    changes.append({'change': 'omit NSD/PSD declarations and POLY1 contact generator from routing LEF',
                    'reason': 'nonrouting entries unsupported by QRouter; original cell GDS retained'})
    changes.append({'change': 'materialize NSPL_V12 and NSPL_V23 default vias',
                    'reason': '0.8 cut + 0.6 enclosure, copied from original V12/V23 generation rules'})
    changes.append({'change': 'inter-layer cut spacing 0.6 um for VIA1/CONT and VIA2/VIA1',
                    'reason': 'NSPL Calibre 9.VIA1.S and 11.VIA2.S prohibit cut stacking'})
    result = {'inputs': inputs, 'changes': changes,
              'derived': {name: sha(output/name) for name in views}}
    (output/'adapter.json').write_text(json.dumps(result, indent=2)+'\n')
    return digital
