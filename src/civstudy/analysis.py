"""Scene-level tables and figures from actual retained attempts only."""
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
from .common import ROOT, load_config, now, read_jsonl, write_csv, write_json

TASK_NAMES = {'development_build_city': 'Build city', 'development_transport': 'Transport'}
OUTCOMES = ['native_success', 'native_failure', 'output_failure', 'execution_failure', 'step_limit',
            'interrupted', 'infrastructure_error', 'running', 'native_terminal_unknown', 'not_run']
LABELS = {
    'output_failure': 'Two unusable final outputs; no replacement action',
    'execution_failure': 'Explicit native command rejection',
    'native_terminal_unknown': 'SDK terminated normally while native minitask verdict remained unknown',
    'step_limit': 'Reached 2000 submitted actions while native outcome unresolved',
    'unchanged_action_repeat': 'Same action and task-relevant state repeated consecutively; context review required',
    'low_score_settlement': 'Native failure immediately after choosing build_city with score below goal',
    'native_deadline_reached': 'Native failure at or after the recorded native turn deadline',
    'transported_unit_no_longer_observed': 'A carried own unit disappeared without an observed city creation; inspect native messages',
    'success_without_loaded_ship_move': 'Native success with no observed movement of a loaded ship',
    'available_goal_settlement_deferred': 'Goal met and build_city legal, but another action selected; context review required',
    'unit_disappearance_during_food_deficit': 'Own unit disappeared over END_TURN while a visible own city had negative food surplus; causal interpretation requires review',
}


def report_result(path):
    row = json.loads(path.read_text())
    row['recorded_stop_reason'] = row['stop_reason']
    if row.get('error_type')=='terminal_without_native_verdict':
        row['stop_reason'] = 'native_terminal_unknown'
    for field in ['prompt_tokens','completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens']:
        if field in row:
            row[field+'_known'] = row[field]
            if row.get(field+'_unknown_calls',0):
                row[field] = None
    return row


def state_key(state):
    obs = state.get('observation', {})
    return json.dumps({'units': {k: {f: v.get(f) for f in ['x', 'y', 'moves_left', 'health']}
                                 for k, v in obs.get('unit', {}).items()},
                       'own_unit_transport':state.get('own_unit_transport',{}),
                       'cities': sorted(obs.get('city', {})), 'metrics': state.get('task_metrics', {})}, sort_keys=True)


def annotate(row, steps):
    labels = []
    common = {k: row[k] for k in ['task_type', 'instance_id', 'episode_id', 'attempt_id']}
    common.update(annotator='civstudy.analysis',reviewer=None)
    if row['stop_reason'] in LABELS:
        labels.append(dict(common, label=row['stop_reason'], definition_version='observable_v2',
                           evidence_steps=[steps[-1]['decision_id']] if steps else [],
                           review_status='direct_stop_record', observation=LABELS[row['stop_reason']]))
    repeated = []
    for before, after in zip(steps, steps[1:]):
        if before.get('native_action') is not None and before.get('native_action') == after.get('native_action'):
            if before.get('after') and after.get('after') and state_key(before['after']) == state_key(after['after']):
                repeated += [before['decision_id'], after['decision_id']]
    if repeated:
        labels.append(dict(common, label='unchanged_action_repeat', definition_version='observable_v2',
                           evidence_steps=list(dict.fromkeys(repeated)), review_status='candidate_requires_context_review',
                           observation=LABELS['unchanged_action_repeat']))
    extra = {}
    submitted = [s for s in steps if 'native_action' in s]
    if row['stop_reason'] == 'native_failure' and submitted:
        action = submitted[-1]['native_action']
        if action and 'build_city' in str(action[2]) and row.get('mini_score') is not None and row.get('mini_goal') is not None and row['mini_score'] < row['mini_goal']:
            extra['low_score_settlement'] = [submitted[-1]['decision_id']]
        if row.get('final_turn') is not None and row.get('native_turn_limit') is not None and row['final_turn'] >= row['native_turn_limit']:
            extra['native_deadline_reached'] = [submitted[-1]['decision_id']]
    loaded_moves = []
    for s in submitted:
        before, after = s.get('before', {}), s.get('after', {})
        old = before.get('observation', {}).get('unit', {})
        new = after.get('observation', {}).get('unit', {})
        cargo = before.get('own_unit_transport', {})
        for identity in old.keys() & new.keys():
            if old[identity].get('type_can_transport') and cargo.get(identity,{}).get('occupied'):
                if (old[identity].get('x'),old[identity].get('y')) != (new[identity].get('x'),new[identity].get('y')):
                    loaded_moves.append(s['decision_id'])
        if after.get('observation') and not any(e.get('type')=='city_appeared' for e in s.get('state_changes',[])):
            if any(cargo.get(identity,{}).get('transported') for identity in old.keys()-new.keys()):
                extra.setdefault('transported_unit_no_longer_observed',[]).append(s['decision_id'])
            own_gone = any(old[identity].get('owner')==before.get('player_id') for identity in old.keys()-new.keys())
            food_deficit = any(city.get('owner')==before.get('player_id') and city.get('surplus_food',0)<0
                               for city in before.get('observation',{}).get('city',{}).values())
            if s['native_action'] is None and own_gone and food_deficit:
                extra.setdefault('unit_disappearance_during_food_deficit',[]).append(s['decision_id'])
        if row['task_type']=='development_build_city':
            metrics = before.get('task_metrics',{})
            if metrics.get('mini_score') is not None and metrics.get('mini_goal') is not None and metrics['mini_score'] >= metrics['mini_goal']:
                if any(a.get('action_key')=='build_city' for a in s.get('legal_actions',[])):
                    action = s['native_action']
                    if action is None or 'build_city' not in str(action[2]):
                        extra.setdefault('available_goal_settlement_deferred',[]).append(s['decision_id'])
    if row['task_type']=='development_transport':
        row['loaded_ship_move_steps'] = len(loaded_moves)
        if row['success'] and not loaded_moves:
            extra['success_without_loaded_ship_move'] = [submitted[-1]['decision_id']] if submitted else []
    for label, evidence in extra.items():
        labels.append(dict(common,label=label,definition_version='observable_v2',evidence_steps=list(dict.fromkeys(evidence)),
                           review_status='candidate_requires_context_review' if label in {'available_goal_settlement_deferred','unit_disappearance_during_food_deficit'} else 'direct_state_record',observation=LABELS[label]))
    return labels


