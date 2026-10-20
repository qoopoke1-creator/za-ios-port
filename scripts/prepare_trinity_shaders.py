#!/usr/bin/env python3
"""Package locally decoded Trinity candidates with the upstream shader splitter.

This creates a shader-analysis profile, not a bootable game profile. Game-derived
outputs must stay outside the repository. No compiler or platform build is run.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def validate(root):
    with (root / 'shader_map.tsv').open(encoding='utf-8') as f:
        rows = list(csv.DictReader((s for s in f if not s.startswith('#')), delimiter='\t'))
    if not rows:
        raise ValueError('No shader records generated')
    keys = {r['dm_ctl_sha16'] for r in rows}
    if len(keys) != len(rows):
        raise ValueError('Duplicate shader keys')
    stages = Counter(r['stage'] for r in rows)
    facts = {}
    for line in (root / 'shader_facts.tsv').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#'):
            key, data = line.split('\t', 1)
            facts[key] = json.loads(data)
    compute = {r['dm_ctl_sha16'] for r in rows if r['stage'] == 'compute'}
    if set(facts) != compute:
        raise ValueError('Compute facts coverage mismatch')
    vertex = {r['dm_ctl_sha16'] for r in rows if r['stage'] == 'vertex'}
    pixel = {r['dm_ctl_sha16'] for r in rows if r['stage'] == 'pixel'}
    pairs = set()
    for line in (root / 'shader_pairs.tsv').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#'):
            a, b = line.split('\t')
            if a not in vertex or b not in pixel:
                raise ValueError('Pair refers to missing or wrong-stage shader')
            pairs.add((a, b))
    manifest = {}
    import struct
    for name in sorted({r['package'] for r in rows}):
        data = (root / 'pkg' / name).read_bytes()
        offset = 0
        records = []
        while offset < len(data):
            if data[offset:offset + 8] != b'BTCDBTCD':
                raise ValueError('Invalid package record separator')
            nt, nc = struct.unpack_from('<II', data, offset + 0x28)
            end = offset + 0x38 + nc + nt
            if end > len(data) or nt < 0x760:
                raise ValueError('Invalid package record bounds')
            code = data[offset + 0x38:offset + 0x38 + nc]
            ctl = data[offset + 0x38 + nc:end]
            own = struct.unpack_from('<I', ctl, 0x20)[0]
            hashed_size = own if 0x760 <= own < 0x880 else 0x880
            records.append(hashlib.sha256(ctl[:hashed_size] + code).hexdigest()[:16])
            offset = end
        selected = sorted((r for r in rows if r['package'] == name), key=lambda r: int(r['index']))
        if [r['dm_ctl_sha16'] for r in selected] != records:
            raise ValueError('Package record content does not match map')
        manifest[name] = {'records': len(records), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return {'unique_shaders': len(rows), 'stages': dict(stages), 'compute_facts': len(facts),
            'variation_pairs': len(pairs), 'packages': manifest,
            'limitations': ['Selective Trinity candidates plus embedded main scan; not full coverage.',
                            'No translation, chain header, GPU test or runtime-ready profile.']}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('decoded', type=Path)
    ap.add_argument('main_nso', type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=2)
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    if out == repo or repo in out.parents or not 1 <= args.jobs <= 8:
        ap.error('Use an external output directory and 1..8 jobs')
    if not args.decoded.is_dir() or not args.main_nso.is_file():
        ap.error('Decoded directory and main NSO must exist')
    out.mkdir(parents=True, exist_ok=True)
    profile = out / 'analysis-profile'
    profile.mkdir(exist_ok=True)
    (profile / 'game.tsv').write_text(
        '# Shader analysis only; memory and driver bindings are not configured.\n'
        'shader_groups\t/=trinity\n'
        'shader_note\tZ-A 2.0.2 selectively decoded Trinity candidates\n', encoding='utf-8')
    env = dict(os.environ, DM_GAME=str(profile), J=str(args.jobs), PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    with (out / 'split.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable, str(repo / 'dm/gfx/tools/shader_split.py'),
                        str(args.decoded.resolve()), str(args.main_nso.resolve()), str(out / 'pkg'),
                        str(out / 'shader_map.tsv'), str(out / 'shader_facts.tsv'), str(out / 'shader_pairs.tsv')],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    result = validate(out)
    result['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    (out / 'package_manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
