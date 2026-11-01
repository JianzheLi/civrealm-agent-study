"""Pass a key over SSH stdin. The macOS dialog is hidden and never logged."""
import argparse
import getpass
import json
import os
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--macos-dialog', action='store_true')
args = parser.parse_args()
key = os.environ.get('DEEPSEEK_API_KEY')
if not key:
    if args.macos_dialog:
        dialog = 'text returned of (display dialog "输入 DeepSeek API Key，用于两个发展任务各 100 局。密钥只传入服务器进程，不保存到文件。" default answer "" with hidden answer buttons {"取消", "开始采集"} default button "开始采集" with title "CivRealm 首轮采集" giving up after 600)'
        reply = subprocess.run(['osascript', '-e', dialog], capture_output=True, text=True)
        if reply.returncode:
            raise SystemExit('Credential input cancelled; collection was not started.')
        key = reply.stdout.strip()
    else:
        key = getpass.getpass('DeepSeek API key (hidden, not saved): ')
if not key:
    raise SystemExit('No credential supplied; collection was not started.')
subprocess.run(['ssh', '-T', 'msfm', 'python3 /home/ubuntu/jianzheli/University/conginitve_reasoning/civrealm-agent-study/scripts/receive_launch.py'],
               input=json.dumps({'key': key}), text=True, check=True)
