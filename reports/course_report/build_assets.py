"""Rebuild report tables and figures from existing results only; no API calls."""
import csv
import json
import math
import shutil
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'reports/course_report'


def quantile(values, p):
    values = sorted(values)
    location = (len(values) - 1) * p
    lower, upper = math.floor(location), math.ceil(location)
    return values[lower] + (values[upper] - values[lower]) * (location - lower)


def main():
    rows = list(csv.DictReader((ROOT / 'reports/development/episode_results.csv').open()))
    diagnostic = json.loads((ROOT / 'reports/failure_diagnosis/cohort_diagnostics.json').read_text())
    summary = json.loads((ROOT / 'reports/development/summary.json').read_text())
    assert len(rows) == 200 and summary['complete']
    assert diagnostic['decisions'] + diagnostic['correction_decisions'] == diagnostic['api_calls']
    assert diagnostic['decisions'] - (diagnostic['correction_decisions'] - diagnostic['recovered_decisions']) == sum(int(r['env_steps']) for r in rows)
    resources = []
    runtime = []
    for task in ['development_build_city', 'development_transport']:
        times = [float(r['duration_s']) for r in rows if r['task_type'] == task]
        runtime.append({'task_type': task, 'n': len(times), 'unit': 'seconds',
                        'mean': statistics.mean(times), 'median': statistics.median(times),
                        'q25': quantile(times, .25), 'q75': quantile(times, .75),
                        'p90': quantile(times, .90), 'max': max(times)})
        for outcome in ['native_success', 'native_failure', 'output_failure']:
            group = [r for r in rows if r['task_type'] == task and r['stop_reason'] == outcome]
            record = {'task_type': task, 'outcome': outcome, 'n': len(group)}
            for field in ['env_steps', 'api_calls_total', 'duration_s']:
                values = [float(r[field]) for r in group]
                record[field] = {'median': statistics.median(values), 'q25': quantile(values, .25),
                                 'q75': quantile(values, .75), 'min': min(values), 'max': max(values),
                                 'mean': statistics.mean(values), 'sum': sum(values)}
            resources.append(record)
    (OUT / 'report_tables.json').write_text(json.dumps(
        {'run_id': summary['run_id'], 'task_summary': summary['tasks'], 'resources_by_outcome': resources,
         'runtime_by_task': runtime,
         'decision_counts': {k: diagnostic[k] for k in ['decisions', 'api_calls', 'correction_decisions', 'recovered_decisions']}},
        ensure_ascii=False, indent=2) + '\n')
    assets = {
        'fig01_outcomes': 'reports/development/figures/outcome_distribution',
        'fig03_resources': 'reports/development/figures/resource_distribution',
        'fig04_city349_progress': 'reports/development/cases/development_build_city-normal-349/progress',
        'fig05_transport631_keyframes': 'reports/development/cases/development_transport-normal-631/keyframes',
        'figS1_observable_labels': 'reports/development/figures/observable_labels',
    }
    for name, original in assets.items():
        for suffix in ['.png', '.pdf']:
            shutil.copy2(ROOT / (original + suffix), OUT / 'figures' / (name + suffix))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
    plt.rcParams['pdf.fonttype'] = 42
    n = diagnostic['decisions']
    correction = diagnostic['correction_decisions']
    recovered = diagnostic['recovered_decisions']
    failed = correction - recovered
    submitted = n - failed
    fig, ax = plt.subplots(figsize=(13, 4.7))
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis('off')
    nodes = {
        'start': (.015, .43, f'Logical decisions\n{n:,}', '#edf3f7'),
        'direct': (.27, .72, f'Usable first output\n{n-correction:,}', '#d9edf7'),
        'correct': (.27, .19, f'Correction requested\n{correction:,}', '#fff0d3'),
        'recovered': (.53, .38, f'Usable after correction\n{recovered:,}', '#d9edf7'),
        'failed': (.53, .035, f'No usable final output\n{failed:,}', '#f3dfeb'),
        'submitted': (.795, .72, f'Submitted to environment\n{submitted:,}', '#d9edf7'),
    }
    width, height = .19, .19
    for _, (x, y, label, color) in nodes.items():
        ax.add_patch(FancyBboxPatch((x, y), width, height, boxstyle='round,pad=.01', facecolor=color,
                                   edgecolor='#4b6070', linewidth=1.2))
        ax.text(x + width/2, y + height/2, label, ha='center', va='center', fontsize=11)
    for source, target in [('start', 'direct'), ('start', 'correct'), ('direct', 'submitted'),
                           ('correct', 'recovered'), ('correct', 'failed'), ('recovered', 'submitted')]:
        x, y, *_ = nodes[source]; tx, ty, *_ = nodes[target]
        ax.add_patch(FancyArrowPatch((x + width + .01, y + height/2), (tx - .012, ty + height/2),
                                    arrowstyle='-|>', mutation_scale=13, linewidth=1.3, color='#4b6070'))
    fig.suptitle(f'Decision-level output and correction flow | {diagnostic["api_calls"]:,} API requests', fontsize=14)
    fig.text(.5, .065, 'Counts are decisions/actions, not successful episodes. Submitted actions include END_TURN.', ha='center', fontsize=9)
    fig.text(.5, .025, f'{summary["run_id"]} | source: cohort_diagnostics.json + episode_results.csv', ha='center', fontsize=8)
    fig.subplots_adjust(left=.015, right=.985, top=.90, bottom=.12)
    fig.savefig(OUT / 'figures/fig02_decision_flow.png', dpi=180, facecolor='white')
    fig.savefig(OUT / 'figures/fig02_decision_flow.pdf', facecolor='white')
    plt.close(fig)
    patterns = json.loads((ROOT / 'reports/failure_diagnosis/common_failure_patterns.json').read_text())
    groups = patterns['groups']
    outcomes = ['native_success', 'native_failure', 'output_failure']
    fields = [
        ('famine_loss', 'At least one famine loss'),
        ('actual_landing', 'At least one confirmed landing'),
        ('landed_settler_lost_at_next_end_turn', 'Landed settler lost at next END_TURN'),
        ('all_settlers_lost_before_city', 'All settlers lost before founding'),
        ('population_block', 'Population blocks settler production'),
    ]
    counts = [[groups[o][key] for o in outcomes] for key, _ in fields]
    percentages = [[100 * groups[o][key] / groups[o]['n'] for o in outcomes] for key, _ in fields]
    fig, ax = plt.subplots(figsize=(10.5, 5.3))
    im = ax.imshow(percentages, vmin=0, vmax=100, cmap='Blues', aspect='auto')
    ax.set_xticks(range(3), [f'{name}\n(n={groups[o]["n"]})' for name, o in zip(
        ['Native success', 'Native failure', 'Output failure'], outcomes)])
    ax.set_yticks(range(len(fields)), [label for _, label in fields])
    ax.tick_params(axis='both', length=0, pad=9)
    for i, values in enumerate(counts):
        for k, count in enumerate(values):
            value = percentages[i][k]
            ax.text(k, i, f'{count}/{groups[outcomes[k]]["n"]} ({value:.1f}%)', ha='center', va='center',
                    fontsize=10.5, color='white' if value >= 60 else '#193248')
    ax.set_title('Transport: recurring events by final outcome', pad=18, fontsize=14)
    bar = fig.colorbar(im, ax=ax, fraction=.035, pad=.04)
    bar.set_label('Percent of episodes within each outcome')
    fig.text(.5, .065, 'Events overlap; these are observed trajectories, not mutually exclusive causal attributions.',
             ha='center', fontsize=9)
    fig.text(.5, .025, f'{patterns["run_id"]} | all 100 transport scenes | source: common_failure_patterns.json',
             ha='center', fontsize=8)
    fig.subplots_adjust(left=.36, right=.91, top=.86, bottom=.20)
    for suffix in ['.png', '.pdf']:
        fig.savefig(OUT / 'figures' / ('fig_common_failure_patterns' + suffix),
                    dpi=180, facecolor='white')
    plt.close(fig)
    print(json.dumps({'scenes': len(rows), 'logical_decisions': n, 'submitted_actions': submitted,
                      'corrections': correction, 'recovered': recovered, 'output_failures': failed,
                      'resource_groups': len(resources)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
