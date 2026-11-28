"""Build this team's NSPL core; preserve failed and incomplete results."""
import argparse
from pathlib import Path
import shutil

from asic.flow import run_core


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk', type=Path, required=True, help='unpacked NSPL_05CMOS_PDK_260820 root')
    parser.add_argument('--openroad', default=shutil.which('openroad'), help='OpenROAD executable')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--target', choices=['core', 'chip'], default='chip')
    parser.add_argument('--experimental', action='store_true',
                        help='allow an incomplete qualification result; never means fabrication readiness')
    args = parser.parse_args()
    if not args.openroad:
        parser.error('OpenROAD not found; provide --openroad')
    return run_core(args)


if __name__ == '__main__':
    raise SystemExit(main())
