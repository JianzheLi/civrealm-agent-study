"""Fetch the curated review pack and complete selected attempts from msfm."""
import json
import html
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTE = '/home/ubuntu/jianzheli/University/conginitve_reasoning/civrealm-agent-study'
PACK = ROOT / 'reports/failure_diagnosis'


def write_index(cases, receipt):
    names = {'development_build_city': '建城', 'development_transport': '跨海'}
    outcomes = {'native_success': '原生成功', 'native_failure': '原生失败', 'output_failure': '输出失败'}
    counts = Counter(c['outcome'] for c in cases)
    table = []
    markdown = []
    for case in cases:
        label = names[case['task_type']] + str(case['instance_id'])
        raw = Path(os.path.relpath(ROOT / case['local_trace_path'], PACK)).as_posix()
        table.append(f'<tr data-task="{case["task_type"]}" data-outcome="{case["outcome"]}">'
                     f'<td>{label}</td><td>{html.escape(case["role"])}</td><td>{outcomes[case["outcome"]]}</td>'
                     f'<td>{case["env_steps"]}</td><td>{case["api_calls"]}</td><td>{html.escape(case["reason"])}</td>'
                     f'<td><a href="{case["html_path"]}">回放与时间线</a><br>'
                     f'<a href="{raw}/player_visible_replay.mp4">完整视频</a> · <a href="{raw}/result.json">原始结果</a></td></tr>')
        markdown.append(f'| [{label}]({case["case_path"]}) | {case["role"]} | {outcomes[case["outcome"]]} | {case["reason"]} |')
    gb = receipt['bytes'] / 1e9
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>固定8K预算：失败诊断与本地案例</title>
<style>body{{max-width:1250px;margin:36px auto;padding:0 24px;font:16px/1.7 system-ui;color:#172b3a;background:#fcfdff}}h1{{font-size:30px}}a{{color:#075b9a}}.intro{{background:#edf4fa;border-left:5px solid #0072b2;padding:14px 22px}}select{{padding:7px;margin:12px 12px 12px 0}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{border-bottom:1px solid #d9e2e9;text-align:left;vertical-align:top;padding:12px 9px}}th{{background:#edf3f7}}img{{max-width:100%}}code{{background:#edf3f7;padding:2px 5px}}</style>
<h1>固定8K预算：失败诊断与本地精选案例</h1>
<div class="intro"><p>本轮保持 <code>thinking/high + max_tokens=8192</code>。1M上下文容量与单次生成额度是两回事；8K是有效的固定预算实验条件。</p>
<p>完整200局中：74局输出失败，9局原生游戏失败。二者分别解释，不删除输出失败来抬高成功率。</p></div>
<p>本地完整保存 <b>{len(cases)} 个案例</b>，约 <b>{gb:.2f} GB</b>原始数据：{counts['native_failure']}个原生失败（全部）、{counts['output_failure']}个输出失败、{counts['native_success']}个成功参照。精选子集用于诊断，总体统计仍使用全部200局。</p>
<p><a href="analysis.md">完整中文失败分析</a> · <a href="cohort_diagnostics.json">全体统计证据</a> · <a href="local_case_index.csv">本地/服务器路径索引</a> · <a href="download_receipt.json">下载核对记录</a></p>
<p><a href="../course_report/失败共性分析.md">失败共性分析与成功对照</a> · <a href="../course_report/发展任务_结果分析报告.md">课程报告正文</a> · <a href="common_failure_patterns.csv">100局跨海共性指标</a></p>
<p>每个案例页面可直接播放完整玩家可见状态回放，展开每次决策，查看请求、最终输出、动作、单位/城市变化和原生通知。回放由轨迹重建，并非游戏屏幕录制。</p>
<label>任务 <select id="task"><option value="">全部</option><option value="development_build_city">建城</option><option value="development_transport">跨海</option></select></label>
<label>结局 <select id="outcome"><option value="">全部</option><option value="native_failure">原生失败</option><option value="output_failure">输出失败</option><option value="native_success">原生成功</option></select></label><span id="count"></span>
<div style="overflow-x:auto"><table><thead><tr><th>案例</th><th>入选角色</th><th>完整局结局</th><th>动作</th><th>API调用</th><th>为什么保留</th><th>本地证据</th></tr></thead><tbody>{''.join(table)}</tbody></table></div>
<h2>全体200局的结局分布</h2><img src="../development/figures/outcome_distribution.png" alt="全体结果，非精选子集">
<script>const task=document.getElementById('task'),outcome=document.getElementById('outcome');function filter(){{let n=0;for(const row of document.querySelectorAll('tbody tr')){{row.hidden=Boolean((task.value&&row.dataset.task!==task.value)||(outcome.value&&row.dataset.outcome!==outcome.value));if(!row.hidden)n++;}}document.getElementById('count').textContent='显示 '+n+' 个案例';}}task.onchange=outcome.onchange=filter;filter();</script></html>'''
    (PACK / 'index.html').write_text(page)
    readme = ['# 失败诊断与本地精选材料', '',
              '[打开本地案例浏览入口](index.html) · [中文失败分析](analysis.md)', '',
              '新增[失败共性分析](../course_report/失败共性分析.md)：用完整100局跨海对照失败与成功。63个未成功实例中54个在建城前失去全部移民且未恢复，53个曾尝试转产；对应逐局指标与证据步骤保存在common_failure_patterns.csv/json。', '',
              f'已下载并核对 {len(cases)} 个完整案例，原始文件约 {gb:.2f} GB。包含全部9个原生失败，以及代表性输出失败与成功参照。', '',
              '每例保留完整观察、实际请求与输出、所有纠错、逐步命令与状态、初末状态和完整状态回放。源目录已有的SDK日志也原样保留，但SDK日志处理器可能跨场景复用，逐局证据以各自steps.jsonl和api_calls.jsonl为准。大文件位于仓库 runs/local_review/development-baseline-v5-20261101/，被Git忽略。精简解释、地图关键帧、进展图和可离线打开的HTML在本目录。', '',
              '**本轮保持8K生成预算。** 这是固定预算条件下的端到端结果；不将输出失败改写为原生失败，也不把它们从总体成功率分母中删除。', '',
              '| 案例 | 入选角色 | 完整局结局 | 为什么保留 |', '|---|---|---|---|', *markdown, '',
              '## 数据与复现', '',
              '- cohort_diagnostics.json、episode_diagnostics.csv：全体200局的失败类型、调用统计与初始条件分组。',
              '- common_failure_patterns.csv/json：完整100局跨海的共性统计、指标定义、关键单位损失与登陆/人口提示证据；由scripts/analyze_common_failure_patterns.py只读生成。',
              '- local_case_index.csv/json：精选案例的原始服务器路径和本地相对路径。',
              '- cases/<episode>/：逐决策HTML/Markdown、timeline.json、真实进展图、玩家可见地图关键帧与原始任务说明。',
              '- rule_evidence.txt、action_evidence.txt：原生评分和plant/build_city动作区别的源码片段。',
              '- download_receipt.json：下载时间、逐例文件数与字节数核对；不使用额外哈希。', '',
              '在服务器加载 scripts/env.sh 后运行 python scripts/prepare_failure_review.py 可重建统计与案例页面；本地 python3 scripts/download_review_cases.py 下载/恢复精选原始文件并重建浏览目录。', '',
              '精选规则见 selected_cases.json；这是按问题选例，不是新的随机样本，不得据其比例替代全体200局统计。原始JSON中仍保留服务器路径，文件未为本地展示而改写。']
    (PACK / 'README.md').write_text('\n'.join(readme) + '\n')


def main():
    PACK.mkdir(parents=True, exist_ok=True)
    subprocess.run(['rsync', '-az', 'msfm:' + REMOTE + '/reports/failure_diagnosis/', str(PACK) + '/'], check=True)
    selection = json.loads((PACK / 'selected_cases.json').read_text())
    cases = json.loads((PACK / 'local_case_index.json').read_text())
    destination = ROOT / 'runs/local_review' / selection['run_id']
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(['rsync', '-azr', '--stats', '--files-from=' + str(PACK / 'rsync_files.txt'),
                    'msfm:' + REMOTE + '/runs/' + selection['run_id'] + '/', str(destination) + '/'], check=True)
    verified = []
    for case in cases:
        folder = ROOT / case['local_trace_path']
        files = [p for p in folder.rglob('*') if p.is_file()]
        size = sum(p.stat().st_size for p in files)
        if len(files) != case['files'] or size != case['bytes']:
            raise RuntimeError('Incomplete download: ' + case['episode_id'])
        verified.append({'episode_id': case['episode_id'], 'files': len(files), 'bytes': size,
                         'local_trace_path': str(folder)})
    receipt = {'run_id': selection['run_id'], 'downloaded_at': datetime.now(timezone.utc).isoformat(),
               'case_count': len(verified), 'bytes': sum(c['bytes'] for c in verified),
               'cases': verified, 'verification': 'Selected file counts and total bytes match remote inventory; no hashes used.'}
    (PACK / 'download_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    (destination.parent / 'README.md').write_text(
        '# 本地精选原始材料\n\n'
        '这里是 reports/failure_diagnosis/selected_cases.json 指定的诊断子集，完整基准仍保存在 msfm。'
        '每个 attempt 保留全部观察、决策、API请求/输出、初末状态和完整状态回放视频。'
        'source_snapshot 与两个 run_manifest 记录实际运行代码和参数。\n\n'
        '原始 result.json 中的 trace_path 仍是服务器路径；本地映射见 reports/failure_diagnosis/local_case_index.csv。'
        '该目录被 Git 忽略。不能用按问题挑选的子集重新计算总体成功率。\n')
    write_index(cases, receipt)
    print(json.dumps({'downloaded_cases': len(verified), 'bytes': receipt['bytes'], 'root': str(destination)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
