# 报告图表与来源

每张图同时提供PNG与PDF。图中的实验数据均来自正式v5运行；不包含准备版本或示意样本。

| 编号 | 文件前缀 | 数据与转换 | 原始图或生成入口 |
|---|---|---|---|
| 图1 | fig01_outcomes | 两任务各100局的互斥停止类型计数 | reports/development/figures/outcome_distribution；episode_results.csv |
| 图2 | fig02_decision_flow | 2225逻辑决策、501纠错、427恢复、74输出失败的计数流程 | reports/failure_diagnosis/cohort_diagnostics.json；本目录上一级build_assets.py |
| 图3 | fig03_resources | 全部200局调用、动作、单局耗时散点；确定性的横向偏移仅减少重叠 | reports/development/figures/resource_distribution；episode_results.csv |
| 图4 | fig04_city349_progress | 建城349的逐提交候选分数、目标与原生回合 | reports/development/cases/development_build_city-normal-349/progress；对应steps.jsonl |
| 图5 | fig05_transport631_keyframes | 跨海631在开始、首次结束回合后、建城后的玩家可见地图 | reports/development/cases/development_transport-normal-631/keyframes；对应initial.json与steps.jsonl |
| 共性对照图 | fig_common_failure_patterns | 全部100局跨海按结局分组，格内显示事件数/组内场景数与比例；各行可重叠 | reports/failure_diagnosis/common_failure_patterns.json；build_assets.py |
| 图S1 | figS1_observable_labels | 多选可观察标签，每任务分母100；标签不是互斥因果归因 | reports/development/figures/observable_labels；failure_annotations.csv |

图1、3、4、5和S1为原有真实数据图的直接复制；图2和共性对照图由本轮实际计数生成。地图只显示玩家已知地块，是轨迹状态重建，不是游戏屏幕录制。
