# 实现模块

实现按 [模块接口](../docs/interfaces.md) 和 [日志规范](../docs/logging_spec.md) 逐步加入，建议划分为：

- env：官方环境与任务适配、玩家观察、合法动作和原生指标。
- agents：统一 DeepSeek 调用、基础 Agent 与明确区分的候选方法。
- runner：逐局循环、执行反馈、停止条件和费用记录。
- trace：逐步证据与逐局汇总的保存。
- analysis：当前先做逐局/逐任务统计、失败分类、案例索引、统计图和地图/事件回放；后续再补配对比较。

当前已实现共享/本机/实例配置校验、CivRealm reset 与 step、actor 调度、DeepSeek 请求和一次输出纠错、单局 runner、逐步/API/结果日志，以及按单任务 manifest 顺序分配的可恢复多进程批次。每个 worker 使用独立进程、环境和轨迹目录，父进程安全汇总 JSONL、CSV 和状态；批次会跳过已有策略结局，只对基础设施失败生成下一 attempt。全组统一使用最新发布的同一 DeepSeek 版本；runner 不设每局 API 调用上限，采用原生终局和 2,000 步宽停止线。失败标签、统计图和案例回放仍待实现。
