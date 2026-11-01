"""Capture the native Freeciv-web UI while reenacting recorded actions, without an LLM."""

import argparse
import json
import os
import queue
import shutil
import threading
import time
import traceback
from pathlib import Path

from .common import ROOT, load_config, now, read_jsonl, write_json
from .env import make_env, native_status


EXAMPLES = {
    'development_build_city-normal-93': 4,
    'development_build_city-normal-349': 50,
    'development_transport-normal-631': 5,
    'development_transport-normal-351': 8,
}

EXAMPLE_EXPLANATIONS = {
    'development_build_city-normal-93':
        '第4回合在(7,5)建成 Weimar，城址分6.2，目标6.2，达到门槛后原生判定成功。'
        '这张图应看新城的位置；6.2衡量该位置的预设资源潜力。',
    'development_build_city-normal-349':
        '第29回合在(9,3)建成 Erfurt，但城址分5.6低于目标6.0，还差0.4，原生判定失败。'
        '因此画面里确实有城市。原轨迹决策0048–0054尝试修路、开矿或等待，理由是工程可补足0.4分；'
        '该假设与预置评分表的规则不符。决策0055在分数仍为5.6时建城，触发终局。'
        '可分析的问题是对评分机制的误解及多次反馈后的策略修正；基线说明未明示静态查表规则，'
        '需同时考虑任务说明是否充分。',
    'development_transport-normal-631':
        '第3回合移民111在(5,3)建成新城 Osnabrück，原生成功标志为1；'
        '原轨迹也有该移民的登船、船只移动、登陆与建城证据。'
        '日志仍显示 mini_score=0、mini_goal=1，这是当前脚本未同步更新分数字段，不能据此判成失败。',
    'development_transport-normal-351':
        '到第10回合期限仍未建成目标新城，原生成功标志为0。画面中的 Hannover 是初始城市。'
        '原轨迹中已有移民因饥荒损失，之后尝试重新生产并购买移民；'
        '城市人口只有1，原生通知明确提示人口不足，盾牌达到45也无法完成移民生产。'
        '模型随后仍等待完工，最终未恢复可用于建城的移民。'
        '可分析的问题是单位维护、生产前提的联合约束，以及收到失败反馈后是否修改计划。',
}


class NativeViewer:
    """Keep Playwright's synchronous API off the environment's asyncio thread."""

    def __init__(self, port, player, player_id, folder, browser_root):
        self.port, self.player, self.player_id = port, player, player_id
        self.folder, self.browser_root = Path(folder), Path(browser_root)
        self.requests, self.responses = queue.Queue(), queue.Queue()
        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.thread.start()
        self.receive()

    def receive(self):
        result = self.responses.get(timeout=120)
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    def capture(self, name, caption):
        self.requests.put(('capture', name, caption))
        return self.receive()

    def close(self):
        if self.thread.is_alive():
            self.requests.put(('close', '', ''))
            result = self.receive()
            self.thread.join(timeout=10)
            return result

    def worker(self):
        try:
            from playwright.sync_api import sync_playwright

            browser_env = os.environ.copy()
            browser_env.pop('DEEPSEEK_API_KEY', None)
            browser_env['LD_LIBRARY_PATH'] = str(self.browser_root / 'libs/usr/lib/x86_64-linux-gnu')
            executable = self.browser_root / 'chrome-headless-shell-linux64/chrome-headless-shell'
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    executable_path=str(executable), headless=True, env=browser_env,
                    args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
                context = browser.new_context(viewport={'width': 1280, 'height': 800})
                context.route('https://apis.google.com/**', lambda route: route.abort())
                page = context.new_page()
                page.goto(
                    f'http://127.0.0.1:18080/webclient/?action=multi&civserverport={self.port}'
                    '&civserverhost=unknown&multi=true&type=multiplayer',
                    wait_until='domcontentloaded')
                page.locator('#username_req').wait_for(state='visible', timeout=30000)
                page.locator('#username_req').fill(f'nativeview{self.port}{time.time_ns() % 1000000}')
                page.locator('.ui-dialog-buttonset .ui-button').nth(1).click()
                page.wait_for_function(
                    'document.body.innerText.includes("You are logged in as")', timeout=30000)
                console = page.locator('#pregame_text_input')
                console.wait_for(state='visible', timeout=30000)
                console.fill('/observe ' + self.player)
                console.press('Enter')
                page.wait_for_function(
                    'typeof units !== "undefined" && Object.keys(units).length > 0', timeout=30000)
                page.evaluate("""playerId => {
                    const first = Object.values(units).find(u => u.owner === playerId);
                    window.nativeExampleInitialTile = first.tile;
                    window.nativeExampleInitialCities = Object.values(cities)
                        .filter(c => c.owner === playerId).map(c => c.id);
                    center_tile_mapcanvas(tiles[first.tile]);
                }""", self.player_id)
                self.responses.put({'ready': True, 'observer_command': '/observe ' + self.player})
                while True:
                    kind, name, caption = self.requests.get()
                    if kind == 'close':
                        break
                    # Let notifications arrive, hide their presentation without running
                    # end-dialog callbacks, and repaint the full native map viewport.
                    page.wait_for_timeout(650)
                    presentation = page.evaluate("""({preferCity, playerId}) => {
                        $('.ui-dialog, .ui-widget-overlay').hide();
                        if (active_city !== null) city_dialog_close_handler();
                        set_default_mapview_active();
                        setup_window_size();
                        const cityList = Object.values(cities).filter(c => c.owner === playerId);
                        const unitList = Object.values(units).filter(u => u.owner === playerId);
                        const newCities = cityList.filter(
                            c => !window.nativeExampleInitialCities.includes(c.id));
                        const focus = preferCity
                            ? newCities[newCities.length - 1] || {tile: window.nativeExampleInitialTile}
                            : unitList[0] || cityList[0];
                        if (focus) center_tile_mapcanvas(tiles[focus.tile]);
                        mapview_slide.active = false;
                        update_map_canvas(0, 0, mapview.store_width, mapview.store_height);
                        const canvas = document.getElementById('canvas');
                        canvas.style.transform = 'scale(2.2)';
                        canvas.style.transformOrigin = '50% 50%';
                        canvas.style.imageRendering = 'pixelated';
                        $('.ui-dialog, .ui-widget-overlay').hide();
                        return {focusId: focus ? focus.id : null,
                            focusTile: focus ? focus.tile : null, playerId,
                            nativeClientState: civclient_state};
                    }""", {'preferCity': name in {'final', 'before_terminal'}, 'playerId': self.player_id})
                    page.wait_for_timeout(400)
                    page.evaluate("$('.ui-dialog, .ui-widget-overlay').hide()")
                    output = self.folder / (name + '.png')
                    page.screenshot(path=str(output))
                    self.responses.put({'path': str(output), 'caption': caption,
                                        'native_map_scale': 2.2, 'dialogs_hidden': True,
                                        'presentation': presentation})
                context.close()
                browser.close()
                self.responses.put({'closed': True})
        except BaseException:
            error = traceback.format_exc()
            (self.folder / 'browser_error.txt').write_text(error)
            self.responses.put({'error': error})


