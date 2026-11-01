"""Native actions and player-visible state; no access to savegame hidden maps."""
from pathlib import Path
import numpy as np
from .common import ROOT, plain


def make_env(task, instance, seed, log_dir):
    import civrealm
    import gymnasium as gym
    from civrealm.configs import fc_args, fc_web_args
    fc_web_args['port'] = '18080'
    settings = {
        'host': 'localhost', 'advisor': 'disabled', 'server_timeout': 60,
        'begin_turn_timeout': 120, 'wait_for_timeout': 30,
        'debug.take_screenshot': False, 'debug.get_webpage_image': None,
        'debug.autosave': False, 'debug.record_action_and_observation': False,
        'debug.logging_path': str(Path(log_dir) / 'sdk_logs'),
        'debug.randomly_generate_seeds': False,
        'debug.gameseed': seed, 'debug.mapseed': seed, 'debug.agentseed': seed,
    }
    for k, v in settings.items():
        fc_args[k] = v
    env = gym.make('civrealm/FreecivMinitask-v0', disable_env_checker=True)
    try:
        obs, info = env.reset(seed=seed, minitask_pattern={'type': task, 'level': 'normal', 'id': instance})
    except BaseException:
        env.close()
        raise
    return env, obs, info


def action_menu(info):
    native, readable = [], []
    directions = ['NorthWest', 'North', 'NorthEast', 'West', 'East', 'SouthWest', 'South', 'SouthEast']
    for kind, actors in info.get('available_actions', {}).items():
        for actor, choices in actors.items():
            for key, valid in choices.items():
                if not valid:
                    continue
                # SDK chat is a communication interface, counted through Decision.chat.
                if kind == 'player' and actor == 'message' and key == 'chat':
                    continue
                entry = {'id': len(native), 'actor_type': kind, 'actor_id': plain(actor), 'action_key': key}
                parts = str(key).split('_')
                if parts[0] in {'goto', 'attack', 'disembark', 'embark'} and len(parts) > 1 and parts[1].isdigit():
                    d = int(parts[1])
                    if d < 8:
                        entry['direction'] = directions[d]
                readable.append(entry)
                native.append((kind, actor, key))
    readable.append({'id': len(native), 'action_key': 'END_TURN'})
    native.append(None)
    return native, readable


def own_transport(env, obs):
    ctrl = env.unwrapped.civ_controller
    result = {}
    for identity, unit in ctrl.unit_ctrl.units.items():
        if unit.get('owner') == ctrl.player_ctrl.my_player_id and (identity in obs.get('unit', {}) or str(identity) in obs.get('unit', {})):
            result[str(identity)] = {k: unit.get(k) for k in ['transported','transported_by','occupied']}
    return plain(result)


def snapshot(env, obs, info, include_messages=False):
    state = {'turn': info.get('turn'), 'player_id': env.unwrapped.civ_controller.player_ctrl.my_player_id,
                  'observation': obs, 'events': info.get('mini_game_messages', []),
                  'own_unit_transport': own_transport(env, obs),
                  'task_metrics': info.get('minitask', {})}
    if include_messages:
        state['native_messages'] = list(env.unwrapped.civ_controller.messages)
    return plain(state)


def language_state(env, obs, info):
    from civrealm.envs.freeciv_wrapper.llm_wrapper import LLMWrapper
    from civrealm.freeciv.map.map_const import TERRAIN_NAMES
    view = LLMWrapper(env).get_llm_info(obs, info)
    state = {k: v for k, v in obs.items() if k not in {'map', 'rules', 'tech'}}
    # sup_units repeats complete unit-type definitions for every technology.
    # Native rules/tech observations remain intact in the retained snapshots.
    tech = {}
    for identity, entry in obs.get('tech', {}).items():
        summary = {k: v for k, v in entry.items() if k not in {'sup_units', 'sup_improvements'}}
        for field in ['sup_units', 'sup_improvements']:
            values = entry.get(field, [])
            if isinstance(values, dict):
                values = list(values.values())
            summary[field] = [v.get('name', v.get('rule_name')) if isinstance(v, dict) else v for v in values]
        tech[identity] = summary
    state['tech'] = tech
    state['own_unit_transport'] = own_transport(env, obs)
    maps = obs.get('map', {})
    visible = np.asarray(maps.get('status', []))
    tiles = []
    if visible.ndim == 2:
        for x, y in zip(*np.nonzero(visible)):
            tile = {'x': int(x), 'y': int(y), 'visibility_status': int(visible[x, y])}
            for key in ['terrain', 'output', 'resource', 'extras']:
                data = maps.get(key)
                if data is not None:
                    tile[key] = plain(data[x, y])
            if 'terrain' in tile:
                tile['terrain_name'] = TERRAIN_NAMES[tile['terrain']]
            tiles.append(tile)
    state['known_tiles'] = tiles
    state['map_shape'] = list(visible.shape)
    state['language_view'] = view
    return plain(state)


def native_status(info):
    metrics = info.get('minitask', {})
    return {'native_game_status': metrics.get('status'),
            'native_player_status': metrics.get('success', metrics.get('is_mini_success')),
            'mini_score': metrics.get('mini_score'), 'mini_goal': metrics.get('mini_goal'),
            'native_turn_limit': metrics.get('max_turn')}


def changes(before, after):
    events = []
    a, b = before.get('observation', {}), after.get('observation', {})
    # Empty terminal observations are unavailable, not proof that all units disappeared.
    if not b:
        return [{'type': 'terminal_observation_unavailable'}]
    for kind in ['unit', 'city']:
        old, new = a.get(kind, {}), b.get(kind, {})
        for identity in new.keys() - old.keys():
            events.append({'type': kind + '_appeared', 'id': identity, 'state': new[identity]})
        for identity in old.keys() - new.keys():
            events.append({'type': kind + '_no_longer_observed', 'id': identity})
        for identity in new.keys() & old.keys():
            for field in ['x', 'y', 'moves_left', 'health', 'owner']:
                av, bv = old[identity].get(field), new[identity].get(field)
                if av != bv:
                    events.append({'type': kind + '_' + field, 'id': identity, 'before': av, 'after': bv})
    old, new = before.get('own_unit_transport', {}), after.get('own_unit_transport', {})
    for identity in old.keys() & new.keys():
        for field in ['transported','transported_by','occupied']:
            if old[identity].get(field) != new[identity].get(field):
                events.append({'type':'unit_'+field,'id':identity,'before':old[identity].get(field),'after':new[identity].get(field)})
    return events
