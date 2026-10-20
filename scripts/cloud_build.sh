#!/bin/bash
# Resource-light build: never upload game-derived files as public artifacts.
set -euo pipefail
ROOT=$PWD
W="$RUNNER_TEMP/za-work"
mkdir -p "$W/input" "$W/result" "$W/tmp"
report() { echo "$*"; }
finish() {
  code=$?
  trap - EXIT
  echo "$code" > "$W/result/exit-code.txt"
  cp "$ROOT/dm/gfx/tools/dmsh_chain.lock" "$W/result/actual-chain.lock" 2>/dev/null || true
  tar -czf "$W/result.tar.gz" -C "$W/result" .
  curl --fail --silent --show-error --retry 3 -H "Authorization: Bearer $BRIDGE_TOKEN" \
    --upload-file "$W/result.tar.gz" "$BRIDGE_URL/output" > /dev/null || code=1
  exit "$code"
}
trap finish EXIT
report 'Downloading authenticated private build input'
curl --fail --silent --show-error --retry 3 -H "Authorization: Bearer $BRIDGE_TOKEN" "$BRIDGE_URL/input" -o "$W/input.tar.gz"
echo "$INPUT_SHA256  $W/input.tar.gz" | shasum -a 256 -c - > /dev/null
tar -xzf "$W/input.tar.gz" -C "$W/input"
export GAME=0100F43008C44000 DM_GAME=0100F43008C44000 DM_GAMES_DIR="$W/input/profile"
export DM_ROOT="$W" WORK="$W/tmp" J=3 IOSOUT="$W/ios-shaders"
export PATCHED="$W/input/patched" ROMFS="$W/input/RomFS" MSL_IOS="$W/ios-shaders"
export AOC='' DM_DISPLAY_NAME='Pokemon Legends Z-A Experimental' DM_APP_VERSION=2.0.2
export DM_ICON="$W/input/icon.jpg" PYTHONUTF8=1
GD="$W/input/profile/$GAME"
mkdir -p "$ROMFS/arc"
# Build-time marker only; the real RomFS is merged locally after compilation.
touch "$ROMFS/arc/data.trpfs"
report 'Recording actual toolchain and generating chain header'
python3 dm/gfx/tools/dmsh_chain.py --update-lock > "$W/result/chain.log" 2>&1
python3 dm/gfx/tools/dmsh_chain.py --header >> "$W/result/chain.log" 2>&1
cp "$GD/dmsh_chain.h" "$W/result/"
report 'Building shader libraries for macOS and iOS'
python3 dm/gfx/tools/dmsh_build.py "$W/input/pkg" "$W/cache" > "$W/result/shaders.log" 2>&1
python3 - "$W/result/shaders.log" <<'PY'
import re,sys
t=open(sys.argv[1]).read()
m=re.search(r'shaders (\d+): ok (\d+)',t)
if not m: raise SystemExit('Missing shader summary')
print(m.group(0))
if m[1]!=m[2]: raise SystemExit('Shader failures require investigation; see private result logs')
PY
CHAIN=$(sed -n 's/^#define DMSH_CHAIN "\(.*\)"/\1/p' "$GD/dmsh_chain.h")
python3 dm/gfx/tools/c1_guard.py "$W/cache/b-$CHAIN" "$GD/c1_full.tsv" > "$W/result/guard.log" 2>&1
cp "$GD/c1_full.tsv" "$W/result/"
report 'Building unsigned iOS application'
GAME="$GAME" W="$W" bash dm/ios/tools/build_ipa.sh "$W/result/app-skeleton.ipa" > "$W/result/app.log" 2>&1 || {
  cp "$W/build/ios/pkg/build.log" "$W/result/xcode.log" 2>/dev/null || true
  exit 1
}
cp "$W/build/ios/pkg/build.log" "$W/result/xcode.log"
report 'Unsigned app skeleton built; real game resources must be merged locally'
