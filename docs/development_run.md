# 两个发展任务：运行与交付

本轮实现负责建城和跨海建城各 100 局。代码完成、原生链路检查、付费采集和全部交付是不同状态；实际进度以服务器 runtime/collection_status.json 与 reports/development/summary.json 为准。未生成结果时不能称为已采集。

## 本地部署

```bash
python3 scripts/sync.py push
```

服务器目录为 /home/ubuntu/jianzheli/University/conginitve_reasoning/civrealm-agent-study，物理位置在数据盘。部署复制独立 SDK 并移除旧的 128 步截断，保留原有连接关闭修复，不修改旧 civilization 项目。复用 /home/ubuntu/jianzheli/University/envs/civrealm Python 环境和 127.0.0.1:18080 游戏服务。用户已确认首五局后每任务 4 个 CPU 进程，共 8 局并行，实例清单不变。

基础版本 v5 将科技观察中重复的完整单位/建筑定义改为名称列表，其余可见科技状态、前置关系、研究目标保留；模型输入不包含原始全套 rules。标准 SDK 观察省略装载关系，因此另从我方已可见单位的原生包记录 transported、transported_by、occupied，并提供给统一基础 Agent。移动力与生命使用标准观察的 moves_left、health 字段。通用游戏通知（如维护费、单位损失、动作反馈）按决策保存增量，并进入最近四次反馈；初始与最终状态另存完整玩家通知。完整原始观察仍在轨迹中。v4 曾错误地将 SDK 每回合清空的通知列表当成累计列表；v5 在独立 SDK 中保留该列表，跨回合游标不再丢失通知，不改变 Lua 回合或任务规则。v4 的所有已执行实例按修复后配置重采，旧记录仅保留为被替换版本。v1–v4 的旧诊断尝试（包括已结束场景、中断和故障）保留，费用计入全部调用，但不混入 v5 的 200 局策略结果。

## 启动

本页原有启动、监督和汇总命令仍针对 `development.json` 的 4 条历史＋8K 批次。新批次采用 32 条历史＋16K 时，使用 [独立配置与显式启动方法](history32_output16k.md)，不要把新结果写入旧 run_id 或覆盖已有报告。

本地已设置 DEEPSEEK_API_KEY 时直接启动；否则终端隐藏输入：

```bash
python3 scripts/launch_remote.py
```

macOS 桌面可使用隐藏输入窗口：

```bash
python3 scripts/launch_remote.py --macos-dialog
```

密钥通过 SSH stdin 注入远程监督进程及其子进程环境，不写入文件或日志。重复启动会由监督进程锁拒绝。启动后先完成每任务前 5 局并检查证据和调用计数，随后自动续跑至每任务 100 局，最后生成分析。初始五局包含在正式场景内；若必要修复改变了基础配置，须更新 run_id 并保留旧尝试，按最终设置重新采集受影响场景。

首次准备可在服务器检查原生链路（无 API 调用，记录在 runs/preflight，不混入策略结果）：

```bash
source scripts/env.sh
python -m civstudy.probe
python -m unittest discover -s tests -v
```

监督进程调用的采集入口也可单独运行，前提是其进程环境已有密钥：

```bash
python -m civstudy.runner --task development_build_city
python -m civstudy.runner --task development_transport
```

同一 run_id 会跳过已有策略结局，仅对基础设施故障最多保留两次尝试；不覆盖策略失败或截断。已有未完成尝试保留，缺失实例单列。修改参数或提示词后使用新 run_id。

## 汇总与下载

```bash
# 服务器，已有 source scripts/env.sh
python -m civstudy.analysis
# 本地
python3 scripts/sync.py pull
```

reports/development/ 保存逐局表、全部尝试表、任务汇总、未完成清单、问题标签、案例索引、五类静态图和中文报告。完整轨迹、每次请求、观察、SDK 日志留在 runs/。SDK 的日志处理器按采集进程复用，后续场景的 root.log 可能写入该进程首个场景的 sdk_logs；逐局证据以各自 steps.jsonl、api_calls.jsonl 和初末状态为准，不能按 SDK 日志所在文件夹推断场景归属。分析入口也会为每个策略结局生成 player_visible_replay.mp4，初始状态和每次决策各一帧，包含未能提交动作的输出失败步骤；这些是轨迹重建，非游戏屏幕录像。video_index.csv 提供原始路径及帧数，完整视频集合默认保留服务器；用户另行指定的19个典型案例已下载至本地 runs/local_review/，详见 reports/failure_diagnosis/README.md，使用 python3 scripts/download_review_cases.py 可恢复下载。单独生成视频可运行 python -m civstudy.replay。案例文件引用原始服务器路径；重建关键帧明确称为玩家可见状态回放。

问题标签 observable_v2 记录停止原因、低分建城、原生到期、载运单位不再可见等直接现象；unchanged_action_repeat 和 available_goal_settlement_deferred 仍需上下文复核。原生成功但没有观察到载人船移动也是描述标签，不自动改变原生成功判定。没有真实策略数据时分析只输出覆盖表和待补报告，不生成示意结果图。

scene_manifest.json 和 scene_index.csv 保留抽样清单与顺序，trajectory_index.csv 定位逐局初末状态、决策轨迹和调用账本。transport_process.csv 为每个跨海策略结果单独记录装载、载人船移动、登陆与同一单位随后建城的有序证据链；证据不足不改变原生成功字段，也不声称确认隐藏地图上的大陆归属。

图表工作流参考 Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. [arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065)。
