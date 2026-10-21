#!/usr/bin/env python3
"""Build supplied extracted Z-A data with the upstream registered profile."""
import os
import re
from pathlib import Path
import shutil
import sys
import build_ipa_from_nsp as b

repo = Path(__file__).resolve().parents[1]
w = Path(os.environ['ZA_WORK'])
sys.path.insert(0, str(repo / 'dm/games'))
import game
g = game.load('0100F43008C44000')
env = dict(os.environ, DM_GAME=g.id, GAME=g.id, DM_ROOT=str(w), WORK=str(w / 'tmp'), J='3')
logs = w / 'result/logs'
logs.mkdir(parents=True, exist_ok=True)
ex = w / 'input/extract'
b.check_build(ex, 'v393216', g)
py = sys.executable
patched = w / 'patched'
b.rewrite(py, repo, ex / 'ExeFS', patched, env, logs, g)
b.run([py, repo / 'dm/gfx/tools/dmsh_chain.py', '--update-lock'], logs / 'chain-lock.log', env=env)
b.run([py, repo / 'dm/gfx/tools/dmsh_chain.py', '--header'], logs / 'chain-header.log', env=env)
sh = w / 'shader'
oodle = lambda: {'DM_OODLE_HOST': str(b.build_mac_host(repo, w / 'tools/dmhost', env, logs, g)), 'DM_OODLE_MODULES': str(patched)}
key = b.split_shaders(py, repo, [ex / 'RomFS'], [ex / 'ExeFS/main'], sh / 'pkg', env, logs, g, False, oodle)
ios = b.build_shaders(py, repo, sh, repo / 'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate', env, logs, g, False, key)
summary = re.search(r'shaders (\d+): ok (\d+)', (logs / 'dmsh_build.log').read_text(errors='replace'))
if not summary or summary[1] != summary[2]:
    raise RuntimeError('Shader build did not complete without failures')
chain = re.search(r'#define DMSH_CHAIN "(.*)"', g.table('dmsh_chain.h').read_text())[1]
b.run([py, repo / 'dm/gfx/tools/c1_guard.py', sh / 'cache' / f'b-{chain}', g.table('c1_full.tsv')], logs / 'c1_guard.log', env=env)
b.run([py, repo / 'dm/gfx/tools/cb_extent.py', sh / 'cache' / f'b-{chain}', g.table('cb_extent.tsv')], logs / 'cb_extent.log', env=env)
marker = w / 'marker/arc'
marker.mkdir(parents=True)
(marker / 'data.trpfs').touch()
ienv = dict(env, W=str(w / 'ipa'), PATCHED=str(patched), ROMFS=str(marker.parent), MSL_IOS=str(ios), GFXAPI='nvn', FONT_PY=py,
            DM_DISPLAY_NAME='Pokémon Legends: Z-A', DM_BUNDLE_ID='org.nxnative.0100f43008c44000', DM_APP_VERSION='2.0.2',
            DM_ICON=str(ex / 'icon.jpg'), AOC=str(w / 'input/aoc'), DM_LANG='zh-Hant', DM_SHOW_FPS='0')
b.run(['bash', repo / 'dm/ios/tools/build_ipa.sh', w / 'result/app-skeleton.ipa'], logs / 'app.log', env=ienv)
for name in ('dmsh_chain.h', 'c1_full.tsv', 'cb_extent.tsv'):
    shutil.copy2(g.table(name), w / 'result' / name)
shutil.copy2(repo / 'dm/gfx/tools/dmsh_chain.lock', w / 'result/actual-chain.lock')
