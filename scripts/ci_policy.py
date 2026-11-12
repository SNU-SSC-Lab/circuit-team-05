"""Read GitHub event data as JSON; never interpolate PR text into a shell."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from policy import PolicyError, check_docs, check_pr, root_at


def check_event(root, event):
    check_docs(root)
    if 'pull_request' not in event:
        return {'document_check':'passed','pr_check':'not_applicable'}
    pr=event['pull_request']
    base,head=pr['base']['sha'],pr['head']['sha']
    if not all(isinstance(v,str) and re.fullmatch(r'[0-9a-f]{40,64}',v) for v in (base,head)):
        raise PolicyError('base/head must be immutable Git commit SHAs')
    check_pr(root,pr.get('body') or '',base,head)
    return {'document_check':'passed','pr_check':'passed','base':base,'head':head}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event',default=os.getenv('GITHUB_EVENT_PATH'))
    args=parser.parse_args()
    start=time.perf_counter()
    try:
        event=json.loads(Path(args.event).read_text(encoding='utf-8')) if args.event else {}
        result=check_event(root_at('.'),event)
    except (PolicyError,ValueError,KeyError,TypeError,OSError) as error:
        print(str(error),file=sys.stderr); return 2
    result['wall_seconds']=time.perf_counter()-start
    print(json.dumps(result,ensure_ascii=False)); return 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
