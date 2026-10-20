#!/usr/bin/env python3
"""Prepare full local resources for an isolated private Mac startup probe."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile

work = Path(sys.argv[1]).resolve()
stage = work / 'cloud-input'
(stage / 'runtime.entitlements').write_text('''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>com.apple.security.cs.allow-jit</key><true/>
<key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/></dict></plist>
''', encoding='utf-8')
archive = work / 'cloud-input.tar.gz'
with tarfile.open(archive, 'w:gz', compresslevel=1) as tf:
    for path in sorted(stage.rglob('*')):
        if path.is_file(): tf.add(path, arcname=path.relative_to(stage).as_posix())
    tf.add(work / 'cloud-result/dmsh_chain.h', arcname='dmsh_chain.h')
    tf.add(work / 'data/v393216/RomFS', arcname='RomFS')
digest = hashlib.sha256()
with archive.open('rb') as f:
    while data := f.read(8 * 2**20): digest.update(data)
print(json.dumps({'bytes':archive.stat().st_size,'sha256':digest.hexdigest()}))
