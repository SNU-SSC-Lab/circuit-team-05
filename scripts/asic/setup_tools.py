"""Install pinned OpenROAD in an owned directory; no global package changes."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def download(url, path, expected):
    if not path.is_file():
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 SSC-ASIC'})
        temporary = path.with_suffix(path.suffix+'.part')
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as output:
            while data := response.read(1024*1024):
                output.write(data)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
            raise ValueError('download checksum mismatch: '+path.name)
        temporary.replace(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('cached checksum mismatch: '+path.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--downloads', type=Path)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    lock = json.loads((ROOT/'verification/asic/tools.json').read_text())
    out = args.out.resolve()
    cache = args.downloads.resolve() if args.downloads else out/'downloads'
    cache.mkdir(parents=True, exist_ok=True)
    root = out/'root'
    root.mkdir(parents=True, exist_ok=True)
    for package in lock['packages']:
        path = cache/package['name']
        if args.offline and not path.is_file():
            raise FileNotFoundError(path)
        download(package['url'], path, package['sha256'])
        subprocess.run(['dpkg-deb', '-x', str(path), str(root)], check=True)
    bindir = out/'bin'
    bindir.mkdir(exist_ok=True)
    libraries = str(root/'usr/lib/x86_64-linux-gnu')+':'+str(root/'opt/or-tools/lib')
    for tool in ['openroad', 'sta']:
        wrapper = bindir/tool
        wrapper.write_text('#!/bin/sh\nexport LD_LIBRARY_PATH='+shlex.quote(libraries)
                           +'${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}\nexec '
                           +shlex.quote(str(root/'usr/bin'/tool))+' "$@"\n')
        wrapper.chmod(0o755)
    version = subprocess.check_output([str(bindir/'openroad'), '-version'], text=True).strip()
    if version != lock['openroad_version']:
        raise ValueError('unexpected OpenROAD version: '+version)
    print(bindir)


if __name__ == '__main__':
    main()
