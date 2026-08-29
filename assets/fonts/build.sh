#!/usr/bin/env bash
#
# Builds the three self-hosted webfonts in assets/fonts/ from the variable TTF
# sources in google/fonts, pinned to the commits listed below.
#
#   bash assets/fonts/build.sh              build and install into assets/fonts/
#   bash assets/fonts/build.sh --print-sums download the sources, print their
#                                          SHA-256 and exit without building
#
# Everything happens in a temp directory; the output files are copied into
# assets/fonts/ only after the verification at the end passes. See README.md
# for provenance, licensing and the update routine.

set -Eeuo pipefail

FONTTOOLS_VERSION=4.63.0
BROTLI_VERSION=1.2.0

# The exact latin subset Google Fonts serves the landing page today.
UNICODES='U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD'
# Copyright (0), trademark (7) and license (13, 14) travel with the fonts.
NAME_IDS=0,1,2,3,4,5,6,7,13,14,16,17

# Fixed build timestamp, so two runs produce byte-identical files.
export SOURCE_DATE_EPOCH=0

# out name | google/fonts dir | TTF file | commit | TTF SHA-256 | OFL SHA-256 | rename pairs | version
FAMILIES=(
  'klartex-serif|sourceserif4|SourceSerif4[opsz,wght].ttf|08dc85da6bca7ae308a6f1d38d0b137465646071|97b2d4da6e3cb494b5a1e66ae176914d852ccabef49e0c02c0df25f3e39aca0b|5f94c3fd3a23131a417ab5a0c8452de57e70c3cfb9f604d88241f7065ebf9fd9|Source Serif 4=Klartex Serif;SourceSerif4=KlartexSerif|4.004'
  'klartex-sans|sourcesans3|SourceSans3[wght].ttf|914ec116571b1162d886aa402e715552221f0b77|042fe2cc0b933e328410d7acbd0aa6a1873dca5aef81875f4bc214b08825c7b9|09746787287a289323b0ec3cff4d1a4a801331b82b7207c1e186f5d26619a392|Source Sans 3=Klartex Sans;SourceSans3=KlartexSans|3.052'
  'jetbrains-mono|jetbrainsmono|JetBrainsMono[wght].ttf|6e4b84c976cadb3c49a40fd9a1c203e4f7fcf2da|48715a42ec242c21e9f02692891e147d022299a52e48d5e413e1a942193ffeda|b2fe5e8987594e9ffd1d2ca52a2f5d73eb8335243893c5d6254b5ad69269591d||2.211'
)

print_sums=0
case "${1:-}" in
  '') ;;
  --print-sums) print_sums=1 ;;
  *) echo "usage: $0 [--print-sums]" >&2; exit 2 ;;
esac

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out_dir="$root/assets/fonts"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

die() { echo "build.sh: $*" >&2; exit 1; }

check_sum() { # file expected_sum label
  local actual
  actual=$(shasum -a 256 "$1" | cut -d ' ' -f 1)
  [ -n "$2" ] || die "no SHA-256 recorded for $3 — run --print-sums and fill it in"
  [ "$actual" = "$2" ] || die "SHA-256 mismatch for $3: expected $2, got $actual"
}

# --- download -----------------------------------------------------------------

