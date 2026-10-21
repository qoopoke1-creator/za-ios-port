#!/usr/bin/env python3
"""Merge real local RomFS into an unsigned cloud-built IPA, preserving ZIP modes."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import stat
import zipfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('skeleton', type=Path)
    ap.add_argument('romfs', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists():
        ap.error('Output already exists; choose a new filename')
    with zipfile.ZipFile(args.skeleton) as source:
        plists = [n for n in source.namelist() if n.count('/') == 2 and n.endswith('.app/Info.plist')]
        if len(plists) != 1:
            raise ValueError('Expected one root application Info.plist')
        base = plists[0].rsplit('/', 1)[0]
        plist = plistlib.loads(source.read(plists[0]))
        executable = base + '/' + plist['CFBundleExecutable']
        if executable not in source.namelist() or source.getinfo(executable).file_size < 1024:
            raise ValueError('Application executable missing or too small')
        real_marker = args.romfs / 'arc/data.trpfs'
        if not real_marker.is_file() or real_marker.stat().st_size < 1024:
            raise ValueError('Real game archive missing')
        partial = out.with_suffix('.ipa.partial')
        written = 0
        with zipfile.ZipFile(partial, 'w', allowZip64=True) as target:
            for entry in source.infolist():
                if entry.filename.startswith(base + '/romfs/') or entry.filename.startswith(base + '/_CodeSignature/') or entry.filename == base + '/embedded.mobileprovision':
                    continue
                # Existing Unix permissions and symbolic-link attributes stay intact.
                with source.open(entry) as src, target.open(entry, 'w', force_zip64=entry.file_size >= 2**31) as dst:
                    while data := src.read(4 * 2**20):
                        dst.write(data)
            for path in sorted(args.romfs.rglob('*')):
                if not path.is_file():
                    continue
                arc = base + '/romfs/' + path.relative_to(args.romfs).as_posix()
                entry = zipfile.ZipInfo.from_file(path, arc)
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | 0o644) << 16
                entry.compress_type = zipfile.ZIP_STORED
                with path.open('rb') as src, target.open(entry, 'w', force_zip64=path.stat().st_size >= 2**31) as dst:
                    while data := src.read(4 * 2**20):
                        dst.write(data)
                written += 1
        with zipfile.ZipFile(partial) as result:
            bad = result.testzip()
            if bad:
                raise ValueError(f'IPA CRC check failed: {bad}')
            if result.getinfo(base + '/romfs/arc/data.trpfs').file_size != real_marker.stat().st_size:
                raise ValueError('RomFS marker size mismatch')
            if not ((result.getinfo(executable).external_attr >> 16) & 0o111):
                raise ValueError('Executable mode lost')
        partial.replace(out)
    digest = hashlib.sha256()
    with out.open('rb') as f:
        while data := f.read(8 * 2**20):
            digest.update(data)
    report = {'ipa': out.name, 'bytes': out.stat().st_size, 'sha256': digest.hexdigest(),
              'bundle_id': plist['CFBundleIdentifier'], 'version': plist.get('CFBundleShortVersionString'),
              'minimum_os': plist.get('MinimumOSVersion'), 'romfs_files': written,
              'unsigned': True, 'runtime_tested': False,
              'limitations': 'Experimental profile and selective shader coverage; not proven to boot or play.'}
    out.with_suffix('.manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
