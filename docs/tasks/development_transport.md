# 跨海建城：development_transport

本轮 normal，100 个诊断实例，抽样种子 20261102。规则来自容器 civrealm/freeciv-web:1.4 中 savegames/minitask/minitask_T1_task_development_transport_level_normal_id_580.sav 的 [script] 段，以及 SDK freeciv/units/unit_actions.py；SDK 基于 1b144d6ec92a8aaa8e30eee64c881418208a4689。

给 Agent 的目标是使用移民和运输船前往新土地建城。动作前提来自 SDK：board 在城市地块寻找同格合适运输船；方向性的 embark 指定邻格运输船；运输通过移动船只完成；空岸登陆使用合法的 disembark 方向动作。deboard 和 unit_unload 在该实现中要求城市，不能把它们当作空岸登陆动作。动作是否可用及移动力限制以当步菜单为准。

检查过的 normal 存档 max_turn=10、mini_goal=1、初始 mini_score=0。Lua 在我方 city_built 事件中直接设置 is_mini_success=1，并没有额外检查是否跨越大陆，也没有同步把 mini_score 改成 1；[代码摘录](../../reports/failure_diagnosis/rule_evidence.txt) 保留回调及初始化语句。因此成功必须读取原生 success 字段，不能用 mini_score>=mini_goal 代替；运输、装载、登陆是否发生则从玩家可见的逐步状态另行报告。每局记录实际原生期限。

[论文表9](https://arxiv.org/html/2401.10568v2) 的设计是以另一片陆地上新建城市数 N 为分数，N>0 时成功；normal 的回合上限为10。当前容器 Lua 的上述行为与论文定义有差异，尤其 mini_score 没有同步更新，因此该字段不能当作有效的完成度来比较策略。它也不使用建城任务的资源加权分或城址评分矩阵。案例631在第3回合建成新城，原生成功为1而 mini_score 仍为0；案例351到第10回合未建成新城，原生成功为0。图像及逐案原因见[原生界面案例](../../reports/native_examples/README.md)。

期限到达时，脚本先设置失败，再按 mini_score 与 mini_goal 判断是否成功；游戏结束事件也会处理尚未决的结果。runner 的 2000 步停止线和基础设施故障单独记录，不将其当作原生到期。

保存移民和船的位置、transported/transported_by、移动力、装载/登陆动作、建城与原生事件。观察缺失不解释为单位全部死亡；重复、等待和多单位配合要结合状态分析。Agent 只获得玩家观察，不获得隐藏地图或研究者读取的存档状态。
