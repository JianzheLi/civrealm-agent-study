# 建城：development_build_city

本轮 normal，100 个诊断实例，抽样种子 20261101。研究者读取的规则来自容器 civrealm/freeciv-web:1.4 中 savegames/minitask/minitask_T1_task_development_build_city_level_normal_id_754.sav 的 [script] 段；SDK 基于 1b144d6ec92a8aaa8e30eee64c881418208a4689。

Agent 控制移民探索玩家可见地图，选择资源条件较好的位置建城。当前候选位置的 mini_score 与目标 mini_goal 是环境反馈；可合法建城不代表该位置已经满足分数目标。移动耗费移动力，是否可执行以当步合法动作列表为准。

## 分数含义与计算规则

[CivRealm 论文附录A.2、表9](https://arxiv.org/html/2401.10568v2) 将单地块的粮食、生产、贸易产出分别记为 F、P、T，先计算加权分，再对城址对应范围中评分最高的6块求和：

$$
\rho_i=0.4F_i+0.4P_i+0.2T_i,\qquad S_c=\sum_{i\in\mathrm{top6}(c)}\rho_i.
$$

论文把成功门槛写成候选城址评分分布的80%分位数。这体现了任务的选址目标：找到资源潜力较好的城址。这里的分数不是百分制，也不是城市当回合实际使用地块的净产出，更不是完整文明对局的综合分。

本轮容器存档的实际运行方式是**查询预置评分矩阵**。存档已经保存 map_conf 和 score_goal；Lua 不在每次行动后重新计算资源加权分或分位数。对游戏坐标(x,y)，其规则是：

```lua
-- 移动后反馈当前位置的分数，建城时读取城市位置的分数
score = map_conf[math.floor(y + 1)][math.floor(x + 1)]
-- 在建城事件中判断是否达标
is_mini_success = (score >= score_goal - 0.0001) and 1 or 0
```

因此，“低分”具体指所选城址的表内分数低于该实例的目标。修路或开矿不会更新这张表，不能据此推断 mini_score 会增加。论文公式解释评分设计；本轮逐局数值与结局以存档矩阵、实际 mini_goal 和原生反馈为准。尚未取得独立存档生成器源码，未从截图反推或编造各地块对分数的贡献。

## 终局与分析边界

原生 city_built 回调在建城后结束任务，以城市位置的脚本评分与 score_goal 比较（容差 0.0001）。低分建城也是原生终局，不能另换策略继续。检查过的 normal 存档 max_turn=30、score_goal=6.0；每局仍从反馈记录实际期限与目标，不把某个存档的数值当作所有实例的保证。到期及游戏结束处理以脚本输出为准。

只按原生 success/is_mini_success 统计成功。runner 的 2000 步停止线是独立的运行停止原因，不能改写原生未知状态。关闭我方 advisor，不使用规则策略代操。

输入包含官方语言视图、已知地块、单位/城市、合法动作和最近四次反馈。存档中的 map_conf 评分矩阵和未发现地块不进入模型输入。评分变化、移民位置、最终建城动作与原生结局用于案例分析；合理探索或等待需结合移动力和回合解释。

首轮案例复核进一步读取 normal ID 349 的原始脚本：get_build_city_msg 第110行和 get_unit_reward 第142行均按地块坐标直接查询预置 map_conf；[代码摘录](../../reports/failure_diagnosis/rule_evidence.txt) 保留行号并省略隐藏地图值。另核实 ID 93 的(7,5)查表值6.2、目标6.2；ID 349 的(9,3)查表值5.6、目标6.0。对应成功/失败截图及解释见[原生界面案例](../../reports/native_examples/README.md)。这是研究者事后核查的规则解释，v5 固定批次的 Agent 任务说明与输入配置未在采集中途修改；诊断时需同时考虑任务说明是否充分。