for family in "${FAMILIES[@]}"; do
  IFS='|' read -r name dir ttf commit ttf_sum ofl_sum renames version <<< "$family"
  url_ttf=${ttf//\[/%5B}
  url_ttf=${url_ttf//\]/%5D}
  base="https://raw.githubusercontent.com/google/fonts/$commit/ofl/$dir"

  curl -fsSL -o "$tmp/$name.src.ttf" "$base/$url_ttf" || die "could not download $ttf"
  curl -fsSL -o "$tmp/$name-OFL.txt" "$base/OFL.txt" || die "could not download OFL.txt for $dir"

  if [ "$print_sums" -eq 1 ]; then
    echo "$name  ttf  $(shasum -a 256 "$tmp/$name.src.ttf" | cut -d ' ' -f 1)"
    echo "$name  ofl  $(shasum -a 256 "$tmp/$name-OFL.txt" | cut -d ' ' -f 1)"
    continue
  fi

  check_sum "$tmp/$name.src.ttf" "$ttf_sum" "$ttf"
  check_sum "$tmp/$name-OFL.txt" "$ofl_sum" "ofl/$dir/OFL.txt"
done

if [ "$print_sums" -eq 1 ]; then
  exit 0
fi

# --- toolchain ----------------------------------------------------------------

python3 -m venv "$tmp/venv"
"$tmp/venv/bin/pip" -q install "fonttools==$FONTTOOLS_VERSION" "brotli==$BROTLI_VERSION"
py="$tmp/venv/bin/python"

# --- rename and subset --------------------------------------------------------

for family in "${FAMILIES[@]}"; do
  IFS='|' read -r name dir ttf commit ttf_sum ofl_sum renames version <<< "$family"
  echo "building $name.woff2 …"

  # The variation axes are left exactly as they come. Narrowing the weight axis
  # with varLib.instancer re-solves the variation model and shifts advance
  # widths by hundredths of a pixel, which moves every glyph after the first and
  # changes the rendering. CSS limits the usable weights instead.
  cp "$tmp/$name.src.ttf" "$tmp/$name.ttf"

  # Subsetting makes these Modified Versions under the OFL, so the derivatives
  # of the two Source families carry their own name. Copyright, trademark and
  # license records stay verbatim.
  if [ -n "$renames" ]; then
    "$py" - "$tmp/$name.ttf" "$renames" <<'PY'
import os
import sys

from fontTools.ttLib import TTFont

path, pairs = sys.argv[1], sys.argv[2]
KEEP = {0, 7, 13, 14}
subs = [pair.split("=", 1) for pair in pairs.split(";") if pair]

font = TTFont(path)
for record in font["name"].names:
    if record.nameID in KEEP:
        continue
    old = record.toUnicode()
    new = old
    for source, target in subs:
        new = new.replace(source, target)
    if new != old:
        record.string = new
font.save(path + ".renamed")
os.replace(path + ".renamed", path)
PY
  fi

  # --no-hinting drops the sources' `prep` program, which Google Fonts also
  # strips. Keeping it makes Chrome grid-fit the outlines and renders the text
  # a shade thinner than the same font served from Google.
  "$py" -m fontTools.subset "$tmp/$name.ttf" \
    --output-file="$tmp/$name.woff2" \
    --flavor=woff2 \
    --unicodes="$UNICODES" \
    --name-IDs="$NAME_IDS" \
    --no-hinting \
    --notdef-outline
done

# --- verify -------------------------------------------------------------------

"$py" - "$tmp" <<'PY'
import sys

from fontTools.ttLib import TTFont

tmp = sys.argv[1]
KEEP = {0, 7, 13, 14}
REQUIRED = "åäöÖ—·"
FORBIDDEN = "≥"
EXPECTED = {
    "klartex-serif": {
        "version": "4.004",
        "axes": {"wght": (200.0, 900.0), "opsz": (8.0, 60.0)},
        "renamed": "Source",
    },
    "klartex-sans": {
        "version": "3.052",
        "axes": {"wght": (200.0, 900.0)},
        "renamed": "Source",
    },
    "jetbrains-mono": {
        "version": "2.211",
        "axes": {"wght": (100.0, 800.0)},
        "renamed": None,
    },
}

failures = []
for name, expected in EXPECTED.items():
    path = f"{tmp}/{name}.woff2"
    font = TTFont(path)
    fail = failures.append

    axes = {a.axisTag: (a.minValue, a.maxValue) for a in font["fvar"].axes}
    if axes != expected["axes"]:
        fail(f"{name}: axes {axes} != {expected['axes']}")

    cmap = set(font.getBestCmap())
    missing = [c for c in REQUIRED if ord(c) not in cmap]
    if missing:
        fail(f"{name}: cmap is missing {''.join(missing)}")
    present = [c for c in FORBIDDEN if ord(c) in cmap]
    if present:
        fail(f"{name}: cmap has {''.join(present)}, which is outside Google's latin subset")

    hinting = sorted({"prep", "fpgm", "cvt "} & set(font.keys()))
    if hinting:
        fail(f"{name}: hinting tables {hinting} are still in the file")

    names = font["name"]
    for name_id in (0, 13, 14):
        if names.getDebugName(name_id) is None:
            fail(f"{name}: name ID {name_id} is gone")
    version = names.getDebugName(5) or ""
    if expected["version"] not in version:
        fail(f"{name}: version {version!r} does not carry {expected['version']}")

    reserved = expected["renamed"]
    if reserved:
        leaked = sorted(
            {r.nameID for r in names.names if r.nameID not in KEEP and reserved in r.toUnicode()}
        )
        if leaked:
            fail(f"{name}: reserved font name {reserved!r} still in name IDs {leaked}")

    size = len(open(path, "rb").read())
    print(f"  {name}.woff2  {size:>7} bytes  {names.getDebugName(1)}  {version}")

if failures:
    print("\n".join(f"FAIL {f}" for f in failures), file=sys.stderr)
    sys.exit(1)
PY

# --- install ------------------------------------------------------------------

mkdir -p "$out_dir"
for family in "${FAMILIES[@]}"; do
  IFS='|' read -r name dir ttf commit ttf_sum ofl_sum renames version <<< "$family"
  cp "$tmp/$name.woff2" "$out_dir/$name.woff2"
  cp "$tmp/$name-OFL.txt" "$out_dir/$name-OFL.txt"
done

echo "installed in $out_dir"
