"""Upload this repository's source or download compact reports only."""
import argparse
import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
remote = '/home/ubuntu/jianzheli/University/conginitve_reasoning/civrealm-agent-study'
parser = argparse.ArgumentParser()
parser.add_argument('direction', choices=['push', 'pull'])
args = parser.parse_args()
if args.direction == 'pull':
    for directory in ['development','archive']:
        (root/'reports'/directory).mkdir(parents=True,exist_ok=True)
        subprocess.run(['rsync', '-az', '--delete', '--exclude=*.mp4', '--exclude=*.webm',
                        'msfm:' + remote + '/reports/' + directory + '/', str(root/'reports'/directory) + '/'], check=True)
else:
    subprocess.run(['ssh', 'msfm', 'mkdir -p ' + shlex.quote(remote)], check=True)
    command = ['rsync', '-az', '--exclude=__pycache__/', '--exclude=*.pyc']
    for entry in ['AGENTS.md', 'README.md', 'CONTRIBUTING.md', '.gitignore', 'requirements.txt', 'pyproject.toml']:
        command += ['--include=/' + entry]
    for entry in ['src', 'scripts', 'configs', 'prompts', 'docs', 'tests']:
        command += ['--include=/' + entry + '/***']
    command += ['--exclude=*', str(root) + '/', 'msfm:' + remote + '/']
    subprocess.run(command, check=True)
    revision = {
        'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'working_tree_status': subprocess.check_output(['git', 'status', '--short'], cwd=root, text=True).splitlines(),
        'deployed_at': datetime.now(timezone.utc).isoformat(),
    }
    subprocess.run(['ssh', '-T', 'msfm', 'python3 ' + shlex.quote(remote + '/scripts/bootstrap_remote.py')],
                   input=json.dumps(revision), text=True, check=True)
