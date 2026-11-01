"""Read the frozen cohort once and prepare a portable, offline review pack; no API calls."""
import csv
import html
import json
import os
from collections import Counter
from pathlib import Path

from civstudy.common import ROOT, now, read_jsonl, write_csv, write_json

OUTPUT = ROOT / 'reports/failure_diagnosis'
SELECTION = json.loads((OUTPUT / 'selected_cases.json').read_text())
RUN = ROOT / 'runs' / SELECTION['run_id']
CHOSEN = {f"{c['task_type']}-normal-{c['instance_id']}": c for c in SELECTION['cases']}


def unit_view(state):
    cargo = state.get('own_unit_transport', {})
    return {identity: {**{k: unit.get(k) for k in ['x', 'y', 'moves_left', 'health']},
                       **cargo.get(identity, {})}
            for identity, unit in state.get('observation', {}).get('unit', {}).items()}


def city_view(state):
    return {identity: {k: v for k, v in city.items()
                       if any(word in k for word in ['food', 'prod', 'shield']) or k in ['name', 'size', 'owner']}
            for identity, city in state.get('observation', {}).get('city', {}).items()}


def public_notices(step):
    return [str(v) for v in step.get('native_messages_after', []) if not str(v).lstrip().startswith('{')]


def compact_call(call):
    usage = call.get('usage') or {}
    return {'call_id': call['call_id'], 'purpose': call['purpose'], 'finish_reason': call.get('finish_reason'),
            'content': call.get('content'), 'prompt_tokens': usage.get('prompt_tokens'),
            'completion_tokens': usage.get('completion_tokens'),
            'reasoning_tokens': (usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
            'latency_s': call.get('latency_s')}


def prepare_selected(row, steps, calls, config):
    from civstudy.analysis import case_figures
    episode = row['episode_id']
    entry = CHOSEN[episode]
    folder = case_figures(row, steps, OUTPUT, config)
    destination = ROOT / 'runs/local_review' / SELECTION['run_id'] / 'episodes' / episode / 'attempt0'
    relative = Path(os.path.relpath(destination, folder))
    call_index = {c['call_id']: c for c in calls}
    timeline = []
    for step in steps:
        before, after = step['before'], step.get('after')
        timeline.append({'decision_id': step['decision_id'], 'env_step': step.get('env_step'),
                         'turn': before.get('turn'), 'action_submitted': 'native_action' in step,
                         'native_action': step.get('native_action'), 'reason': step.get('decision', {}).get('reason'),
                         'before_metrics': before['task_metrics'], 'after_metrics': (after or {}).get('task_metrics'),
                         'legal_build_city': any(a.get('action_key') == 'build_city' for a in step['legal_actions']),
                         'before_units': unit_view(before), 'after_units': unit_view(after) if after else None,
                         'before_cities': city_view(before), 'after_cities': city_view(after) if after else None,
                         'state_changes': step.get('state_changes'), 'native_notices': public_notices(step),
                         'output_errors': step.get('output_errors'),
                         'calls': [compact_call(call_index[k]) for k in step['api_calls']]})
    write_json(folder / 'timeline.json', timeline)
    (folder / 'agent_task_instruction.txt').write_text(steps[0]['context']['objective_and_rules'] + '\n')
    title = f"{episode}：{entry['role']}"
    lines = [f'# {title}', '', entry['reason'], '',
             f"原生成功={row['success']}；停止原因={row['stop_reason']}；动作={row['env_steps']}；"
             f"调用={row['api_calls_total']}；耗时={row['duration_s']:.1f}秒。", '',
             f"[完整状态回放]({relative}/player_visible_replay.mp4) · [本地交互时间线](index.html) · "
             f"[逐步结构化摘要](timeline.json) · [全部请求与输出]({relative}/api_calls.jsonl) · "
             f"[原始轨迹]({relative}/steps.jsonl)", '',
             '回放依据真实玩家观察重建，并非游戏屏幕录制。原始JSON中的服务器路径保持不变，本地映射见本材料索引。', '',
             '![进展](progress.png)', '', '![玩家可见地图](keyframes.png)', '',
             '| 决策 | 回合 | 实际动作 | 模型简短理由 | 原生通知/输出错误 |', '|---|---:|---|---|---|']
    sections = []
    for step in timeline:
        action = ('END_TURN' if step['native_action'] is None else str(step['native_action'])) if step['action_submitted'] else '未提交动作'
        evidence = ' / '.join(step['native_notices']) or str(step['output_errors'] or '')
        clean = lambda value: str(value or '').replace('|', '/').replace('\n', ' ')
        short = step['decision_id'].rsplit('-decision', 1)[-1]
        lines.append(f"| {short} | {step['turn']} | {clean(action)} | {clean(step['reason'])} | {clean(evidence)} |")
        record_path = relative / f'decision_{short}.json'
        data = json.dumps(step, ensure_ascii=False, indent=2)
        sections.append(f'<details id="d{short}"><summary>决策 {short} · 回合 {step["turn"]} · {html.escape(action)}</summary>'
                        f'<p>{html.escape(step["reason"] or "没有可执行的最终输出")}</p>'
                        f'<p><a href="{record_path}">完整决策记录（观察、实际请求、合法菜单与前后状态）</a></p>'
                        f'<pre>{html.escape(data)}</pre></details>')
    (folder / 'case.md').write_text('\n'.join(lines) + '\n')
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{max-width:1100px;margin:32px auto;padding:0 20px;font:16px/1.6 system-ui;color:#172b3a}}a{{color:#075b9a}}video{{width:100%;max-height:680px;background:#303846}}img{{max-width:100%}}summary{{cursor:pointer;padding:12px;background:#edf3f7}}details{{margin:10px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f9fb;padding:16px;font-size:13px}}</style>
<p><a href="../../index.html">← 返回案例目录</a></p><h1>{html.escape(title)}</h1>
<p>{html.escape(entry['reason'])}</p><p>停止原因：{row['stop_reason']}；动作 {row['env_steps']}；调用 {row['api_calls_total']}。</p>
<video controls preload="none" src="{relative}/player_visible_replay.mp4"></video>
<p>玩家可见状态重建，每次决策一帧；不是游戏屏幕录制。下列模型理由是最终简短输出，不是内部思考过程。</p>
<p><a href="{relative}/initial.json">初始观察</a> · <a href="{relative}/final.json">最终观察</a> · <a href="{relative}/steps.jsonl">完整轨迹</a> · <a href="{relative}/api_calls.jsonl">全部请求与输出</a> · <a href="agent_task_instruction.txt">模型当时的任务说明</a></p>
<img src="progress.png" alt="真实指标进展"><img src="keyframes.png" alt="玩家可见地图关键帧">
<h2>逐决策证据</h2>{''.join(sections)}</html>'''
    (folder / 'index.html').write_text(page)
    size = sum(p.stat().st_size for p in Path(row['trace_path']).rglob('*') if p.is_file())
    files = sum(p.is_file() for p in Path(row['trace_path']).rglob('*'))
    return {**entry, 'episode_id': episode, 'outcome': row['stop_reason'], 'env_steps': row['env_steps'],
            'api_calls': row['api_calls_total'], 'remote_trace_path': row['trace_path'],
            'local_trace_path': str(destination.relative_to(ROOT)), 'bytes': size, 'files': files,
            'case_path': f'cases/{episode}/case.md', 'html_path': f'cases/{episode}/index.html'}


def main():
    import matplotlib
    matplotlib.use('Agg')
    config = json.loads((ROOT / 'configs/development.json').read_text())
    assert config['run_id'] == SELECTION['run_id']
    rows = list(csv.DictReader((ROOT / 'reports/development/episode_results.csv').open()))
    assert len(rows) == 200 and all(r['has_policy_result'] == 'True' for r in rows)
    invalid = Counter(); endings = Counter(); groups = {}; episode_rows = []; selected = {}
    calls_total = decisions = correction_total = recovery_total = 0
    nonlength_errors = []; length_nonempty = []; native_reviews = []; terminal_examples = []
    for index in rows:
        folder = Path(index['trace_path']); row = json.loads((folder / 'result.json').read_text())
        steps = read_jsonl(folder / 'steps.jsonl'); calls = read_jsonl(folder / 'api_calls.jsonl')
        call_index = {c['call_id']: c for c in calls}; per_decision = {}
        for c in calls: per_decision.setdefault(c['decision_id'], []).append(c)
        decisions += len(steps); calls_total += len(calls)
        for s in steps:
            cs = per_decision[s['decision_id']]
            corrected = any(c['purpose'] == 'correction' for c in cs)
            correction_total += corrected
            recovery_total += corrected and bool(s.get('decision'))
            for error in s.get('output_errors', []):
                c = call_index[error['call_id']]
                kind = 'length_empty' if c.get('finish_reason') == 'length' and not c.get('content') else 'length_partial_json' if c.get('finish_reason') == 'length' else 'other_output_error'
                invalid[kind] += 1
                if kind == 'other_output_error': nonlength_errors.append({'episode_id': row['episode_id'], 'error': error, 'call': compact_call(c)})
        for c in calls:
            if c.get('finish_reason') == 'length' and c.get('content'):
                length_nonempty.append({'episode_id': row['episode_id'], **compact_call(c)})
        final_calls = per_decision[steps[-1]['decision_id']]
        if row['stop_reason'] == 'output_failure':
            signature = [(c.get('finish_reason'), bool(c.get('content')),
                          (c.get('usage') or {}).get('completion_tokens'),
                          ((c.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens')) for c in final_calls]
            endings[json.dumps(signature)] += 1
            terminal_examples.append({'episode_id': row['episode_id'], 'calls': [compact_call(c) for c in final_calls]})
        initial = steps[0]['before']; units = initial['observation'].get('unit', {})
        initial_cities = city_view(initial)
        famine_steps = [s['decision_id'] for s in steps if any('Famine feared' in m and 'lost' in m for m in public_notices(s))]
        landed = [s for s in steps if s.get('native_action') and 'disembark' in str(s['native_action'][2])]
        population = [s['decision_id'] for s in steps if any("can't build Settlers yet" in m for m in public_notices(s))]
        land_units = sum(not u.get('type_can_transport') for u in units.values())
        ships = len(units) - land_units
        surpluses = [c.get('surplus_food') for c in initial_cities.values()]
        food = surpluses[0] if surpluses else None
        summary = {'task_type': row['task_type'], 'episode_id': row['episode_id'], 'instance_id': row['instance_id'],
                   'stop_reason': row['stop_reason'], 'success': row['success'], 'env_steps': row['env_steps'],
                   'api_calls': row['api_calls_total'], 'initial_land_units': land_units, 'initial_ships': ships,
                   'initial_food_surplus': food, 'famine_loss_notifications': len(famine_steps),
                   'landing_actions': len(landed), 'population_block_notifications': len(population)}
        episode_rows.append(summary)
        if row['task_type'] == 'development_transport':
            key = f'food_surplus={food};land_units={land_units};ships={ships}'
            group = groups.setdefault(key, Counter()); group['n'] += 1; group[row['stop_reason']] += 1
        if row['stop_reason'] == 'native_failure':
            losses = []
            for landing in landed:
                identity = str(landing['native_action'][1]); after_landing = False
                for s in steps:
                    if s is landing: after_landing = True; continue
                    if not after_landing or not s.get('after'): continue
                    old = s['before']['observation'].get('unit', {}); new = s['after']['observation'].get('unit', {})
                    if identity in old and identity not in new:
                        losses.append({'unit_id': identity, 'landing_step': landing['decision_id'], 'disappearance_step': s['decision_id'],
                                       'notices': public_notices(s), 'cities_created': [e for e in s.get('state_changes', []) if e.get('type') == 'city_appeared']})
                        break
            native_reviews.append({**summary, 'famine_steps': famine_steps, 'population_block_steps': population, 'landing_losses': losses})
        if row['episode_id'] in CHOSEN:
            selected[row['episode_id']] = prepare_selected(row, steps, calls, config)
    ordered = [selected[f"{c['task_type']}-normal-{c['instance_id']}"] for c in SELECTION['cases']]
    stats = {'run_id': SELECTION['run_id'], 'generated_at': now(), 'episodes': len(rows), 'decisions': decisions,
             'api_calls': calls_total, 'correction_decisions': correction_total, 'recovered_decisions': recovery_total,
             'invalid_call_types': dict(invalid), 'terminal_output_signatures': dict(endings),
             'transport_initial_condition_groups': groups, 'native_failure_review': native_reviews,
             'other_output_errors': nonlength_errors, 'nonempty_length_calls': length_nonempty,
             'terminal_output_evidence': terminal_examples, 'selected_cases': ordered}
    write_json(OUTPUT / 'cohort_diagnostics.json', stats)
    write_csv(OUTPUT / 'episode_diagnostics.csv', episode_rows)
    write_json(OUTPUT / 'local_case_index.json', ordered)
    write_csv(OUTPUT / 'local_case_index.csv', ordered)
    paths = ['environment.json', 'run_manifest_development_build_city.json', 'run_manifest_development_transport.json',
             'source_snapshot/', 'analysis_source.py', 'replay_source.py']
    paths += [f"episodes/{r['episode_id']}/attempt0/" for r in ordered]
    (OUTPUT / 'rsync_files.txt').write_text('\n'.join(paths) + '\n')
    print(json.dumps({k: stats[k] for k in ['episodes', 'decisions', 'api_calls', 'correction_decisions', 'recovered_decisions', 'invalid_call_types', 'terminal_output_signatures', 'transport_initial_condition_groups', 'other_output_errors']}, ensure_ascii=False))
    print('Selected case count:', len(ordered), 'bytes:', sum(r['bytes'] for r in ordered), 'files:', sum(r['files'] for r in ordered))


if __name__ == '__main__':
    main()
