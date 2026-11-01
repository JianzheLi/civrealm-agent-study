# 建城：development_build_city

本轮 normal，100 个诊断实例，抽样种子 20261101。研究者读取的规则来自容器 civrealm/freeciv-web:1.4 中 savegames/minitask/minitask_T1_task_development_build_city_level_normal_id_754.sav 的 [script] 段；SDK 基于 1b144d6ec92a8aaa8e30eee64c881418208a4689。

Agent 控制移民探索玩家可见地图，选择资源条件较好的位置建城。当前候选位置的 mini_score 与目标 mini_goal 是环境反馈；可合法建城不代表该位置已经满足分数目标。移动耗费移动力，是否可执行以当步合法动作列表为准。

原生 city_built 回调在建城后结束任务，以城市位置的脚本评分与 score_goal 比较（容差 0.0001）。低分建城也是原生终局，不能另换策略继续。检查过的 normal 存档 max_turn=30、score_goal=6.0；每局仍从反馈记录实际期限与目标，不把某个存档的数值当作所有实例的保证。到期及游戏结束处理以脚本输出为准。

只按原生 success/is_mini_success 统计成功。runner 的 2000 步停止线是独立的运行停止原因，不能改写原生未知状态。关闭我方 advisor，不使用规则策略代操。

输入包含官方语言视图、已知地块、单位/城市、合法动作和最近四次反馈。存档中的 map_conf 评分矩阵和未发现地块不进入模型输入。评分变化、移民位置、最终建城动作与原生结局用于案例分析；合理探索或等待需结合移动力和回合解释。

首轮案例复核进一步读取 normal ID 349 的原始脚本：get_build_city_msg 第110行和 get_unit_reward 第142行均按地块坐标直接查询预置 map_conf。该脚本的候选评分不是实时粮食、生产和贸易产出的重新计算；修路或开矿不能据此推断任务评分会上升。这是研究者事后核查的规则解释，v5 固定批次的 Agent 任务说明与输入配置未在采集中途修改。
