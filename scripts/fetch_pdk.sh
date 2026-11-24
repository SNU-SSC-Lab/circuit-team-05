#!/usr/bin/env bash
# The 4th-run PDK (verification/pdk/pdk.toml) for GitHub-hosted runners, from the public copy in the ETRI050 kit repository
# (GoodKook/ETRI-0.5um-CMOS-MPW-Std-Cell-DK, byte-identical to the ZIP the teams were handed).
# Pinned to a commit and checked against SHA-256; only the digital standard-cell part is unpacked.
#   bash scripts/fetch_pdk.sh <dir>     then SSC_PDK=<dir>
# Ported from SNU-SSC-Lab/circuit-integration harness/fetch_pdk.sh at 60c7acc. SPEC 0015.
set -euo pipefail
dest="${1:?destination directory}"
url="https://raw.githubusercontent.com/GoodKook/ETRI-0.5um-CMOS-MPW-Std-Cell-DK/11f1218feaa245fa7fb7c8dafa440e54543c63b4/docs/ETRI_0p5um_NSPL_260820/NSPL_05CMOS_PDK_260820.tar.gz"
sha256="2e49115a08f6af96c1f8433130ad4316551b5eba9001a3133905b544166af954"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL --retry 3 -o "$tmp/pdk.tar.gz" "$url"
echo "$sha256  $tmp/pdk.tar.gz" | sha256sum -c --quiet
mkdir -p "$dest"
tar -xzf "$tmp/pdk.tar.gz" -C "$dest" --no-same-owner --no-same-permissions \
  NSPL_05CMOS_PDK_260820/NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T_PnR
echo "PDK digital kit in $dest"