def save_figure(fig, path):
    fig.savefig(path.with_suffix('.png'), dpi=180, facecolor='white')
    fig.savefig(path.with_suffix('.pdf'), facecolor='white')


def transport_process(row, steps):
    """Positive evidence for the same passenger's ordered transport journey."""
    journeys, completed = {}, []
    observed_load, moves, landings = [], [], []
    if steps:
        for identity,cargo in steps[0]['before'].get('own_unit_transport',{}).items():
            if cargo.get('transported'):
                journeys[identity]={'unit_id':identity,'carrier_id':str(cargo.get('transported_by')),
                                   'load_step':'initial_state','load_index':-1}
                observed_load.append('initial_state:'+identity)
    for index,step in enumerate(steps):
        before,after=step.get('before',{}),step.get('after',{})
        old_cargo,new_cargo=before.get('own_unit_transport',{}),after.get('own_unit_transport',{})
        old_units=before.get('observation',{}).get('unit',{})
        new_units=after.get('observation',{}).get('unit',{})
        evidence=step['decision_id']
        for identity,cargo in new_cargo.items():
            if cargo.get('transported') and not old_cargo.get(identity,{}).get('transported'):
                journeys[identity]={'unit_id':identity,'carrier_id':str(cargo.get('transported_by')),
                                   'load_step':evidence,'load_index':index}
                observed_load.append(evidence)
        for identity,cargo in old_cargo.items():
            if not cargo.get('transported'): continue
            carrier=str(cargo.get('transported_by'))
            if carrier in old_units and carrier in new_units:
                old,new=old_units[carrier],new_units[carrier]
                if (old.get('x'),old.get('y'))!=(new.get('x'),new.get('y')):
                    moves.append(evidence)
                    journey=journeys.get(identity)
                    # Passengers can transfer directly between ships (observed in 976).
                    if journey and index>journey['load_index']:
                        journey.setdefault('loaded_move_step',evidence)
                        journey.setdefault('loaded_move_carrier_id',carrier)
                        journey.setdefault('move_index',index)
            if identity in new_units and identity in new_cargo and not new_cargo[identity].get('transported'):
                landings.append(evidence)
                journey=journeys.get(identity)
                if journey and 'move_index' in journey and index>journey['move_index']:
                    journey['landing_step']=evidence
                    journey['landing_index']=index
        action=step.get('native_action')
        if action and action[0]=='unit' and action[2]=='build_city':
            identity=str(action[1]);journey=journeys.get(identity)
            if not journey or index<=journey.get('landing_index',index): continue
            unit=old_units.get(identity,{})
            old_cities=before.get('observation',{}).get('city',{})
            new_cities=after.get('observation',{}).get('city',{})
            created=[city for key,city in new_cities.items() if key not in old_cities and
                     city.get('owner')==before.get('player_id') and
                     (city.get('x'),city.get('y'))==(unit.get('x'),unit.get('y'))]
            if created:
                completed.append({k:v for k,v in dict(journey,settlement_step=evidence).items() if not k.endswith('_index')})
    return {'episode_id':row['episode_id'],'instance_id':row['instance_id'],'attempt_id':row['attempt_id'],
            'native_success':row['success'],'load_observed':bool(observed_load),'loaded_ship_move_observed':bool(moves),
            'landing_observed':bool(landings),'ordered_transport_settlement_observed':bool(completed),
            'load_evidence':list(dict.fromkeys(observed_load)),'move_evidence':list(dict.fromkeys(moves)),
            'landing_evidence':list(dict.fromkeys(landings)),'complete_journeys':completed,
            'interpretation':'Positive player-visible evidence; an unestablished chain does not change the native verdict',
            'trace_path':row['trace_path']}


