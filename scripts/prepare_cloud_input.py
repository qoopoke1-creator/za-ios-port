#!/usr/bin/env python3
"""Prepare a private, resource-light diagnostic build input outside this repository."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('work', type=Path)
    args = ap.parse_args()
    work = args.work.resolve()
    repo = Path(__file__).resolve().parents[1]
    if work == repo or repo in work.parents:
        ap.error('Work directory must be outside repository')
    stage = work / 'cloud-input'
    stage.mkdir(exist_ok=True)
    profile = stage / 'profile' / '0100F43008C44000'
    profile.mkdir(parents=True, exist_ok=True)
    shaders = work / 'shader-v393216'
    for name in ('shader_map.tsv', 'shader_facts.tsv', 'shader_pairs.tsv'):
        shutil.copy2(shaders / name, profile / name)
    for name in ('shader_map.tsv.conflicts.tsv', 'pso_manifest.tsv', 'bf_want.tsv'):
        (profile / name).write_text('# Empty diagnostic table.\n', encoding='utf-8')
    rows = {
        'title_id': '0100F43008C44000', 'program_id': '0100F43008C44000',
        'name': 'Pokemon Legends Z-A (experimental)', 'ipa': 'PokemonZA-experimental.ipa',
        'app_category': 'public.app-category.games', 'package': 'v393216',
        'shader_versions': 'v393216', 'modules': 'main sdk', 'romfs_marker': 'arc/data.trpfs',
        'zip_store': '.trpfs:.trpfd:.pck:.bnk:.metallib', 'pad_layout': 'full',
        'mem_reserve': '0x100000000', 'mem_alias': '0x80000000', 'mem_stack': '0x10000000',
        'app_pool': '0xCD500000', 'mem_used': '0x7000000',
        'nvn_tex_base': '0x20', 'nvn_tex_slots': '32', 'nvn_samp_base': '0x568',
        'nvn_img_base': '0x120', 'nvn_img_slots': '8',
        'nvn_ssbo_bases': 'vs=0x110 ps=0x510 cs=0x310',
        'shader_groups': '/=trinity', 'shader_note': 'Z-A 2.0.2 selectively decoded Trinity candidates',
    }
    text = '# Experimental build profile, NOT runtime validated.\n# Texture/storage bases follow static reflection; image/sampler settings and memory layout are provisional.\n'
    text += ''.join(f'{k}\t{v}\n' for k, v in rows.items())
    text += 'build\tv393216\t2.0.2\tmain=b1f12fd919eae86ab8a978317677e64b\tsdk=df7a3960c74c3a4803f826c587153252\n'
    (profile / 'game.tsv').write_text(text, encoding='utf-8')
    shutil.copytree(shaders / 'pkg', stage / 'pkg', dirs_exist_ok=True)
    shutil.copytree(work / 'survey-v393216/analysis/patched', stage / 'patched', dirs_exist_ok=True)
    for name in ('icon.jpg', 'control.nacp'):
        shutil.copy2(work / 'survey-v393216/extract' / name, stage / name)
    archive = work / 'cloud-input.tar.gz'
    with tarfile.open(archive, 'w:gz', compresslevel=1) as tf:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                tf.add(path, arcname=path.relative_to(stage).as_posix())
    print(json.dumps({'archive_bytes': archive.stat().st_size,
                      'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
