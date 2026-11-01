# battle_ancient_era：古代陆战

## 基本信息

| 项目 | 内容 |
| --- | --- |
| task_type | `battle_ancient_era` |
| difficulty | `normal` |
| 规则来源 | CivRealm 小游戏存档 `minitask_T1_task_battle_ancient_era_level_normal_id_<id>.sav` 的 Lua 任务脚本；已在 songluo 本地环境抽查 normal ID 0、1、999，核验镜像 ID 为 `sha256:d4ce74d7eb7401ff2383761484f4ccb12b5cd0d9193f4cc4be3c8a0ab257f4a5`，该 ID 是核验证据而非全组强制部署方式 |
| 典型初始条件 | 双方各有 1 个 Leader 和若干古代陆军单位，没有城市。抽查样本的我方/敌方单位数分别为 11/10、12/13、13/14；具体兵种、位置和数量按实例变化 |
| 原生回合期限 | Lua 变量 `max_turn = 50`；`turn_begin` 在 `turn >= max_turn` 时执行原生结算 |

## 给 Agent 的目标与规则

使用现有古代陆军保护己方 Leader，并消灭敌军。每次只能从当前环境提供的合法动作映射中选择一个动作；移动到敌军所在或可攻击位置所产生的战斗结果由 Freeciv 原生规则决定。

任务开场文本写的是“保护己方 Leader 并摧毁敌方 Leader”。但实际 Lua 成功公式要求敌方单位全部归零，二者不能混写：Agent 可以收到原始任务目标，评测必须使用环境返回的原生成功字段。

## 原生结局与评分

- `human_cnt` 和 `ai_cnt` 分别为我方与敌方当前单位数，Leader 也计入单位数。
- `mini_score = human_cnt - ai_cnt`，越大表示兵力差越有利。
- `mini_goal = human_cnt`。脚本以 `mini_score >= mini_goal` 判定成功；在正常计数下，这等价于 `ai_cnt == 0`。
- 任一 Leader 损失会立即更新 `human_leader_alive` 或 `ai_leader_alive`，重新计数并触发结算消息；Lua 随后仍调用上述分数判定，因此不能仅凭“敌方 Leader 已死亡”自行标为成功。
- 到第 50 回合仍会按同一公式结算。没有清空敌方单位时为原生失败，不是 runner 截断。
- `is_mini_success` 是最终评测依据；`mini_score` 用于描述进展，不能替代原生成功状态。

## 玩家可见信息与动作

统一 Agent 输入只使用玩家侧接口提供的信息：当前回合、Lua 播报的任务指标、己方可行动单位，以及 `LLMWrapper` 为每个单位生成的局部地图和较粗粒度的周边块摘要。摘要包含可见地形、设施、单位类型、单位归属和城市归属；未探索区域保留为未探索，不向模型补入存档中的全局坐标或敌军隐藏状态。

相关动作主要是当前单位的八方向移动及环境当时提供的其他合法单位动作。攻击通常由合法移动/原生动作触发。动作名称和 actor ID 必须来自当步有序 `legal_actions`，不能复用上一步编号，也不能依据完整存档为模型筛选路线。

## 进展证据与需要记录的事件

逐步保存玩家可见的双方单位、单位类型、位置摘要、生命/移动状态、合法动作、实际执行命令和战斗反馈。每次伤亡记录损失方、单位类型、Leader 标志，以及伤亡前后的 `human_cnt`、`ai_cnt`、`mini_score`、`is_mini_success`。

以下事件分别记录，不能互相替代：接近敌军、发起攻击、普通单位损失、任一 Leader 损失、敌军单位清零、达到第 50 回合和原生任务终局。若开场文字目标与 Lua 判定导致状态不一致，保留对应步骤作为规则差异案例。

## 运行与分析说明

采用 [研究设计](../llm_study_design.md) 的原生终局、2,000 步宽停止线和无每局 API 调用上限。记录要求见 [日志规范](../logging_spec.md)。50 回合是本任务的原生期限，2,000 env steps 只是 runner 的防失控停止线，两者不得合并。

分析至少报告原生成功率、最终兵力差、双方伤亡、Leader 存活状态、到达终局所需 env steps/API 调用与 token。对“已击杀敌方 Leader 但仍有敌军”的轨迹单独标记，不预先把它解释为模型错误。