def figures(rows, annotations, output, config):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    figdir = output / 'figures'
    figdir.mkdir(exist_ok=True)
    tasks = config['tasks']
    colors = ['#0072B2', '#D55E00', '#CC79A7', '#882255', '#E69F00', '#999999', '#666666', '#56B4E9', '#BBBBBB', '#DDDDDD']
    source = f"{config['run_id']} | model reference: {config['model_reference']} | source: episode_results.csv"
    with plt.rc_context({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False, 'pdf.fonttype': 42}):
        fig, ax = plt.subplots(figsize=(13, 5.2), layout='constrained')
        bottom = np.zeros(len(tasks))
        for category, color in zip(OUTCOMES, colors):
            counts = np.array([sum(r['task_type'] == t and r['stop_reason'] == category for r in rows) for t in tasks])
            bars = ax.bar(range(len(tasks)), counts, bottom=bottom, color=color,
                          label=category + ' (' + ', '.join(str(int(v)) for v in counts) + ')')
            for bar, count, start in zip(bars, counts, bottom):
                if count >= 4:
                    ax.text(bar.get_x() + bar.get_width()/2, start + count/2, str(count), ha='center', va='center',
                            color='white' if color in colors[:4] else 'black')
            bottom += counts
        ax.set(xticks=range(len(tasks)), xticklabels=[TASK_NAMES[t] + f"\npolicy n={sum(r['task_type']==t and r['has_policy_result'] for r in rows)}" for t in tasks], ylabel='Scenes (planned n = 100 per task)',
               title='Native outcomes and runner stop reasons')
        ax.legend(loc='upper left', bbox_to_anchor=(1, 1), fontsize=8, title='Counts: Build city, Transport')
        fig.supxlabel(source, fontsize=7)
        save_figure(fig, figdir / 'outcome_distribution'); plt.close(fig)
        usable = [r for r in rows if r['has_policy_result']]
        if not usable:
            return
        data = np.full((len(LABELS), len(tasks)), np.nan)
        counts = np.zeros_like(data)
        for i, label in enumerate(LABELS):
            for j, task in enumerate(tasks):
                n = sum(r['task_type'] == task for r in usable)
                count = len({a['episode_id'] for a in annotations if a['task_type'] == task and a['label'] == label})
                counts[i, j] = count
                if n:
                    data[i, j] = count/n
        fig, ax = plt.subplots(figsize=(8, 4.8), layout='constrained')
        im = ax.imshow(np.ma.masked_invalid(data), cmap='Blues', vmin=0, vmax=1, aspect='auto')
        for i in range(len(LABELS)):
            for j, task in enumerate(tasks):
                n = sum(r['task_type'] == task for r in usable)
                ax.text(j, i, f'{int(counts[i,j])}/{n}' if n else 'not observed', ha='center', va='center',
                        color='white' if data[i,j] > .6 else 'black')
        ax.set(xticks=range(len(tasks)), xticklabels=[TASK_NAMES[t] for t in tasks],
               yticks=range(len(LABELS)), yticklabels=list(LABELS),
               title='Observable labels; repeat label requires context review')
        fig.colorbar(im, ax=ax, label='Scenes with label / scenes with usable policy result')
        fig.supxlabel(source + ' + failure_annotations.csv; multiple labels allowed', fontsize=7)
        save_figure(fig, figdir / 'observable_labels'); plt.close(fig)
        fig, axes = plt.subplots(1, 3, figsize=(13, 4.8), layout='constrained')
        for ax, metric, label in zip(axes, ['api_calls_total', 'env_steps', 'duration_s'], ['API requests', 'Submitted actions', 'Wall time (s)']):
            for j, task in enumerate(tasks):
                selected = [r for r in usable if r['task_type'] == task]
                for i, r in enumerate(selected):
                    color = colors[OUTCOMES.index(r['stop_reason'])]
                    ax.scatter(j + ((i % 9)-4)*.018, r[metric], c=color, marker='o' if r['success'] else 'x', alpha=.7, s=24)
            ax.set(xticks=range(len(tasks)), xticklabels=[TASK_NAMES[t] for t in tasks], ylabel=label, ylim=(0, None))
        fig.suptitle('All usable policy scenes, including failures and truncation; circles = success, crosses = other')
        present = [c for c in OUTCOMES if any(r['stop_reason']==c for r in usable)]
        axes[-1].legend(handles=[Line2D([],[],color=colors[OUTCOMES.index(c)],marker='o' if c=='native_success' else 'x',
                                      linestyle='None',label=c) for c in present],
                        loc='upper left',bbox_to_anchor=(1.02,1),fontsize=7)
        fig.supxlabel(source + '; deterministic horizontal offset, no smoothing', fontsize=7)
        save_figure(fig, figdir / 'resource_distribution'); plt.close(fig)


