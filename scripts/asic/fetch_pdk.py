"""Fetch the pinned public NSPL kit for cell, GPIO and physical rule views."""
import argparse
from pathlib import Path
import tarfile

from setup_tools import download

URL = 'https://raw.githubusercontent.com/GoodKook/ETRI-0.5um-CMOS-MPW-Std-Cell-DK/11f1218feaa245fa7fb7c8dafa440e54543c63b4/docs/ETRI_0p5um_NSPL_260820/NSPL_05CMOS_PDK_260820.tar.gz'
SHA = '2e49115a08f6af96c1f8433130ad4316551b5eba9001a3133905b544166af954'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    archive = args.archive.resolve() if args.archive else out.parent/'NSPL_05CMOS_PDK_260820.tar.gz'
    archive.parent.mkdir(parents=True, exist_ok=True)
    download(URL, archive, SHA)
    marker = out/'.nspl-archive.sha256'
    if out.exists() and any(out.iterdir()):
        if not marker.is_file() or marker.read_text().strip() != SHA:
            raise ValueError('choose a new output directory; existing contents are not a verified cache')
    else:
        out.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as package:
            package.extractall(out, filter='data')
        marker.write_text(SHA+'\n')
    print(out/'NSPL_05CMOS_PDK_260820')


if __name__ == '__main__':
    main()
