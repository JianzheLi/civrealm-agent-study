# 任务说明与填写指南

本轮使用以下五个 normal 任务，只研究 LLM Agent：

- development_build_city：建城。
- development_transport：跨海运输与建城。
- [battle_ancient_era](battle_ancient_era.md)：古代陆战。
- [battle_defend_city](battle_defend_city.md)：守城。
- diplomacy_trade_tech：科技交易。

从 [TEMPLATE.md](TEMPLATE.md) 复制内容，为每个任务创建以官方 task_type 命名的 Markdown 文件。模板已提供字段，但五份任务规则尚待依据真实实现填写。

说明需要包含规则来源、统一任务目标、可见信息、相关动作与前提、原生成功/失败/到期判定、分数和目标含义，以及可作为进展证据的状态变化。原生回合限制与 runner 的宽松动作停止线分开说明。

任务文档不放针对某个测试 ID 的解法，不将全局隐藏存档信息补给 Agent。研究设计与参数见 [../llm_study_design.md](../llm_study_design.md)，事件记录见 [../logging_spec.md](../logging_spec.md)。

参考：[官方小游戏设置](https://bigai-ai.github.io/civrealm/advanced_materials/minigame_setting.html)、[小游戏设计与 Lua 事件](https://bigai-ai.github.io/civrealm/advanced_materials/minigame_create.html)。
