"""Run expanded DRC fixtures using actual KLayout and saved GDS files."""
import argparse
import os
from pathlib import Path
import subprocess

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', SSC_DRC_TEST_OUT=str(out))
    with (out/'selftest.log').open('w') as stream:
        result = subprocess.run(['klayout', '-b', '-r', str(Path(__file__).with_name('drc_fixture_test.py'))],
                                env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
    print((out/'selftest.log').read_text())
    return result.returncode

if __name__ == '__main__':
    raise SystemExit(main())
