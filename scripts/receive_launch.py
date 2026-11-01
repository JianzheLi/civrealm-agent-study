import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
request = json.load(sys.stdin)
env = os.environ.copy()
env['DEEPSEEK_API_KEY'] = request['key']
log = root / 'runtime/supervisor.log'
with log.open('a') as output:
    process = subprocess.Popen(['bash', '-c', f'source "{root}/scripts/env.sh"\nexec python -u -m civstudy.supervisor'],
                               env=env, stdin=subprocess.DEVNULL, stdout=output,
                               stderr=subprocess.STDOUT, start_new_session=True)
print('STARTED supervisor_pid', process.pid, 'log', log)
