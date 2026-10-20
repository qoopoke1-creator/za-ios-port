#!/usr/bin/env python3
"""Stop the processes started for this build and remove temporary repository secrets."""
import json
from pathlib import Path
import signal
import subprocess
import sys

work = Path(sys.argv[1]).resolve()
state = json.loads((work / 'bridge-processes.json').read_text(encoding='utf-8'))
for name in ('server_pid', 'tunnel_pid'):
    try:
        import os
        os.kill(state[name], signal.SIGTERM)
    except ProcessLookupError:
        pass
for name in ('ZA_BRIDGE_URL', 'ZA_BRIDGE_TOKEN', 'ZA_INPUT_SHA256'):
    subprocess.run(['gh', 'secret', 'delete', name, '--repo', 'qoopoke1-creator/za-ios-port'], check=True)
# Retain the record, but remove the credential from its local configuration.
p = work / 'bridge-config.json'
config = json.loads(p.read_text(encoding='utf-8'))
config['token'] = 'REMOVED_AFTER_BUILD'
p.write_text(json.dumps(config), encoding='utf-8')
print('Build bridge stopped and temporary repository secrets removed.')