def case_figures(row, steps, output, config):
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    folder = output / 'cases' / row['episode_id']
    folder.mkdir(parents=True, exist_ok=True)
    points = [(0, json.loads((Path(row['trace_path'])/'initial.json').read_text()))]
    points += [(s['env_step'], s['after']) for s in steps if s.get('after') and s.get('env_step') is not None]
    fig, axes = plt.subplots(2, 1, figsize=(9, 6), layout='constrained')
    xs = [x for x, _ in points]
    score = [s['task_metrics'].get('mini_score', np.nan) for _, s in points]
    axes[0].plot(xs, score, marker='o', markersize=3, label='Native mini_score')
    goals = [s['task_metrics'].get('mini_goal', np.nan) for _, s in points]
    axes[0].plot(xs, goals, '--', label='Native mini_goal')
    axes[0].set_ylabel('Native task score'); axes[0].legend()
    axes[1].plot(xs, [s.get('turn') for _, s in points], marker='s', markersize=3)
    axes[1].set(xlabel='Submitted actions', ylabel='Native turn')
    events = []
    for s in steps:
        action = s.get('native_action')
        key = str(action[2]) if action else ''
        if any(t in key for t in ['board','embark','build_city']):
            events.append((s.get('env_step'),key))
    for x, label in events[:10]:
        if x is not None:
            axes[0].axvline(x,color='#666666',linewidth=.7,linestyle=':')
            axes[0].annotate(label,(x,.97),xycoords=('data','axes fraction'),rotation=90,va='top',fontsize=7)
    fig.suptitle(f"{TASK_NAMES[row['task_type']]} normal {row['instance_id']} | {row['stop_reason']}")
    fig.supxlabel(f"{config['run_id']} | {row['attempt_id']} | source: steps.jsonl", fontsize=7)
    save_figure(fig, folder / 'progress'); plt.close(fig)
    selected = sorted(set([0, len(points)//2, len(points)-1]))
    fig, axes = plt.subplots(1, len(selected), figsize=(5*len(selected), 5.2), layout='constrained', squeeze=False)
    palette = ['#E5D7B1','#E5CC85','#EBC873','#F4E5A2','#84A86A','#617A56','#A9A37B',
               '#D7D9D6','#748A8B','#B9D6DF','#A9D6E5','#3D7D99','#9AC5BE','#D8D8B4']
    cmap = ListedColormap(palette); cmap.set_bad('#303846')
    for ax, point in zip(axes.flat, selected):
        step, state = points[point]
        obs = state.get('observation', {})
        maps = obs.get('map', {})
        terrain, status = np.asarray(maps.get('terrain', [])), np.asarray(maps.get('status', []))
        if terrain.ndim == 2 and status.shape == terrain.shape:
            ax.imshow(np.ma.masked_where(status.T == 0, terrain.T), cmap=cmap, vmin=0, vmax=13, origin='upper', interpolation='nearest')
            for kind, marker in [('unit','o'),('city','s')]:
                groups = {}
                for identity, obj in obs.get(kind, {}).items():
                    if obj.get('x') is None or obj.get('y') is None:
                        continue
                    ax.scatter(obj['x'], obj['y'], marker=marker, s=90, c='#D55E00' if kind=='unit' else '#0072B2', edgecolors='white')
                    groups.setdefault((obj['x'],obj['y']),[]).append(str(identity))
                for position,identities in groups.items():
                    ax.annotate(('U:' if kind=='unit' else 'C:')+','.join(identities), position, xytext=(4,4 if kind=='unit' else -12), textcoords='offset points', fontsize=8)
            ax.set(xlabel='Native tile x', ylabel='Native tile y')
        else:
            ax.text(.5,.5,'Terminal map not supplied by SDK',ha='center',transform=ax.transAxes)
        ax.set_title(f"Action {step}, turn {state.get('turn')}")
    fig.suptitle(f"Player-visible state replay | {row['episode_id']} | circles: units; squares: cities")
    fig.supxlabel('Dark: undiscovered; native tile coordinates; source: retained observation snapshots (not game screen capture)', fontsize=8)
    save_figure(fig, folder / 'keyframes'); plt.close(fig)
    return folder


def main():
    config = load_config()
    manifest = json.loads((ROOT / config['manifest']).read_text())
    run_dir = ROOT / 'runs' / config['run_id']
    output = ROOT / 'reports/development'
    archive = ROOT / 'reports/archive'
    archive.mkdir(parents=True,exist_ok=True)
    previous = output/'summary.json'
    if previous.exists():
        old_run = json.loads(previous.read_text())['run_id']
        if old_run != config['run_id']:
            shutil.move(str(output),str(archive/old_run))
    output.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True,exist_ok=True)
    shutil.copy2(Path(__file__),run_dir/'analysis_source.py')
    from .replay import build_videos
    shutil.copy2(Path(__file__).with_name('replay.py'),run_dir/'replay_source.py')
    video_index = build_videos(config)
    write_json(output/'label_definitions.json',{'version':'observable_v2','definitions':LABELS,
                                             'annotation_unit':'scene; labels can overlap',
                                             'review':'script observations; causal interpretation requires case review'})
    rows, annotations, all_attempts, step_index = [], [], [], {}
    for task in config['tasks']:
        for instance in manifest[task]['instance_ids']:
            episode_id = f'{task}-normal-{instance}'
            paths = sorted((run_dir / 'episodes' / episode_id).glob('attempt*/result.json'))
            attempts = [report_result(p) for p in paths]
            all_attempts += attempts
            usable = [r for r in attempts if r['stop_reason'] not in {'infrastructure_error','interrupted','running'} and r.get('ended_at')]
            row = dict(usable[-1] if usable else attempts[-1] if attempts else
                       {'task_type': task, 'instance_id': instance, 'difficulty': 'normal', 'episode_id': episode_id,
                        'stop_reason': 'not_run', 'success': False, 'strategy_started': False})
            row['has_policy_result'] = bool(usable)
            row['attempt_count'] = len(attempts)
            row['all_attempts_api_calls'] = sum(a.get('api_calls_total',0) for a in attempts)
            row['all_attempts_cost_usd_known'] = sum(a.get('cost_usd_known',0) for a in attempts)
            row['all_attempts_unknown_cost_calls'] = sum(a.get('unknown_cost_calls',0) for a in attempts)
            rows.append(row)
            if usable:
                steps = read_jsonl(Path(row['trace_path']) / 'steps.jsonl')
                step_index[episode_id] = steps
                annotations += annotate(row, steps)
    write_csv(output/'episode_results.csv', rows)
    write_json(output/'scene_manifest.json',manifest)
    scene_index=[]
    for task in config['tasks']:
        for position,instance in enumerate(manifest[task]['instance_ids'],1):
            scene_index.append({'task_type':task,'difficulty':'normal','sampling_position':position,
                                'instance_id':instance,'sampling_seed':manifest[task]['sampling_seed'],
                                'episode_id':f'{task}-normal-{instance}'})
    write_csv(output/'scene_index.csv',scene_index)
    write_csv(output/'trajectory_index.csv',[
        {'episode_id':r['episode_id'],'attempt_id':r.get('attempt_id'),'has_policy_result':r['has_policy_result'],
         'trace_path':r.get('trace_path'),'steps_path':str(Path(r['trace_path'])/'steps.jsonl') if r.get('trace_path') else None,
         'api_calls_path':str(Path(r['trace_path'])/'api_calls.jsonl') if r.get('trace_path') else None,
         'initial_path':str(Path(r['trace_path'])/'initial.json') if r.get('trace_path') else None,
         'final_path':str(Path(r['trace_path'])/'final.json') if r.get('trace_path') else None} for r in rows])
    write_csv(output/'attempt_results.csv', all_attempts, fields=list(dict.fromkeys(k for a in all_attempts for k in a)) or ['episode_id','stop_reason'])
    write_csv(output/'failure_annotations.csv', annotations, ['task_type','instance_id','episode_id','attempt_id','annotator','reviewer','label','definition_version','evidence_steps','review_status','observation'])
    transport_rows=[transport_process(r,step_index[r['episode_id']]) for r in rows
                    if r['task_type']=='development_transport' and r['has_policy_result']]
    write_csv(output/'transport_process.csv',transport_rows,
              ['episode_id','instance_id','attempt_id','native_success','load_observed','loaded_ship_move_observed',
               'landing_observed','ordered_transport_settlement_observed','load_evidence','move_evidence','landing_evidence',
               'complete_journeys','interpretation','trace_path'])
    pending = [r for r in rows if not r['has_policy_result']]
    write_csv(output/'pending_instances.csv', [{k:r.get(k) for k in ['episode_id','task_type','instance_id','stop_reason','attempt_count','trace_path']} for r in pending],
              ['episode_id','task_type','instance_id','stop_reason','attempt_count','trace_path'])
    summaries = []
    for task in config['tasks']:
        subset = [r for r in rows if r['task_type']==task]
        usable = [r for r in subset if r['has_policy_result']]
        n, successes = len(usable), sum(r['success'] for r in usable)
        summary = {'task_type':task,'planned':len(subset),'started':sum(r['attempt_count']>0 for r in subset),
                   'policy_result_scenes':n,'native_finished':sum(r['stop_reason'] in {'native_success','native_failure'} for r in usable),
                   'successes':successes,'success_rate':successes/n if n else None,
                   **dict(Counter(r['stop_reason'] for r in subset))}
        summary.update(env_steps_total=sum(r.get('env_steps',0) for r in usable),
                       api_calls_policy_results=sum(r.get('api_calls_total',0) for r in usable),
                       cost_usd_known_all_attempts=sum(r['all_attempts_cost_usd_known'] for r in subset),
                       unknown_cost_calls_all_attempts=sum(r['all_attempts_unknown_cost_calls'] for r in subset))
        if n:
            p, z = successes/n, 1.959963984540054
            mid = (p+z*z/(2*n))/(1+z*z/n)
            half = z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
            summary.update(wilson95_lower=mid-half,wilson95_upper=mid+half)
            for metric in ['env_steps','api_calls_total','duration_s']:
                values = [r[metric] for r in usable]
                summary[metric+'_median'] = float(np.median(values))
                summary[metric+'_min'] = min(values); summary[metric+'_max'] = max(values)
        summaries.append(summary)
    write_csv(output/'task_summary.csv', summaries)
    prior_attempts = []
    ledger_calls = []
    for run_id in [config['run_id']] + config.get('superseded_run_ids',[]):
        for path in (ROOT/'runs'/run_id/'episodes').glob('*/attempt*/api_calls.jsonl'):
            ledger_calls += read_jsonl(path)
        if run_id != config['run_id']:
            for path in (ROOT/'runs'/run_id/'episodes').glob('*/attempt*/result.json'):
                prior_attempts.append(report_result(path))
    write_csv(output/'superseded_attempts.csv',prior_attempts,fields=list(dict.fromkeys(k for a in prior_attempts for k in a)) or ['episode_id','stop_reason'])
    formal_calls = [c for c in ledger_calls if c['run_id']==config['run_id']]
    summary = {'run_id':config['run_id'],'generated_at':now(), 'planned_scenes':len(rows),
               'policy_result_scenes':sum(r['has_policy_result'] for r in rows),
               'complete':all(r['has_policy_result'] for r in rows), 'tasks':summaries,
               'superseded_run_ids':config.get('superseded_run_ids',[]),
               'superseded_attempt_count':len(prior_attempts),
               'video_count':len(video_index),
               'api_calls_all_attempts':len(ledger_calls),
               'api_calls_formal_all_attempts':len(formal_calls),
               'cost_usd_known_formal_all_attempts':sum(c['cost_usd'] for c in formal_calls if c.get('cost_usd') is not None),
               'unknown_cost_calls_formal':sum(c.get('cost_usd') is None for c in formal_calls),
               'cost_usd_known_all_attempts':sum(c['cost_usd'] for c in ledger_calls if c.get('cost_usd') is not None),
               'unknown_cost_calls':sum(c.get('cost_usd') is None for c in ledger_calls),
               'actual_models':sorted(set(m for r in all_attempts for m in r.get('actual_models',[])))}
    write_json(output/'summary.json', summary)
    if any(r['has_policy_result'] for r in rows):
        figures(rows, annotations, output, config)
    cases = []
    for task in config['tasks']:
        valid = [r for r in rows if r['task_type']==task and r['has_policy_result']]
        failures = [r for r in valid if not r['success']]
        picked = []
        if failures:
            groups = Counter(r['stop_reason'] for r in failures).most_common()
            primary = sorted([r for r in failures if r['stop_reason']==groups[0][0]],key=lambda r:r['env_steps'])
            picked.append(primary[len(primary)//2])
            secondary = [r for r in failures if r['stop_reason']==groups[1][0]] if len(groups)>1 else [r for r in primary if r['episode_id']!=picked[0]['episode_id']]
            if secondary:
                secondary.sort(key=lambda r:r['env_steps'])
                picked.append(secondary[len(secondary)//2])
        successful = sorted([r for r in valid if r['success']],key=lambda r:r['env_steps'])
        if successful:
            picked.append(successful[len(successful)//2])
        for row in picked:
            steps = step_index[row['episode_id']]
            folder = case_figures(row, steps, output, config)
            calls = read_jsonl(Path(row['trace_path'])/'api_calls.jsonl')
            narrative = []
            if row['stop_reason'] == 'output_failure':
                final_calls = calls[-2:]
                narrative.append('失败发生在输出协议阶段，最后一次决策经过一次纠错后仍没有可执行的最终 JSON。')
                narrative.append('对应请求的 finish_reason 为 ' + '、'.join(str(c.get('finish_reason')) for c in final_calls) + '；模型思考内容未用作分析证据。')
            elif row['stop_reason'] == 'native_failure':
                last_action = next((s.get('native_action') for s in reversed(steps) if 'native_action' in s),None)
                if last_action and 'build_city' in str(last_action[2]):
                    narrative.append(f"最后提交了建城动作；终局 mini_score={row.get('mini_score')}，mini_goal={row.get('mini_goal')}，原生反馈判定失败。")
                elif row.get('native_turn_limit') is not None and row.get('final_turn') is not None and row['final_turn'] >= row['native_turn_limit']:
                    narrative.append(f"到达原生回合期限 {row['native_turn_limit']} 时，环境判定任务失败。关键步骤需结合地图、移动力与剩余任务阶段阅读。")
                else:
                    narrative.append('环境给出了原生失败判定；具体事件和状态变化见下表。')
            elif row['success']:
                narrative.append('环境确认成功。')
                if task == 'development_transport':
                    sequence = [(s.get('env_step'),s.get('native_action')) for s in steps if s.get('native_action') and any(t in str(s['native_action'][2]) for t in ['board','embark','build_city'])]
                    narrative.append('装载、登陆、建城相关的实际提交为：' + str(sequence) + '。这些提交是否生效同时参照 state_changes。')
                    narrative.append('原生成功来自 Lua 建城回调，不能从 mini_score 的数值代替判断。')
            else:
                narrative.append(f"运行停止于 {row['stop_reason']}；保留原生状态 {row['native_player_status']}。")
            if task=='development_transport':
                process=next(r for r in transport_rows if r['episode_id']==row['episode_id'])
                narrative.append(f"玩家可见过程证据：装载={process['load_observed']}，载人船移动={process['loaded_ship_move_observed']}，登陆={process['landing_observed']}，同一单位有序建城链={process['ordered_transport_settlement_observed']}。逐阶段步骤见 transport_process.csv；False 表示该项证据未建立。")
                if process['complete_journeys']:
                    narrative.append('完整链条：'+str(process['complete_journeys'])+'。')
            lines = [f"# {row['episode_id']}", '', f"原生状态：{row['native_player_status']}；运行结束原因：{row['stop_reason']}。",
                     f"动作 {row['env_steps']}；调用 {row['api_calls_total']}；原始轨迹 `{row['trace_path']}`。", '',
                     *narrative, '',
                     '下表摘录关键决策、简短理由、真实状态变化和玩家通知。通知单条最多展示500字，完整连续过程见原始轨迹。', '',
                     '| 决策 | 回合 | 模型选择依据 | 实际动作 | 状态变化 | 玩家通知 |','|---|---:|---|---|---|---|']
            selected_steps = set(range(min(3,len(steps)))) | set(range(max(0,len(steps)-4),len(steps)))
            important = [i for i,s in enumerate(steps) if any(e.get('type') in {'unit_transported','unit_transported_by','unit_no_longer_observed','city_appeared'} for e in s.get('state_changes',[]))]
            selected_steps.update(important[:8]);selected_steps.update(important[-5:])
            for i,s in enumerate(steps):
                if i not in selected_steps:
                    continue
                reason = str(s.get('decision',{}).get('reason',s.get('output_errors',''))).replace('|','/').replace('\n',' ')
                event_summary = []
                for event in s.get('state_changes',[]):
                    event = dict(event)
                    if 'state' in event:
                        event['state'] = {k:v for k,v in event['state'].items() if k in ['name','x','y','owner','size','transported_by']}
                    event_summary.append(event)
                action = ('END_TURN' if s['native_action'] is None else s['native_action']) if 'native_action' in s else '未提交'
                notifications = [str(m)[:500].replace('|','/').replace('\n',' ') for m in s.get('native_messages_after',[]) if not ('\"task\"' in str(m) and '\"minitask\"' in str(m))]
                lines.append(f"| {s['decision_id']} | {s.get('game_turn')} | {reason} | {action} | {str(event_summary).replace('|','/')} | {' / '.join(notifications)} |")
            lines += ['', '![原生指标与回合进展](progress.png)', '', '![玩家可见状态关键帧](keyframes.png)', '',
                      '状态回放依据 SDK 玩家观察重建；末步地图缺失时明确标注，不补入隐藏地图。']
            (folder/'case.md').write_text('\n'.join(lines)+'\n')
            cases.append({'episode_id':row['episode_id'],'task_type':task,'instance_id':row['instance_id'],
                          'outcome':row['stop_reason'],'case_path':str(folder/'case.md'),'trace_path':row['trace_path']})
    write_csv(output/'case_index.csv',cases,['episode_id','task_type','instance_id','outcome','case_path','trace_path'])
    local_time = datetime.fromisoformat(summary['generated_at']).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
    lines = ['# 两个发展任务第一轮分析', '',
             f"生成时间：{local_time}（北京时间）。运行 `{config['run_id']}`。",
             f"当前有策略结果 {summary['policy_result_scenes']}/200；" + ('已完成全部预定场景。' if summary['complete'] else '尚未完成，待补实例见 pending_instances.csv。'), '',
             f"模型参考：{config['model_reference']}；实际返回标识：{', '.join(summary['actual_models']) or '尚无调用'}。",
             'thinking/high，8192 输出 tokens，最近 4 次动作历史，2000 环境动作宽停止线。', '',
             '| 任务 | 预定 | 有策略结果 | 已确认成功 | 确认成功比例（分母为策略场景） |','|---|---:|---:|---:|---|']
    for s in summaries:
        rate = f"{s['success_rate']:.1%}" if s['success_rate'] is not None else '尚无数据'
        lines.append(f"| {s['task_type']} | {s['planned']} | {s['policy_result_scenes']} | {s['successes']} | {rate} |")
    lines += ['', f"全部尝试共 {summary['api_calls_all_attempts']} 次 API 请求；已知用量费用估算 {summary['cost_usd_known_all_attempts']:.6f} USD；费用未知请求 {summary['unknown_cost_calls']} 次。费用估算不是供应商账单。",
              f"其中正式版本共 {summary['api_calls_formal_all_attempts']} 次请求，已知费用 {summary['cost_usd_known_formal_all_attempts']:.6f} USD，费用未知 {summary['unknown_cost_calls_formal']} 次；其余为被替换版本的准备开销。", '',
              '', '按场景统计；输出失败、执行失败与步数截断计入策略分母，基础设施故障及未运行单列。不同任务的原始分数不合并求均值。token 用量有未知请求时，表中总量留空，_known 字段保留已知小计。', '',
              '跨海任务的 Lua 在我方建城事件直接设置成功，mini_score 可能仍为 0。原生成功与实际装载、运输、登陆过程分别展示。', '',
              '正式策略结果只来自当前 run_id。准备期间被替换版本的尝试列在 superseded_attempts.csv，不计入当前场景表现，但其请求与费用计入全部开销。', '',
              'v4 的通知累计游标与 SDK 每回合清空列表不匹配，遗漏部分玩家通知；v5 在独立 SDK 中保留跨回合通知，所有受影响实例按修复后的基础配置重新采集。旧轨迹原样保留，没有用其缺失通知作因果判断。', '',
              f"完整玩家可见状态回放视频 {len(video_index)} 个，逐决策从真实初始状态及轨迹重建，非游戏屏幕录制；服务器路径与帧数见 video_index.csv。视频只显示玩家已知地图，完整请求和事件见对应 steps.jsonl。", '',
              'SDK 已终止但小游戏胜负仍未知的场景单列为 native_terminal_unknown，不改写原生状态，也不记作原生失败。它们计入已执行策略的场景数，但没有得到成功确认；原始停止标签另保留在 recorded_stop_reason 中。', '',
              '问题标签记录直接可见的停止原因；unchanged_action_repeat 仅表示动作与任务相关状态连续相同，仍需结合上下文判断其合理性。标签不是已经验证的因果解释。', '',
              f"代表案例共 {len(cases)} 个：先按常见失败类型分组，在最多两类中选择动作数居中的实例，成功参照也选动作数居中的实例；只有一种失败类型时取两个不同实例。缺少相应结局时不补造。见 case_index.csv。"]
    transport_success=[r for r in transport_rows if r['native_success']]
    complete_chains=sum(r['ordered_transport_settlement_observed'] for r in transport_success)
    lines += ['',f"跨海原生成功的 {len(transport_success)} 局中，{complete_chains} 局观察到了同一单位按装载（或初始已载运）、载人船移动、登陆、在登陆后位置建城的有序证据链。没有建立完整证据链时，不自动改写原生判定；逐局阶段与证据步骤见 transport_process.csv。玩家可见记录中的运输链也不等于隐藏全地图上的大陆归属证明。"]
    length_calls = [c for c in formal_calls if c.get('finish_reason')=='length']
    known_finish = sum(c.get('finish_reason') is not None for c in formal_calls)
    lines += ['',f"正式版本中，{len(length_calls)}/{known_finish} 次有完成原因记录的请求以 length 结束；其中 {sum(not c.get('content') for c in length_calls)} 次最终 content 为空。逐请求证据保留在各局 api_calls.jsonl；这与游戏原生失败分开统计。"]
    lines += ['', '| 任务 | 原生失败 | 输出失败 | 原生胜负未知 | 动作总数 | 调用中位数 | 动作中位数 | 耗时中位数（秒） |',
              '|---|---:|---:|---:|---:|---:|---:|---:|']
    for s in summaries:
        duration=f"{s['duration_s_median']:.1f}" if 'duration_s_median' in s else '—'
        lines.append(f"| {s['task_type']} | {s.get('native_failure',0)} | {s.get('output_failure',0)} | {s.get('native_terminal_unknown',0)} | {s['env_steps_total']} | {s.get('api_calls_total_median','—')} | {s.get('env_steps_median','—')} | {duration} |")
    explanations = {'unit_disappearance_during_food_deficit':'结束回合时粮食赤字与我方单位消失同现',
                    'transported_unit_no_longer_observed':'运输中的我方单位随后不再可见',
                    'success_without_loaded_ship_move':'原生成功，但未观察到载人船移动',
                    'available_goal_settlement_deferred':'已达目标且可建城时选择了其他动作',
                    'unchanged_action_repeat':'同一动作与任务相关状态连续相同',
                    'low_score_settlement':'低于目标分数时建城并原生失败'}
    for task in config['tasks']:
        denominator = sum(r['task_type']==task and r['has_policy_result'] for r in rows)
        observed = []
        for label, text in explanations.items():
            count = len({a['episode_id'] for a in annotations if a['task_type']==task and a['label']==label})
            if count:
                observed.append(f'{text}：{count}/{denominator} 局')
        if observed:
            lines += ['', task+' 的可观察现象为：'+'；'.join(observed)+'。标签可重叠，粮食赤字同现与单位消失本身不证明具体因果机制。']
    if length_calls:
        all_reasoning=sum(bool(c.get('usage')) and c['usage'].get('completion_tokens')==config['max_tokens'] and
                          (c['usage'].get('completion_tokens_details') or {}).get('reasoning_tokens')==config['max_tokens'] and
                          not c.get('content') for c in length_calls)
        lines += ['',f"其中 {all_reasoning} 次请求的 completion_tokens 与 reasoning_tokens 都为 {config['max_tokens']}，最终 content 为空，与生成预算耗尽的解释一致。是否调整思考强度或输出预算能改善端到端成功率，仍需独立干预验证，本轮没有进行该比较。"]
    lines += ['', '后续待验证原因应从具体轨迹提出：对到期或关键单位损失案例，区分剩余回合判断、路线选择和城市资源维护；建城349还涉及静态任务评分与实时产出的区别，以及最后选择是否仍符合分数目标。案例中的观察、理由和后继状态只支持该过程的解释，不能替代干预试验。当前汇总仅覆盖本次两个 normal 发展任务。']
    if summary['policy_result_scenes']:
        lines += ['', '![各任务结局及覆盖](figures/outcome_distribution.png)', '', '![多选可观察标签分布](figures/observable_labels.png)', '',
                  '![全部策略场景资源分布](figures/resource_distribution.png)']
    if (output/'review_notes.md').exists():
        lines += ['', '具体轨迹的补充解释见 [案例复核](review_notes.md)，该文件注明复核者、场景和证据步骤。']
    lines += ['', '复现：服务器中 source scripts/env.sh 后运行 python -m civstudy.analysis。表格、静态图和案例均从保留轨迹生成。', '',
              '图表工作流参考 Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. [arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065)；本报告未使用示意数据。']
    (output/'development_first_round.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
