"""Build this team's NSPL core; preserve failed and incomplete results."""
import argparse
from pathlib import Path
import shutil

from asic.flow import UNQUALIFIED_DEFAULT, UNVERIFIED, load_allowed, run_core


def parse(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk', type=Path, required=True, help='unpacked NSPL_05CMOS_PDK_260820 root')
    parser.add_argument('--openroad', default=shutil.which('openroad'), help='OpenROAD executable')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--target', choices=['core', 'chip'], default='chip')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--experimental', action='store_true',
                      help='allow an incomplete qualification result; never means fabrication readiness')
    mode.add_argument('--gate', action='store_true',
                      help='merge gate (SPEC 0019): only checks named in verification/reliability/unverified.json '
                           'allows_checks may stay unsupported; never means fabrication readiness')
    args = parser.parse_args(argv)
    if not args.openroad:
        parser.error('OpenROAD not found; provide --openroad')
    if args.gate:
        args.mode, args.allowed = 'gate', load_allowed(UNVERIFIED)
    elif args.experimental:
        args.mode, args.allowed = 'experimental', UNQUALIFIED_DEFAULT
    else:
        args.mode, args.allowed = 'strict', frozenset()
    return args


def main(argv=None):
    return run_core(parse(argv))


if __name__ == '__main__':
    raise SystemExit(main())