def capture_example(episode, source_run, browser_root, output_root):
    source = ROOT / 'runs' / source_run / 'episodes' / episode / 'attempt0'
    original = json.loads((source / 'result.json').read_text())
    steps = [s for s in read_jsonl(source / 'steps.jsonl') if 'native_action' in s]
    folder = Path(output_root) / episode
    folder.mkdir(parents=True, exist_ok=False)
    task, instance = original['task_type'], original['instance_id']
    result = {
        'episode_id': episode, 'source_run': source_run, 'source_trace': str(source),
        'type': 'native_freeciv_web_screenshots_of_recorded_action_reenactment',
        'recorded_at': now(), 'source_stop_reason': original['stop_reason'],
        'source_success': original['success'], 'model_requests': 0,
        'frames': [], 'submitted_actions': 0,
        'note': 'New live UI demonstration from the recorded actions; not an original-run screen recording.',
    }
    env = viewer = None
    obs, info = {}, {}
    try:
        env, obs, info = make_env(task, instance, original['game_seed'], folder)
        own_player = obs['player'][env.unwrapped.civ_controller.player_ctrl.my_player_id]['name']
        viewer = NativeViewer(env.unwrapped.get_port(), own_player,
                              env.unwrapped.civ_controller.player_ctrl.my_player_id, folder, browser_root)
        result['observer_player'] = own_player

        def take(name):
            status = native_status(info)
            label = ('SUCCESS' if status['native_player_status'] == 1 else
                     'FAILURE' if status['native_player_status'] == 0 else 'IN PROGRESS')
            caption = (f'RE-ENACTMENT | {episode} | {name} | '
                       f'action {result["submitted_actions"]} | turn {info.get("turn")} | {label}')
            frame = viewer.capture(name, caption)
            frame.update(name=name, turn=info.get('turn'), status=status)
            result['frames'].append(frame)

        take('initial')
        for index, step in enumerate(steps, 1):
            if episode == 'development_transport-normal-351' and index == len(steps):
                take('before_terminal')
            action = step['native_action']
            action = tuple(action) if isinstance(action, list) else action
            obs, reward, terminated, truncated, info = env.step(action)
            result['submitted_actions'] = index
            if index == EXAMPLES[episode]:
                take('process')
            if terminated or truncated or info.get('minitask', {}).get('status') == 1:
                break
        take('final')
        result.update(native_status(info))
        result['success'] = result['native_player_status'] == 1
        result['source_outcome_agrees'] = result['native_player_status'] == original['native_player_status']
    except BaseException:
        result['error'] = traceback.format_exc()
        raise
    finally:
        if viewer is not None:
            viewer.close()
        if env is not None:
            env.close()
        write_json(folder / 'capture.json', result)
    print(json.dumps({k: result[k] for k in ['episode_id', 'success', 'submitted_actions', 'source_outcome_agrees']}), flush=True)
    return result


