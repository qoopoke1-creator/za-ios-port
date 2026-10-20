#!/bin/bash
# Private startup/input probe. No game-derived logs or frames are printed publicly.
set -euo pipefail
ROOT=$PWD
W="$RUNNER_TEMP/za-runtime"
mkdir -p "$W/input" "$W/result" "$W/save" "$W/temp" "$W/msl"
finish() {
  code=$?
  trap - EXIT
  echo "$code" > "$W/result/wrapper-exit.txt"
  tar -czf "$W/result.tar.gz" -C "$W/result" .
  curl --fail --silent --show-error --retry 3 -H "Authorization: Bearer $BRIDGE_TOKEN" \
    --upload-file "$W/result.tar.gz" "$BRIDGE_URL/output" >/dev/null || code=1
  exit "$code"
}
trap finish EXIT
curl --fail --silent --show-error --retry 3 -H "Authorization: Bearer $BRIDGE_TOKEN" "$BRIDGE_URL/input" -o "$W/input.tar.gz"
echo "$INPUT_SHA256  $W/input.tar.gz" | shasum -a 256 -c - >/dev/null
tar -xzf "$W/input.tar.gz" -C "$W/input"
export GAME=0100F43008C44000 DM_GAME=0100F43008C44000 DM_GAMES_DIR="$W/input/profile"
GD="$W/input/profile/$GAME"
# Startup probe uses the exact generated chain header from the IPA build.
cp "$W/input/dmsh_chain.h" "$GD/dmsh_chain.h"
make -C dm/host GAME="$GAME" > "$W/result/host-build.log" 2>&1
codesign --force --sign - --entitlements "$W/input/runtime.entitlements" dm/host/dmhost > "$W/result/sign.log" 2>&1
export DM_ROOT="$W" DM_ROMFS="$W/input/RomFS" DM_SAVE="$W/save" DM_TEMP="$W/temp"
export DM_MSL_DIR="$W/msl" DM_NVN_SHMAP="$GD/shader_map.tsv" DM_FONT_DIR='/System/Library/Fonts/Supplemental'
export DM_LANG=zh-Hans DM_KBD=Player DM_OPMODE=0
export DM_KEYS='10:A,15:A,20:A,25:A,35:A,45:A,55:A,65:LUp~2,70:RRight~2,75:LRight~2'
export DM_NVN_SHOT="1,30,60,120,300,600,900,1200:$W/result/frame_%d.png"
python3 - "$ROOT/dm/host/dmhost" "$W" <<'PY'
import os,pathlib,subprocess,sys,json,time
w=pathlib.Path(sys.argv[2]); t=time.monotonic()
with (w/'result/runtime.log').open('w') as log:
 p=subprocess.Popen([sys.argv[1],str(w/'input/patched')],stdout=log,stderr=subprocess.STDOUT,env=os.environ)
 timed_out=False
 try: rc=p.wait(timeout=90)
 except subprocess.TimeoutExpired:
  timed_out=True; p.terminate()
  try: rc=p.wait(timeout=10)
  except subprocess.TimeoutExpired: p.kill(); rc=p.wait()
(w/'result/runtime-status.json').write_text(json.dumps({'exit_code':rc,'timeout':timed_out,'seconds':time.monotonic()-t,'shader_libraries':'not loaded in this startup probe','save':'fresh isolated save'}))
PY
echo 'Startup probe completed. Private logs returned; movement is not inferred from scripted input alone.'
