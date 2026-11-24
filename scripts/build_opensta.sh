#!/usr/bin/env bash
# OpenSTA for GitHub-hosted runners (Ubuntu 24.04), cached by .github/workflows/pdk.yml. Pinned sources,
# ported from SNU-SSC-Lab/circuit-integration harness/build_opensta.sh at 60c7acc. SPEC 0015.
#   bash scripts/build_opensta.sh <prefix>     installs <prefix>/bin/sta
set -euo pipefail
prefix="${1:?install prefix}"
sudo apt-get install -y -qq --no-install-recommends cmake tcl-dev swig bison flex libfl-dev libeigen3-dev \
  zlib1g-dev autoconf automake libtool > /dev/null
src="$(mktemp -d)"
trap 'rm -rf "$src"' EXIT
git clone -q --depth 1 -b 3.0.0 https://github.com/The-OpenROAD-Project/cudd.git "$src/cudd"
(cd "$src/cudd" && autoreconf -fi > /dev/null 2>&1 && ./configure --prefix="$src/cudd-install" --disable-shared > /dev/null \
  && make -j"$(nproc)" > /dev/null 2>&1 && make install > /dev/null)
git clone -q https://github.com/parallaxsw/OpenSTA.git "$src/OpenSTA"
git -C "$src/OpenSTA" checkout -q 8b4cc283bea33764ba96fb935e6e2732a8708779
cmake -S "$src/OpenSTA" -B "$src/OpenSTA/build" -DCMAKE_BUILD_TYPE=Release -DCUDD_DIR="$src/cudd-install" > /dev/null
cmake --build "$src/OpenSTA/build" -j"$(nproc)" > /dev/null
install -D "$src/OpenSTA/build/sta" "$prefix/bin/sta"
"$prefix/bin/sta" -version
