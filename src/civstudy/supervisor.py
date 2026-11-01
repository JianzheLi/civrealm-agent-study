"""CPU collection workers, included first-five validation, then full collection and analysis."""
import json
import os
import subprocess
import shutil
import importlib.metadata
import sys
from .common import ROOT, load_config, now, read_jsonl, write_json


def first_five_ready(config):
    manifest = json.loads((ROOT / config['manifest']).read_text())
    folder = ROOT / 'runs' / config['run_id']
    errors = []
    for task in config['tasks']:
        decisions = 0
        for instance in manifest[task]['instance_ids'][:5]:
            results = list((folder / 'episodes' / f'{task}-normal-{instance}').glob('attempt*/result.json'))
            rows = [json.loads(p.read_text()) for p in results]
            usable = [r for r in rows if r['stop_reason'] not in {'infrastructure_error', 'interrupted', 'running'} and r.get('ended_at')]
            if not usable:
                errors.append(f'{task}/{instance}: no usable policy result')
            for p in results:
                calls = read_jsonl(p.parent / 'api_calls.jsonl')
                steps = read_jsonl(p.parent / 'steps.jsonl')
                decisions += sum(bool(s.get('decision')) for s in steps)
                if calls and (not steps or not all(s.get('messages') and s.get('before') for s in steps)):
                    errors.append(f'{task}/{instance}: missing request/observation evidence')
                if len(calls) != json.loads(p.read_text())['api_calls_total']:
                    errors.append(f'{task}/{instance}: call count mismatch')
        if not decisions:
            errors.append(task + ': no executable decision among first five scenes')
    return errors


def main():
    import fcntl
    lock = (ROOT / 'runtime/supervisor.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('A collection supervisor is already running')
    config = load_config()
    write_json(ROOT/'runs'/config['run_id']/'environment.json',
               {'recorded_at':now(),'python':sys.version,'python_executable':sys.executable,
                'packages':{name:importlib.metadata.version(name) for name in ['numpy','openai','gymnasium','pandas','matplotlib','scipy','pillow','ray']}})
    snapshot = ROOT / 'runs' / config['run_id'] / 'source_snapshot'
    if not snapshot.exists():
        snapshot.mkdir(parents=True)
        for name in ['src','scripts','configs','prompts','docs','tests']:
            shutil.copytree(ROOT/name,snapshot/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copy2(ROOT/'runtime/source_revision.json',snapshot/'source_revision.json')
    state = {'run_id': config['run_id'], 'pid': os.getpid(), 'started_at': now(), 'status': 'first_five'}
    status_path = ROOT / 'runtime/collection_status.json'
    write_json(status_path, state)
    for limit in [5, 100]:
        processes, logs = [], []
        for task in config['tasks']:
            workers = 1 if limit == 5 else config['workers_per_task']
            for worker in range(workers):
                log = (ROOT / 'runtime' / (task + f'_worker{worker}.log')).open('a')
                logs.append(log)
                processes.append(subprocess.Popen([sys.executable, '-u', '-m', 'civstudy.runner', '--task', task,
                                                   '--limit', str(limit),'--worker-index',str(worker),'--workers',str(workers)],
                                                  stdout=log, stderr=subprocess.STDOUT))
        codes = [p.wait() for p in processes]
        for log in logs:
            log.close()
        if any(codes):
            state.update(status='worker_failed', exit_codes=codes, ended_at=now())
            write_json(status_path, state)
            break
        if limit == 5:
            errors = first_five_ready(config)
            write_json(ROOT / 'runtime/first_five_check.json', {'checked_at': now(), 'errors': errors})
            if errors:
                state.update(status='first_five_needs_fix', errors=errors, ended_at=now())
                write_json(status_path, state)
                break
            state.update(status='collecting', first_five_checked_at=now())
            write_json(status_path, state)
    else:
        state.update(status='analyzing')
        write_json(status_path, state)
    completed = subprocess.run([sys.executable, '-m', 'civstudy.analysis']).returncode
    if state['status'] == 'analyzing':
        summary = json.loads((ROOT / 'reports/development/summary.json').read_text()) if not completed else {}
        state.update(status='complete' if summary.get('complete') else 'incomplete', ended_at=now())
        write_json(status_path, state)


if __name__ == '__main__':
    main()
