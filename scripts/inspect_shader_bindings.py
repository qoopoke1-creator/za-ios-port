#!/usr/bin/env python3
"""Summarize translator reflection without changing binding assumptions."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
handles = Counter()
storage = defaultdict(set)
for path in root.glob('*.res.json'):
    d = json.loads(path.read_text(encoding='utf-8'))
    for item in d.get('textures', []):
        handles[str((item.get('cbuf_slot'), item.get('handle'), item.get('separate')))] += 1
    for item in d.get('sbufs', []):
        storage[d.get('stage', '?')].add((item.get('cb_slot'), item.get('cb_offset')))
result = {'texture_handles': handles.most_common(), 'storage_offsets': {k: sorted(v) for k, v in storage.items()}}
(root / 'binding_inventory.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
