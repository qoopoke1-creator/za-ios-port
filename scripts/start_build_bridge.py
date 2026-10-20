#!/usr/bin/env python3
"""Start the one-build bridge and configure encrypted repository secrets."""
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import hashlib

work = Path(sys.argv[1]).resolve()
repo = Path(__file__).resolve().parents[1]
config = work / 'bridge-config.json'
token = secrets.token_urlsafe(48)
archive = work / 'cloud-input.tar.gz'
config.write_text(json.dumps({'input': str(archive), 'output': str(work / 'cloud-result.tar.gz'),
                              'token': token, 'port': 18765}), encoding='utf-8')
flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
server = subprocess.Popen([sys.executable, str(repo / 'scripts/local_build_bridge.py'), str(config)], creationflags=flags)
log_path = work / 'tunnel.log'
with log_path.open('w', encoding='utf-8') as log:
    tunnel = subprocess.Popen([shutil.which('cloudflared'), 'tunnel', '--url', 'http://127.0.0.1:18765', '--no-autoupdate'],
                              stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
url = None
for _ in range(60):
    match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', log_path.read_text(encoding='utf-8', errors='replace'))
    if match:
        url = match[0]
        break
    time.sleep(1)
if not url:
    server.terminate()
    tunnel.terminate()
    raise SystemExit('Temporary tunnel did not become available; inspect local tunnel.log')
for name, value in {'ZA_BRIDGE_URL': url, 'ZA_BRIDGE_TOKEN': token,
                    'ZA_INPUT_SHA256': hashlib.sha256(archive.read_bytes()).hexdigest()}.items():
    subprocess.run(['gh', 'secret', 'set', name, '--repo', 'qoopoke1-creator/za-ios-port'], input=value, text=True, check=True)
(work / 'bridge-processes.json').write_text(json.dumps({'server_pid': server.pid, 'tunnel_pid': tunnel.pid}), encoding='utf-8')
print('Bridge started; URL and token configured as repository secrets without console output.')