def export_gallery(results):
    output = ROOT / 'reports/native_examples'
    output.mkdir(parents=True, exist_ok=True)
    lines = ['# Freeciv 原生游戏界面示例', '',
             '以下是按已有案例动作重新演示时截取的 Freeciv-web 界面，用于展示成功与失败过程。'
             '不是第一轮采集当时的原始截图，也不替代正式实验结果；本次不调用模型。', '',
             '| 案例 | 本次原生结局 | 与原案例结局一致 | 画面 |', '| --- | --- | --- | --- |']
    manifest = []
    for result in results:
        episode = result['episode_id']
        case = output / episode
        case.mkdir(exist_ok=True)
        for frame in result['frames']:
            shutil.copy2(frame['path'], case / (frame['name'] + '.png'))
        write_json(case / 'capture.json', result)
        outcome = '成功' if result['success'] else '原生失败' if result['native_player_status'] == 0 else '未决'
        links = ' · '.join(f'[{f["name"]}]({episode}/{f["name"]}.png)' for f in result['frames'])
        lines.append(f'| {episode} | {outcome} | {result["source_outcome_agrees"]} | {links} |')
        manifest.append(result)
    lines += ['', '完整复演与截图元数据见各案例 capture.json。画面通过独立观察者客户端观察玩家视角，'
              '界面弹窗已关闭，原生地图显示放大至2.2倍；截图说明在本页和元数据中保留。'
              '模型与第一轮行为的分析仍应引用原轨迹。', '']
    lines += [
        '## 分数怎么算，为什么有城市仍会失败', '',
        '**建城任务**的分数衡量城址的资源潜力。论文表9先对地块计算粮食、生产和贸易的加权分，'
        '再取城址对应范围内评分最高的6块求和：', '',
        '$$', r'\rho_i=0.4F_i+0.4P_i+0.2T_i,\qquad S_c=\sum_{i\in\mathrm{top6}(c)}\rho_i', '$$', '',
        '其中 F、P、T 分别是地块的粮食、生产、贸易产出。论文把目标定义为候选城址评分分布的80%分位数；'
        '具体实例的实际目标读取 mini_goal。[论文附录A.2、表9](https://arxiv.org/html/2401.10568v2)', '',
        '当前存档已把位置分和目标预先写好；实际运行的 Lua 按坐标查表，并在建城时判定：', '',
        '```lua', 'score = map_conf[y + 1][x + 1]',
        'success = (score >= score_goal - 0.0001)  -- 在建城事件中判定', '```', '',
        '所以“低分”指所选位置低于该局门槛。修路、开矿不会更新这张预置表；'
        '城市当回合的净粮食、净生产也不能直接代入，代替城址的6地块评分。'
        '分数达到门槛后还需要实际建城；在低分位置建城会立即结束任务。'
        '完整地图评分表未提供给 Agent。'
        '[建城规则及脚本证据](../../docs/tasks/development_build_city.md)', '',
        '**跨海任务**按期限内是否触发我方新建城事件判成功，当前脚本没有额外核查大陆变化，'
        '且建城后只改成功标志，没有把 mini_score 从0改为1。'
        '因此用原生 success/is_mini_success 判结局，另外检查登船、航行、登陆和建城的轨迹。'
        '[跨海规则](../../docs/tasks/development_transport.md)', '',
        '| 案例 | 城址分或原始分数字段 | 目标 | 原生成功标志 | 判定理由 |',
        '| --- | ---: | ---: | ---: | --- |',
        '| 建城93 | 6.2 | 6.2 | 1 | 在达标位置建城 |',
        '| 建城349 | 5.6 | 6.0 | 0 | 所选城址低于目标0.4 |',
        '| 跨海631 | 0 | 1 | 1 | 已建新城，分数字段未更新 |',
        '| 跨海351 | 0 | 1 | 0 | 到期未建新城 |', '',
        '这些是任务自己的 mini_score，与完整文明对局的综合分数分开统计。'
        '下文行为原因引用第一轮轨迹，截图仅展示相应复演的游戏状态。', '',
    ]
    for result in results:
        episode = result['episode_id']
        task_name = '建城' if 'build_city' in episode else '跨海建城'
        outcome = '成功' if result['success'] else '失败'
        lines += [f'## {task_name}{outcome}（{episode.rsplit("-", 1)[-1]}）', '',
                  EXAMPLE_EXPLANATIONS[episode], '',
                  f'[原轨迹与逐步决策](../failure_diagnosis/cases/{episode}/case.md)', '',
                  f'![{task_name}{outcome}的原生地图状态]({episode}/final.png)', '']
    (output / 'README.md').write_text('\n'.join(lines))
    write_json(output / 'manifest.json', manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', nargs='+', choices=list(EXAMPLES), default=list(EXAMPLES))
    parser.add_argument('--source-run', default=load_config()['run_id'])
    parser.add_argument('--browser-root', type=Path, default=ROOT / 'runtime/tools/browser')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'runs/native_examples_20261102')
    args = parser.parse_args()
    results = []
    for episode in args.cases:
        results.append(capture_example(episode, args.source_run, args.browser_root, args.output_root))
        export_gallery(results)


if __name__ == '__main__':
    main()
