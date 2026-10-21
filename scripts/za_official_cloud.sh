#!/bin/bash
set -euo pipefail
export ZA_WORK="$RUNNER_TEMP/za-official"
mkdir -p "$ZA_WORK/input" "$ZA_WORK/result" "$ZA_WORK/tmp"
finish() {
  code=$?
  trap - EXIT
  echo "$code" > "$ZA_WORK/result/exit-code.txt"
  tar -czf "$ZA_WORK/result.tar.gz" -C "$ZA_WORK/result" .
  curl --fail --silent --show-error --retry 3 -H "Authorization: Bearer $BRIDGE_TOKEN" --upload-file "$ZA_WORK/result.tar.gz" "$BRIDGE_URL/output" >/dev/null || code=1
  exit "$code"
}
trap finish EXIT
curl --fail --silent --show-error --retry 3 -H "Authorization: Bearer $BRIDGE_TOKEN" "$BRIDGE_URL/input" -o "$ZA_WORK/input.tar.gz"
echo "$INPUT_SHA256  $ZA_WORK/input.tar.gz" | shasum -a 256 -c - >/dev/null
tar -xzf "$ZA_WORK/input.tar.gz" -C "$ZA_WORK/input"
rm "$ZA_WORK/input.tar.gz"
cat > dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate <<'SH'
#!/bin/bash
exec dotnet "$(dirname "$0")/dmsh_xlate.dll" "$@"
SH
chmod +x dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate
python3 scripts/za_official_cloud.py > "$ZA_WORK/result/build.log" 2>&1
