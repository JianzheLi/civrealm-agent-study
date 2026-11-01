# 可复现运行入口

所有脚本读取 `configs/` 中的共享、本机和实例配置，不在命令中重复未记录的正式实验设置。先在项目虚拟环境中安装本仓库，再从仓库根目录运行。

```powershell
python -W ignore .\scripts\check_environment.py --probe
python -W ignore .\scripts\smoke_episode.py --task battle_defend_city --instance-id 669
python -W ignore .\scripts\run_episode.py --task battle_defend_city --instance-id 669
python -W ignore .\scripts\run_batch.py --task battle_defend_city --limit 5 --workers 2
```

`run_batch.py` 严格按实例 manifest 顺序分配场景。`--workers N` 使用 N 个独立 Python 进程，每个 episode 有独立环境、端口和轨迹目录，父进程串行写批次汇总。新批次的 `--limit N` 只用于前 N 个开发/验证场景；正式 100 局不传 `--limit`。中断或基础设施失败后使用启动时输出的 batch ID 恢复，并保持相同 workers 和运行限制：

```powershell
python -W ignore .\scripts\run_batch.py --task battle_defend_city --workers 2 --resume <BATCH_ID>
```

恢复时必须使用相同配置和运行限制。已有策略结局会跳过；`infrastructure_error` 会保留并使用递增 attempt 重新运行。批次目录位于 `<run_root>/batches/<batch_id>/`，包含 `batch_manifest.json`、`episode_results.jsonl`、`episode_results.csv` 和 `batch_status.json`。每个 attempt 的完整轨迹仍位于其 `result_dir`。批量失败标签、图表和案例导出尚待实现。

本地 4 路付费测试只用于开发，先确认配置仍为 `development`，再让前 4 个实例各运行一个游戏回合：

```powershell
python -W ignore .\scripts\run_batch.py --task battle_defend_city --limit 4 --workers 4 --max-game-turns 1
```

观察是否出现 HTTP 429、端口冲突、Docker 内存不足或 `infrastructure_error`。若有 429 或系统明显卡顿，正式批次改用 `--workers 2`。正式采集不传 `--limit` 和 `--max-game-turns`；开发批次不能计入正式结果。
