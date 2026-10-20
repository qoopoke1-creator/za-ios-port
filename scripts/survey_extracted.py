#!/usr/bin/env python3
"""Survey already extracted modules without Xcode or access to game keys."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('extraction', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--rewrite', action='store_true', help='also attempt native rewriting of main and sdk')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / 'dm/games'))
    sys.path.insert(0, str(repo / 'dm/tools'))
    import profile_guess
    import nacp

    root, out = args.extraction.resolve(), args.out.resolve()
    exefs = root / 'ExeFS'
    if not exefs.is_dir() or not (root / 'romfs_manifest.tsv').is_file():
        parser.error('extraction must contain ExeFS and romfs_manifest.tsv')
    out.mkdir(parents=True, exist_ok=True)
    facts = profile_guess.facts_of(exefs, root / 'romfs_manifest.tsv')
    guesses = profile_guess.guess(facts)
    npdm = (exefs / 'main.npdm').read_bytes()
    flags = npdm[0xc] if npdm[:4] == b'META' else None
    code = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    result = {
        'source_commit': code,
        'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)),
        'name': nacp.name(root / 'control.nacp'),
        'npdm_flags': flags,
        'npdm_is_64_bit': bool(flags & 1) if flags is not None else None,
        'facts': facts,
        'guesses': guesses,
        'limitations': ['Static survey only; no host execution or GPU validation.',
                        'Manifest reads file headers, not all RomFS contents.'],
    }

    def normalize(value):
        if isinstance(value, dict):
            return {str(k): normalize(v) for k, v in value.items()}
        if isinstance(value, set):
            return sorted(value)
        if isinstance(value, (list, tuple)):
            return [normalize(v) for v in value]
        return value

    (out / 'facts.json').write_text(json.dumps(normalize(result), indent=2, ensure_ascii=True), encoding='utf-8')
    lines = ['# Extracted game static survey', '', f'- Source: `{code}`',
             f'- Source dirty: `{result["source_dirty"]}`',
             f'- NPDM 64-bit flag: `{result["npdm_is_64_bit"]}`',
             f'- Program ID: `{facts["program"]:016X}`' if facts['program'] is not None else '- Program ID: unknown',
             '- SDK: ' + ', '.join(sorted(facts['sdkver'])),
             '- Raw string markers (not engine identification): ' + ', '.join(facts['markers']), '',
             '| Module | Build ID (first 16 bytes) | Text / RO / Data MiB | BSS MiB |',
             '| --- | --- | --- | --- |']
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    for name, module in facts['mods'].items():
        sizes = ' / '.join(f'{n / 2**20:.2f}' for n in module['sizes'])
        lines.append(f'| {name} | `{module["bid"]}` | {sizes} | {module["bss"] / 2**20:.2f} |')
        if name != 'rtld':
            with (out / f'census_{name}.log').open('w', encoding='utf-8') as log:
                subprocess.run([sys.executable, str(repo / 'dm/tools/insn_census.py'), str(exefs / name)],
                               env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    with (out / 'imports.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable, str(repo / 'dm/tools/nso_syms.py'), str(repo / 'dm/host'), '-', str(exefs)],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    if args.rewrite:
        patched = out / 'patched'
        patched.mkdir(exist_ok=True)
        for name in ('main', 'sdk'):
            with (out / f'rewrite_{name}.log').open('w', encoding='utf-8') as log:
                subprocess.run([sys.executable, str(repo / 'dm/tools/patch_nso.py'), str(exefs / name), str(patched), name],
                               env=dict(env, DM_RULESET='native'), stdout=log, stderr=subprocess.STDOUT, check=True)
        lines += ['', '- Offline rewriting completed for main and sdk. This does not prove instruction equivalence or runtime correctness.']
    lines += ['', '## Provisional guesses (not validated)', '', '| Key | Value | Reason |', '| --- | --- | --- |']
    lines += [f'| {key} | `{value}` | {reason} |' for key, (value, reason) in guesses.items()]
    lines += ['', '## Limits', '', *['- ' + s for s in result['limitations']],
              '- Import differences are not all missing implementations: SDK code can execute natively.',
              '- Census and import reports are beside this file.']
    (out / 'survey.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Static survey written to {out}')


if __name__ == '__main__':
    main()
