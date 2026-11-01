# 可复现运行入口

所有脚本读取 `configs/` 中的共享、本机和实例配置，不在命令中重复未记录的正式实验设置。先在项目虚拟环境中安装本仓库，再从仓库根目录运行。

```powershell
python -W ignore .\scripts\check_environment.py --probe
python -W ignore .\scripts\smoke_episode.py --task battle_defend_city --instance-id 669
python -W ignore .\scripts\run_episode.py --task battle_defend_city --instance-id 669
python -W ignore .\scripts\run_batch.py --task battle_defend_city --limit 5
```

`run_batch.py` 严格按实例 manifest 顺序运行。新批次的 `--limit N` 只用于前 N 个开发/验证场景；正式 100 局不传 `--limit`。中断或基础设施失败后使用首次输出中的 batch ID 恢复：

```powershell
python -W ignore .\scripts\run_batch.py --task battle_defend_city --resume <BATCH_ID>
```

恢复时必须使用相同配置和运行限制。已有策略结局会跳过；`infrastructure_error` 会保留并使用递增 attempt 重新运行。批次目录位于 `<run_root>/batches/<batch_id>/`，包含 `batch_manifest.json`、`episode_results.jsonl`、`episode_results.csv` 和 `batch_status.json`。每个 attempt 的完整轨迹仍位于其 `result_dir`。批量失败标签、图表和案例导出尚待实现。
