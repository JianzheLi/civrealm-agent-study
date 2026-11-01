# 正式运行视频证据规范

视频用于展示 Agent 在关键任务上的实际观察、决策和环境反馈，不替代 JSONL 轨迹或原生终局。第一轮预先录制两个 battle 任务各自 manifest 的前 5 个链路验证场景，共 10 局；默认不录制全部 200 局，以控制存储和人工成本。若课程最终要求全量录制，必须在冻结首轮配置前修改 `configs/first_round.yaml`。

## 录制范围

- 录制实际 Freeciv 网页、当前任务/实例标识和必要的运行状态。
- 不展示 API Key、环境变量值、个人聊天、浏览器密码或其他私人窗口。
- 模型最终 JSON、简短理由、实际命令和原生反馈应能通过同一 run ID、episode ID 在轨迹中查到；不要求在画面中展示内部思维链。
- 正式录制应覆盖从 reset 完成到原生终局或 runner 停止。录制意外中断时保留片段并在索引标注，不伪装为完整视频。

## 文件与索引

本机视频放在：

```text
runs/videos/<run_id>/<episode_id>.mkv
```

优先录制 MKV，避免程序或系统异常时整个文件损坏；交付前可无损 remux 为 MP4。每个视频进入 `video_index.csv`：

```text
run_id,episode_id,task_type,instance_id,capture_type,complete,path,sha256,notes
```

`capture_type` 使用：

- `actual_gameplay`：正式运行时真实录制。
- `replay`：事后重放或重新运行，只用于解释，不能替代正式实验结果。
- `state_reconstruction`：根据轨迹重建的画面，必须明确标注。

视频文件不进入 Git；Git 中只保存精简索引、必要截图和报告引用。视频至少保留一份额外备份。

## 正式运行前检查

1. 打开正确的 Freeciv 页面并确认任务、难度和 instance ID。
2. 关闭或遮挡所有凭据、通知和私人窗口。
3. 确认录制目录、剩余磁盘空间、画面和系统时间。
4. 先开始录制，再启动该 episode；结束后先确认轨迹落盘，再停止录制。
5. 计算 SHA-256，填写 `video_index.csv`，核对 run ID 和 episode ID。

展示案例优先从已经录制的正式场景中选取。若正式视频中没有合适的成功或失败案例，可以额外制作 replay，但报告必须同时引用原始正式轨迹，并把 replay 与统计样本分开。
