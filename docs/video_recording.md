# 正式展示视频规范

视频用于在汇报中简洁展示 Agent 如何观察、选择合法动作并影响环境，不承担完整实验审计。完整证据以 `steps.jsonl`、`api_calls.jsonl` 和 `episode_result.json` 为准，因此不要求录制前 5 个验证场景或全部正式 episode 的全程画面。

## 录制范围与时长

- 每个任务制作 1 个代表案例，最终成片建议 3–5 分钟。
- 前 5 个 pipeline validation 场景只要求完整轨迹和 EpisodeResult，不要求录像。
- 先完成一部分正式轨迹并阅读结果，再选择有代表性的成功、失败或关键行为案例；不要为了视频改变 Agent 动作。
- 优先使用同一真实 episode 的开局、2–3 个关键决策和结局片段。中间等待过程可以不录或剪除，但必须标注“节选/已剪辑”。
- 如果没有录到合适的真实片段，可以制作 replay 或 state reconstruction，但必须明确标注，且不能替代原始轨迹和统计结果。

若课程之后明确要求连续全程录像，应先更新共享配置和本规范，再决定额外录制范围；不能事后把剪辑视频描述成全程录像。

## 推荐的 3–5 分钟结构

| 时间 | 展示内容 |
| --- | --- |
| 0:00–0:20 | 任务、难度、instance ID、模型、run ID 和 episode ID |
| 0:20–1:00 | 玩家可见初始状态、任务目标和当前合法动作 |
| 1:00–3:20 | 2–3 次关键决策：模型最终 JSON、实际动作、网页反馈和状态变化 |
| 3:20–4:20 | 原生终局，或轨迹中的最终状态与停止原因 |
| 4:20–5:00 | 本案例表现、调用/token/耗时和一个局限；可与汇总图衔接 |

不展示或讲解模型内部思维链。只展示模型返回的简短 `reason`、动作编号、实际命令和环境反馈。

## 实际录制方式

推荐先正常采集正式轨迹，再从候选案例中选择一个 episode。对于后续新运行的展示案例，可分段录制：

1. 在 reset 前开始录制，保留任务标识和初始状态。
2. 录下开局的 1–2 次真实决策后暂停录制。
3. 观察运行，在关键战斗、策略变化或接近终局时恢复录制。
4. 录下原生结果或 runner 停止摘要，确认轨迹已经落盘。
5. 将实际片段剪成短视频，并在片头或字幕写明“实际运行节选，非连续全程录像”。

如果展示时需要现场演示，只运行一段短 live demo，并明确它不是统计样本的完整终局；正式结果仍引用已保存的 EpisodeResult。

## 画面必须包含

- Freeciv 网页中的玩家可见地图、单位/城市和任务状态。
- 当前任务、难度与 instance ID。
- 至少两次“观察/合法动作 → 模型最终 JSON → 实际命令 → 环境反馈”的完整对应。
- 可追溯的 run ID、episode ID 和关键 env step。
- 对应 EpisodeResult 的原生成功/失败、停止原因或仍未决状态。

不得展示 API Key、环境变量值、个人聊天、浏览器密码、通知或其他私人窗口。不要向模型输入或在分析中使用玩家不可见的全局信息。

## 文件与索引

原始片段和最终成片建议放在：

```text
runs/videos/presentation/<task_type>/<episode_id>/raw/
runs/videos/presentation/<task_type>/<episode_id>/final.mp4
```

原始录制优先使用 MKV，避免程序异常造成整段损坏；最终交付为 MP4。每个最终视频进入 `video_index.csv`：

```text
run_id,episode_id,task_type,instance_id,capture_type,coverage,edited,path,sha256,notes
```

`capture_type` 使用：

- `actual_gameplay_highlights`：同一真实运行的节选，推荐用于正式展示。
- `live_demo`：汇报时的短现场演示，不代表完整统计样本。
- `replay`：事后重新运行或回放，必须标注。
- `state_reconstruction`：根据轨迹重建画面，必须标注。

`coverage` 写明 `opening+key_steps+terminal`、`opening+key_steps` 等实际覆盖范围；`edited` 对剪辑视频填写 `true`。视频文件不进入 Git，Git 中只保存精简索引、必要截图和报告引用。最终成片至少保留一份额外备份。

## 交付前检查

1. 视频中的 run/episode/instance 与轨迹完全一致。
2. 关键动作能在 `steps.jsonl` 中按 env step 找到。
3. 结局和停止原因与 `episode_result.json` 一致。
4. 所有跳切、倍速、replay 和重建画面均有明确标注。
5. 没有凭据、通知或私人信息。
6. 最终时长适合汇报，并已计算 SHA-256、填写 `video_index.csv`。
