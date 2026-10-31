# 共享设计文档

根目录 [README](../README.md) 是新成员的整体指南：研究问题、阶段操作、交付物、宽松限制、记录清单和最后的分工。

- [tasks/](tasks/README.md)：五种任务的原生规则、可见信息与评分说明；从 [模板](tasks/TEMPLATE.md) 开始填写。
- [interfaces.md](interfaces.md)：环境、Agent、执行器和记录模块交接的数据。
- [logging_spec.md](logging_spec.md)：每步、每次 API 请求、每局的记录及统计口径。
- [experiment_protocol.md](experiment_protocol.md)：诊断、开发与独立测试的边界，比较和异常约定。
- [llm_study_design.md](llm_study_design.md)：100 局/任务、模型参数、宽松停止线和费用安排。

先按负责的模块阅读对应文档，实现或修改接口时同步相关约定。当前文档是设计契约，尚未代表可运行实现；真实入口和输出生成后再补上。
