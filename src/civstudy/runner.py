"""Resume complete scene results, retain attempts, and count submitted actions."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from .common import ROOT, append_json, load_config, now, plain, read_jsonl, write_json
from .openrouter import api_key
from .env import action_menu, changes, language_state, make_env, native_status, snapshot

INFRA = {'infrastructure_error', 'interrupted', 'running'}


def run_episode(config, task, instance, attempt_number, run_dir):
    from .agent import Agent, OutputFailure
    episode_id = f'{task}-normal-{instance}'
    attempt_id = f'{episode_id}-attempt{attempt_number}'
    folder = run_dir / 'episodes' / episode_id / f'attempt{attempt_number}'
    folder.mkdir(parents=True, exist_ok=False)
    identity = dict(run_id=config['run_id'], episode_id=episode_id, attempt_id=attempt_id)
    result = dict(identity, task_type=task, difficulty='normal', instance_id=instance,
                  method=config['method'], prompt_version=config['prompt_version'],
                  code_version=config.get('code_version'), game_seed=20261101 + instance,
                  started_at=now(), stop_reason='running', success=False,
                  strategy_started=False, env_steps=0, end_turn_actions=0, chat_messages=0,
                  initial_turn=None, final_turn=None, native_game_status=None,
                  native_player_status=None, mini_score=None, mini_goal=None,
                  trace_path=str(folder), native_turn_limit=None)
    write_json(folder / 'result.json', result)
    started, history = time.monotonic(), []
    env = agent = None
    obs, info = {}, {}
    phase = 'initialization'
    record = None
    try:
        env, obs, info = make_env(task, instance, result['game_seed'], folder)
        if not info:
            raise RuntimeError('Empty reset information')
        result['initial_turn'] = info.get('turn')
        write_json(folder / 'initial.json', snapshot(env, obs, info, include_messages=True))
        message_cursor = 0
        spec = json.loads((ROOT / config['task_specs']).read_text())[task]
        agent = Agent(config, folder / 'api_calls.jsonl', identity)
        for index in range(config['max_env_steps']):
            native, menu = action_menu(info)
            decision_id = attempt_id + f'-decision{index:04d}'
            before = snapshot(env, obs, info)
            record = dict(identity, decision_id=decision_id, env_step=None, game_turn=info.get('turn'),
                          before=before, legal_actions=menu, execution_response='not_submitted')
            messages = env.unwrapped.civ_controller.messages
            record['native_messages_before'] = list(messages[message_cursor:])
            message_cursor = len(messages)
            context = {'task_type': task, 'objective_and_rules': spec['objective'],
                       'state': language_state(env, obs, info), 'task_metrics': info.get('minitask', {}),
                       'events': info.get('mini_game_messages', []), 'legal_actions': menu,
                       'native_messages':record['native_messages_before'],
                       'communication_actions': plain(info.get('available_actions', {}).get('player', {})),
                       'history': history[-config['history_length']:],
                       'resource_context': {'remaining_env_steps': config['max_env_steps'] - index,
                                            'api_calls_so_far': len(agent.calls),
                                            'elapsed_s': time.monotonic() - started}}
            record['context'] = context
            write_json(folder / f'decision_{index:04d}.json', record)
            phase = 'api'
            result['strategy_started'] = True
            decision = agent.decide(context, len(native), decision_id, record)
            action = native[decision['action_id']]
            phase = 'execution'
            chat = decision.get('chat')
            if chat:
                env.unwrapped.civ_controller.ws_client.send_message(chat)
                result['chat_messages'] += 1
                record['chat_sent'] = chat
            result['env_steps'] += 1  # submissions, including those that later fail
            if action is None:
                result['end_turn_actions'] += 1
            record.update(env_step=result['env_steps'], submitted_at=now(), native_action=plain(action))
            write_json(folder / f'decision_{index:04d}.json', record)
            next_obs, reward, terminated, truncated, next_info = env.step(action)
            if not next_info:
                record['execution_response'] = 'unknown'
                record['environment_error'] = 'empty_info_after_native_timeout'
                raise RuntimeError('Empty environment feedback')
            obs, info = next_obs, next_info
            after = snapshot(env, obs, info)
            record.update(after=after, reward=reward, terminated=terminated, truncated=truncated,
                          returned_at=now(), execution_response='returned_without_explicit_ack',
                          state_changes=changes(before, after))
            messages = env.unwrapped.civ_controller.messages
            record['native_messages_after'] = list(messages[message_cursor:])
            message_cursor = len(messages)
            history.append({'native_action': plain(action), 'reason': decision['reason'],
                            'before_metrics': before['task_metrics'], 'after_metrics': after['task_metrics'],
                            'state_changes': record['state_changes'], 'turn': info.get('turn')})
            history[-1]['native_messages'] = record['native_messages_after']
            write_json(folder / f'decision_{index:04d}.json', record)
            append_json(folder / 'steps.jsonl', record)
            record = None
            if terminated or info.get('minitask', {}).get('status') == 1:
                status = native_status(info)['native_player_status']
                result['stop_reason'] = 'native_success' if status == 1 else 'native_failure' if status == 0 else 'native_terminal_unknown'
                if status not in [0, 1]:
                    result['error_type'] = 'terminal_without_native_verdict'
                break
            if truncated:
                result['stop_reason'] = 'infrastructure_error'
                result['error_type'] = 'native_truncation_without_task_verdict'
                break
        else:
            result['stop_reason'] = 'step_limit'
    except OutputFailure as error:
        result.update(stop_reason='output_failure', error_type=type(error).__name__)
    except KeyboardInterrupt:
        result.update(stop_reason='interrupted', error_type='KeyboardInterrupt')
    except Exception as error:
        # A native explicit rejection is an execution failure, not a rerunnable server fault.
        rejected = phase == 'execution' and 'Bad command' in str(error)
        result.update(stop_reason='execution_failure' if rejected else 'infrastructure_error',
                      error_type=type(error).__name__, error_phase=phase)
        if rejected and record is not None:
            record['execution_response'] = 'rejected'
            record['environment_error'] = str(error)
    finally:
        if record is not None:
            write_json(folder / f'decision_{len(history):04d}.json', record)
            append_json(folder / 'steps.jsonl', record)
        result.update(native_status(info))
        result['success'] = result['native_player_status'] == 1
        result['final_turn'] = info.get('turn')
        if result['initial_turn'] is not None and result['final_turn'] is not None:
            result['game_turns_elapsed'] = result['final_turn'] - result['initial_turn']
        if env is not None:
            write_json(folder / 'final.json', snapshot(env, obs, info, include_messages=True))
            try:
                env.close()
            except Exception as error:
                result['close_error'] = type(error).__name__
        calls = agent.calls if agent is not None else []
        result.update(api_calls_total=len(calls), api_calls_decision=sum(c['purpose'] == 'decision' for c in calls),
                      api_calls_correction=sum(c['purpose'] == 'correction' for c in calls),
                      actual_models=sorted(set(c['actual_model'] for c in calls if c.get('actual_model'))),
                      api_latency_s=sum(c['latency_s'] for c in calls),
                      cost_usd_known=sum(c['cost_usd'] for c in calls if c.get('cost_usd') is not None),
                      unknown_cost_calls=sum(c.get('cost_usd') is None for c in calls),
                      usage_unknown_calls=sum(c['usage_unknown'] for c in calls))
        for key in ['prompt_tokens', 'completion_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens']:
            values = [(c.get('usage') or {}).get(key) for c in calls]
            result[key] = sum(v for v in values if v is not None)
            result[key + '_unknown_calls'] = sum(v is None for v in values)
        result['reasoning_tokens_known'] = sum(((c.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens') or 0 for c in calls)
        result['reasoning_tokens_unknown_calls'] = sum(((c.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens') is None for c in calls)
        result['duration_s'] = time.monotonic() - started
        result['ended_at'] = now()
        write_json(folder / 'result.json', result)
        append_json(run_dir / f'attempts_{task}.jsonl', result)
    print(json.dumps({k: result[k] for k in ['episode_id', 'attempt_id', 'stop_reason', 'env_steps', 'api_calls_total', 'success']}) , flush=True)
    return result


def collect(task, config_path=None, limit=None, worker_index=0, workers=1):
    config = load_config(config_path)
    try:
        api_key(config)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    run_dir = ROOT / 'runs' / config['run_id']
    run_dir.mkdir(parents=True, exist_ok=True)
    config['source_revision'] = json.loads((ROOT / 'runtime/source_revision.json').read_text())
    config['code_version'] = config['source_revision']['git_head']
    run_manifest = run_dir / f'run_manifest_{task}.json'
    # Freeze one manifest before the two task processes start; existing content is retained.
    try:
        with run_manifest.open('x') as f:
            json.dump(dict(config, created_at=now()), f, ensure_ascii=False, indent=2)
    except FileExistsError:
        frozen = json.loads(run_manifest.read_text())
        for key in ['model', 'max_tokens', 'reasoning_effort', 'top_p', 'max_env_steps', 'history_length', 'source_revision',
                    'api_provider', 'base_url', 'openrouter_provider', 'request_timeout_s']:
            if frozen.get(key) != config.get(key):
                raise SystemExit(f'Frozen run differs in {key}; use a distinct run_id.')
    manifest = json.loads((ROOT / config['manifest']).read_text())
    instances = manifest[task]['instance_ids'][:limit][worker_index::workers]
    for position, instance in enumerate(instances):
        paths = sorted((run_dir / 'episodes' / f'{task}-normal-{instance}').glob('attempt*/result.json'))
        previous = [json.loads(p.read_text()) for p in paths]
        result = None
        if any(r['stop_reason'] not in INFRA and r.get('ended_at') for r in previous):
            continue
        for attempt in range(len(previous), config['infrastructure_retries'] + 1):
            result = run_episode(config, task, instance, attempt, run_dir)
            if result['stop_reason'] not in INFRA or result['stop_reason'] == 'interrupted':
                break
        if previous and len(previous) >= config['infrastructure_retries'] + 1:
            print(f'PENDING_INFRA {task} {instance}: both attempts retained', flush=True)
        if position == 4:
            print('FIRST_FIVE_FINISHED', task, flush=True)
        if result is not None and result['stop_reason'] == 'interrupted':
            break


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', required=True)
    parser.add_argument('--config')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--worker-index',type=int,default=0)
    parser.add_argument('--workers',type=int,default=1)
    args = parser.parse_args()
    collect(args.task, args.config, args.limit, args.worker_index, args.workers)
