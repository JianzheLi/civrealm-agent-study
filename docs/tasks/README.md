# 任务说明

确定一个任务后，为其创建以官方 task_type 命名的 Markdown 文件。范围已确定为两个发展、两个战斗和一个外交任务，全部 normal，当前仅研究 LLM Agent。

建议任务为 `development_build_city`、`development_transport`、`battle_ancient_era`、`battle_defend_city` 与 `diplomacy_trade_tech`。具体名称尚未冻结，选择依据及运行设置见 [../llm_study_design.md](../llm_study_design.md)。

一份任务说明需要交代：

1. 官方类型、难度、初始场景特征及规则来源。
2. 给所有 Agent 相同的自然语言目标。
3. 玩家可见观察、可用动作与行动前提。
4. 原生任务状态、成功/失败条件、得分和目标值的含义。
5. 哪些动作或状态变化可以作为进展证据。
6. 需要记录的任务特定事件，例如城市创建、单位损失或双方接受条约。

这是任务规则文档，不放针对某个测试 ID 的解法。可见信息的摘要不能从研究者读取的全局存档中补入玩家尚未知晓的内容。

参考：[官方小游戏设置](https://bigai-ai.github.io/civrealm/advanced_materials/minigame_setting.html)、[小游戏设计与 Lua 事件](https://bigai-ai.github.io/civrealm/advanced_materials/minigame_create.html)。
