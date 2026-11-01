"""One native reset/action per development task; no model call or formal result."""
import inspect
import json
from .common import ROOT, load_config, now, write_json
from .env import action_menu, language_state, make_env, snapshot


def main():
    import civrealm.envs.freeciv_minitask_env as sdk
    path = inspect.getfile(sdk)
    if not str(path).startswith(str(ROOT / 'third_party')):
        raise RuntimeError('The process did not load the independent SDK')
    if 'self._course_steps >= 128' in inspect.getsource(sdk.FreecivMinitaskEnv.step):
        raise RuntimeError('Inherited 128-step truncation remains active')
    config = load_config()
    manifest = json.loads((ROOT / config['manifest']).read_text())
    for task in config['tasks']:
        instance = manifest[task]['instance_ids'][0]
        folder = ROOT / 'runs/preflight' / config['run_id'] / task
        env, obs, info = make_env(task, instance, 20261101 + instance, folder)
        try:
            native, menu = action_menu(info)
            state = language_state(env, obs, info)
            if task == 'development_transport' and not state['own_unit_transport']:
                raise RuntimeError('Own cargo/carrier observations are absent')
            if 'self.messages.clear()' in inspect.getsource(type(env.unwrapped.civ_controller).handle_end_turn):
                raise RuntimeError('Native turn clears the cumulative notification cursor')
            initial = snapshot(env,obs,info,include_messages=True)
            initial_actor_types = sorted(info.get('available_actions',{}))
            write_json(folder/'initial.json',initial)
            write_json(folder/'model_context.json', {'state':state,'legal_actions':menu})
            after, reward, terminated, truncated, next_info = env.step(None)
            if not next_info:
                raise RuntimeError('No feedback after native END_TURN')
            final = snapshot(env,after,next_info,include_messages=True)
            if final['native_messages'][:len(initial['native_messages'])] != initial['native_messages']:
                raise RuntimeError('Player notification history was replaced during END_TURN')
            write_json(folder/'after.json',final)
            result = {'checked_at':now(),'task':task,'instance_id':instance,'sdk_path':path,
                      'legal_action_count':len(menu),'actor_types':initial_actor_types,
                      'unit_count':len(initial['observation'].get('unit',{})),'known_tiles':len(state['known_tiles']),
                      'own_unit_transport':state['own_unit_transport'],
                      'metrics':initial['task_metrics'], 'after_metrics':next_info.get('minitask'),
                      'initial_turn':initial['turn'],'after_turn':next_info.get('turn'),
                      'terminated':terminated,'truncated':truncated,'paid_requests':0}
            result['notification_history_preserved'] = True
            write_json(folder/'check.json',result)
            print(json.dumps(result,ensure_ascii=False),flush=True)
        finally:
            env.close()


if __name__ == '__main__':
    main()
