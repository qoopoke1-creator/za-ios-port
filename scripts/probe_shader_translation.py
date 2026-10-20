#!/usr/bin/env python3
"""Try one shader per stage with the unchanged bundled .NET translator."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('packages', type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--all', action='store_true', help='translate all records in bounded batches')
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    if out == repo or repo in out.parents:
        ap.error('Output must be outside repository')
    out.mkdir(parents=True, exist_ok=True)
    dll = repo / 'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate.dll'
    lock = dict(line.split('\t', 1) for line in (repo / 'dm/gfx/tools/dmsh_chain.lock').read_text().splitlines() if line and not line.startswith('#'))
    for name in ('dmsh_xlate.dll', 'Ryujinx.Graphics.Shader.dll', 'Ryujinx.Common.dll'):
        if hashlib.sha256((dll.parent / name).read_bytes()).hexdigest()[:16] != lock[name]:
            raise ValueError(f'Bundled DLL differs from lock: {name}')
    with (args.packages / 'shader_map.tsv').open(encoding='utf-8') as f:
        rows = list(csv.DictReader((s for s in f if not s.startswith('#')), delimiter='\t'))
    facts = {}
    for line in (args.packages / 'shader_facts.tsv').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#'):
            k, value = line.split('\t')
            facts[k] = json.loads(value)
    jobs = []
    cached = {}
    selected = rows if args.all else [next(r for r in rows if r['stage'] == stage) for stage in ('vertex', 'pixel', 'compute')]
    for row in selected:
        short = {'vertex': 'vs', 'pixel': 'ps', 'compute': 'cs'}[row['stage']]
        name = row['package']
        if name not in cached:
            data = (args.packages / 'pkg' / name).read_bytes()
            offsets, offset = [], 0
            while offset < len(data):
                offsets.append(offset)
                nt, nc = struct.unpack_from('<II', data, offset + 0x28)
                offset += 0x38 + nt + nc
            cached[name] = data, offsets
        data, offsets = cached[name]
        offset = offsets[int(row['index'])]
        nt, nc = struct.unpack_from('<II', data, offset + 0x28)
        code = data[offset + 0x38:offset + 0x38 + nc]
        ctl = data[offset + 0x38 + nc:offset + 0x38 + nc + nt]
        c1o, c1t = struct.unpack_from('<II', ctl, 0x700)
        if not 0 <= c1o <= c1t <= len(code):
            raise ValueError('Invalid constant segment range')
        c1 = code[c1o:c1t]
        if short != 'cs':
            code = code[0x30:]
        elif code[:4] == bytes.fromhex('79563412'):
            if any(code[0x30:0x100]):
                raise ValueError('Compute header padding mismatch')
            code = code[0x100:]
        key = row['dm_ctl_sha16']
        path = out / f'{key}.bin'
        path.write_bytes(code)
        job = dict(key=key, stage=short, code=str(path), tex={}, img={}, attr={}, fout={}, c1=c1.hex(), debug=True, reduced=True)
        job.update(facts.get(key, {}))
        jobs.append(job)
    status = 0
    for start in range(0, len(jobs), 128):
        jp = out / f'jobs-{start:05d}.json'
        batch = jobs[start:start + 128]
        jp.write_text(json.dumps(batch), encoding='utf-8')
        pending = [j for j in batch if not (out / (j['key'] + '.spv')).is_file()]
        if not pending:
            continue
        jp.write_text(json.dumps(pending), encoding='utf-8')
        with (out / f'translation-{start:05d}.log').open('w', encoding='utf-8') as log:
            proc = subprocess.run(['dotnet', str(dll), str(jp), str(out)], stdout=log, stderr=subprocess.STDOUT,
                                  env=dict(os.environ, DOTNET_NOLOGO='1'), timeout=180)
        status = max(status, int(proc.returncode != 0))
        print(f'Batch {start // 128 + 1}: {len(batch)} jobs, exit {proc.returncode}', flush=True)
    result = {'exit_code': status, 'dlls_match_lock': True, 'samples': []}
    for job in jobs:
        spv = out / (job['key'] + '.spv')
        valid = spv.is_file() and spv.stat().st_size >= 20 and spv.read_bytes()[:4] == bytes.fromhex('03022307')
        result['samples'].append({'key': job['key'], 'stage': job['stage'], 'spirv_header_valid': valid})
    (out / 'probe_result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'jobs': len(jobs), 'valid_spirv_headers': sum(s['spirv_header_valid'] for s in result['samples']), 'exit_code': status}, indent=2))


if __name__ == '__main__':
    main()
