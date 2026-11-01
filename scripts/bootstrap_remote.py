"""Copy an independent SDK; never modify the previous project's files."""
import json
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
old = root.parent / 'civilization'
sdk = root / 'third_party/civrealm'
sdk.parent.mkdir(parents=True, exist_ok=True)
if not sdk.exists():
    shutil.copytree(old / 'third_party/civrealm', sdk,
                    ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '.pytest_cache'))
p = sdk / 'src/civrealm/envs/freeciv_minitask_env.py'
text = p.read_text()
old_cap = '''        if self._course_steps >= 128 and not terminated:
            truncated = True
            info["course_action_limit"] = True
'''
if old_cap in text:
    p.write_text(text.replace(old_cap, ''))
elif 'self._course_steps >= 128' in text:
    raise RuntimeError('Unexpected old action cap; inspect the independent SDK before collecting')
p = sdk / 'src/civrealm/freeciv/utils/port_utils.py'
p.write_text(p.read_text().replace('os.environ["CIVCOURSE_ROOT"]', 'os.environ["CIVSTUDY_ROOT"]'))
p = sdk / 'src/civrealm/freeciv/civ_controller.py'
# The runner consumes this list with a cumulative cursor. Native turn_messages
# is separate; retaining these player notifications does not change game rules.
p.write_text(p.read_text().replace('        self.messages.clear()',
                                 '        # Retain player notifications for the trajectory cursor.'))
for name in ['runtime', 'runs', 'cache', 'tmp']:
    (root / name).mkdir(exist_ok=True)
revision = json.load(sys.stdin)
revision['sdk'] = {
    'upstream': '1b144d6ec92a8aaa8e30eee64c881418208a4689',
    'path': str(sdk), 'source': str(old / 'third_party/civrealm'),
    'changes': ['Removed inherited course 128-action truncation',
                'Moved port coordination files to CIVSTUDY_ROOT/tmp',
                'Retained existing WebSocket socket/event-loop close fix',
                'Retained player notification list across turns for the cumulative event cursor',
                'Other inherited course patches remain in the independent snapshot; RL modules are unused'],
}
(root / 'runtime/source_revision.json').write_text(json.dumps(revision, ensure_ascii=False, indent=2))
print('READY', root, 'independent SDK:', sdk)
