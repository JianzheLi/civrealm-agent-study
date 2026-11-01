# 第一轮配置与场景清单

development.json 固定两个发展任务的统一模型与运行设置；development_tasks.json 保存相同任务目标及规则来源；development_instances.json 保存各 100 个 normal 实例与抽样种子，前五个包含在总数中。游戏随机设置与抽样种子分别记录。修改正式配置需使用可区分的新 run_id。


## 新批次：32 条历史＋16K 输出

`development_history32_output16k.json` 是在同一发展任务清单和目标上可直接选用的新配置：`history_length=32`、`max_tokens=16384`，使用独立 `run_id` 和 `method`。其余模型、提示词、观察、超时和重试设置与 `development.json` 相同。它不是旧批次的结果替代品。

`load_config()`、监督脚本和历史报告入口仍默认读取原来的 `development.json`，不会因拉取本次变更自动重跑已完成实验。新配置的显式调用方法见 [采集约定](../docs/history32_output16k.md)。战斗和外交负责人应在各自配置中同步这两个参数和独立版本标识，保留各自任务、规则及实例清单。
