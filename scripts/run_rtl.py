"""Run named RTL CI suites locally; report build and simulation wall time separately."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    'integration':['boundary_packets','positions_and_illegal','protocol_and_back_to_back','reset_each_phase'],
    'regression':['all_legal_weights','random_jobs'],
}


def execute(command, log):
    start=time.perf_counter()
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    log.parent.mkdir(parents=True,exist_ok=True)
    log.write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:
        raise RuntimeError(f'{command[0]} failed: see {log}\n{result.stderr[-3000:]}')
    return time.perf_counter()-start


def version(command):
    result=subprocess.run(command,capture_output=True,text=True)
    return (result.stdout or result.stderr).splitlines()[0]


def validate_results(xml, case, stats):
    tree=ET.parse(xml)
    cases=[t for t in tree.findall('.//testcase') if t.get('name')==case]
    if (len(cases)!=1 or tree.findall('.//failure') or tree.findall('.//error') or
            any(t.find('skipped') is not None for t in cases) or not stats.is_file()):
        raise RuntimeError(f'{case}: missing, failed, or skipped tests: {xml}')


def lint(config, output):
    sources=[str(ROOT/p) for p in config['sources']]
    vtime=execute(['verilator','--lint-only','--Wall',str(ROOT/'verification/lint.vlt'),'--top-module',config['top'],*sources],output/'verilator.log')
    itime=execute(['iverilog','-g2012','-Wall','-s',config['top'],'-o',str(output/'compile.vvp'),*sources],output/'iverilog.log')
    return {'verilator_seconds':vtime,'iverilog_seconds':itime}


def simulate(config, suite, build_root, output, waves=False):
    sys.path.insert(0,str(ROOT/'tests/rtl'))
    from cocotb_tools.runner import get_runner
    sim='verilator' if suite=='coverage' else 'icarus'
    tasks=([(dut,'unit_contract') for dut in config['unit_tops']] if suite=='unit' else
           [(config['top'],case) for case in (GROUPS['integration']+GROUPS['regression'] if suite=='coverage' else GROUPS[suite])])
    build_seconds=0.0
    model_seconds=execute([sys.executable,'-m','unittest','discover','-s','tests/rtl','-p','test_model.py','-v'],output/'model-unit.log') if suite=='unit' else 0.0
    records=[]; built=set(); runners={}
    for dut,case in tasks:
        if dut not in runners: runners[dut]=get_runner(sim)
        runner=runners[dut]
        build=build_root/sim/dut
        result_dir=output/f'{dut}-{case}'; result_dir.mkdir(parents=True,exist_ok=True)
        if dut not in built:
            start=time.perf_counter()
            args=['--coverage-line'] if sim=='verilator' else ['-g2012','-Wall']
            runner.build(sources=[ROOT/p for p in config['sources']],hdl_toplevel=dut,
                         build_dir=build,build_args=args,timescale=('1ns','1ps'),waves=waves,
                         log_file=output/f'{dut}-build.log')
            build_seconds+=time.perf_counter()-start
            built.add(dut)
        stats=result_dir/'stats.json'
        stats.unlink(missing_ok=True)
        (result_dir/'coverage.dat').unlink(missing_ok=True)
        start=time.perf_counter()
        module='test_units' if suite=='unit' else 'test_top'
        xml=runner.test(hdl_toplevel=dut,test_module=module,
                        test_filter=rf'^{module}\.{case}$',build_dir=build,test_dir=result_dir,
                        results_xml='results.xml',seed=config['seed'],waves=waves,
                        extra_env={'PYTHONPATH':str(ROOT/'tests/rtl'), 'SSC_DUT':dut,
                                   'SSC_STATS':str(stats),'SSC_DESIGN':str(ROOT/'verification/designs/ternary8.json')},
                        log_file=result_dir/'simulation.log')
        elapsed=time.perf_counter()-start
        validate_results(xml,case,stats)
        records.append({'dut':dut,'test':case,'simulation_seconds':elapsed,
                        'stats':json.loads(stats.read_text(encoding='utf-8'))})
        print(f'{suite}/{dut}/{case}: PASS {elapsed:.3f}s',flush=True)
    data={'build_seconds':build_seconds,'model_unit_seconds':model_seconds,'simulation_seconds':sum(r['simulation_seconds'] for r in records),'tests':records}
    if suite=='coverage':
        coverage_files=list(output.glob('*/coverage.dat'))
        if not coverage_files:
            raise RuntimeError('Verilator did not produce coverage.dat')
        info=output/'rtl-lines.info'
        execute(['verilator_coverage','--write-info',str(info),*[str(p) for p in coverage_files]],output/'coverage-merge.log')
        found=hit=0; files={}; current=None
        for line in info.read_text().splitlines():
            if line.startswith('SF:'):
                current=line[3:]
            elif line.startswith('DA:') and current and '/src/' in current.replace('\\','/'):
                number,count=line[3:].split(',')[:2]
                entry=files.setdefault(current,{'found':0,'hit':0,'uncovered_lines':[]})
                entry['found']+=1; found+=1
                if int(count)>0: entry['hit']+=1; hit+=1
                else: entry['uncovered_lines'].append(int(number))
        if not found: raise RuntimeError('No RTL source line coverage points')
        data['rtl_line_coverage']={'hit':hit,'found':found,'percent':100*hit/found,'files':files,
                                   'exclusions':[],'measurement':'Verilator --coverage-line; integration + regression'}
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite',choices=['lint','unit','integration','regression','coverage'])
    parser.add_argument('--build-root',type=Path,default=ROOT/'.policy-tmp/rtl-build')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--waves',action='store_true')
    args=parser.parse_args()
    output=(args.output or ROOT/f'.policy-tmp/results/rtl-{args.suite}').resolve(); output.mkdir(parents=True,exist_ok=True)
    config=json.loads((ROOT/'verification/designs/ternary8.json').read_text(encoding='utf-8'))
    start=time.perf_counter()
    report={'suite':f'rtl-{args.suite}','status':'failed',
            'versions':{'python':sys.version,'icarus':version(['iverilog','-V']),'verilator':version(['verilator','--version'])}}
    try:
        report['result']=lint(config,output) if args.suite=='lint' else simulate(config,args.suite,args.build_root.resolve(),output,args.waves)
        report['status']='passed'
    except (Exception,SystemExit) as error:
        report['error']=str(error)
        print(str(error),file=sys.stderr)
    report['wall_seconds']=time.perf_counter()-start
    (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('suite','status','wall_seconds')},ensure_ascii=False),flush=True)
    return int(report['status']!='passed')


if __name__=='__main__':
    sys.exit(main())
