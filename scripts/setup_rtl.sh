#!/usr/bin/env bash
# Build the official, pinned Verilator release; the workflow supplies build tools.
set -euo pipefail
rtl_version=5.048
rtl_commit=d0aa828c217410fffc73d92077b6f4f54830357c
rtl_prefix="$(realpath -m "${SSC_TOOL_PREFIX:-.policy-tmp/toolchain}")/verilator-$rtl_version"
rtl_source="$(realpath -m "${SSC_TOOL_SOURCE:-.policy-tmp/tool-source}")/verilator-$rtl_version"
if [[ -x "$rtl_prefix/bin/verilator" ]] && "$rtl_prefix/bin/verilator" --version | grep -q 'Verilator 5.048 '; then
    "$rtl_prefix/bin/verilator" --version
    exit 0
fi
mkdir -p "$rtl_source"
git -C "$rtl_source" init -q
if ! git -C "$rtl_source" remote get-url origin >/dev/null 2>&1; then
    git -C "$rtl_source" remote add origin https://github.com/verilator/verilator.git
fi
git -C "$rtl_source" fetch --depth 1 origin "$rtl_commit"
git -C "$rtl_source" checkout --detach FETCH_HEAD
test "$(git -C "$rtl_source" rev-parse HEAD)" = "$rtl_commit"
cd "$rtl_source"
autoconf
./configure --prefix="$rtl_prefix"
make -j "${SSC_BUILD_JOBS:-2}"
make install
"$rtl_prefix/bin/verilator" --version
