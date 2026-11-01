# Freeciv 原生游戏界面示例

以下是按已有案例动作重新演示时截取的 Freeciv-web 界面，用于展示成功与失败过程。不是第一轮采集当时的原始截图，也不替代正式实验结果；本次不调用模型。

| 案例 | 本次原生结局 | 与原案例结局一致 | 画面 |
| --- | --- | --- | --- |
| development_build_city-normal-93 | 成功 | True | [initial](development_build_city-normal-93/initial.png) · [process](development_build_city-normal-93/process.png) · [final](development_build_city-normal-93/final.png) |
| development_build_city-normal-349 | 原生失败 | True | [initial](development_build_city-normal-349/initial.png) · [process](development_build_city-normal-349/process.png) · [final](development_build_city-normal-349/final.png) |
| development_transport-normal-631 | 成功 | True | [initial](development_transport-normal-631/initial.png) · [process](development_transport-normal-631/process.png) · [final](development_transport-normal-631/final.png) |
| development_transport-normal-351 | 原生失败 | True | [initial](development_transport-normal-351/initial.png) · [process](development_transport-normal-351/process.png) · [before_terminal](development_transport-normal-351/before_terminal.png) · [final](development_transport-normal-351/final.png) |

完整复演与截图元数据见各案例 capture.json。画面通过独立观察者客户端观察玩家视角，界面弹窗已关闭，原生地图显示放大至2.2倍；截图说明在本页和元数据中保留。模型与第一轮行为的分析仍应引用原轨迹。

## 分数怎么算，为什么有城市仍会失败

**建城任务**的分数衡量城址的资源潜力。论文表9先对地块计算粮食、生产和贸易的加权分，再取城址对应范围内评分最高的6块求和：

$$
\rho_i=0.4F_i+0.4P_i+0.2T_i,\qquad S_c=\sum_{i\in\mathrm{top6}(c)}\rho_i
$$

其中 F、P、T 分别是地块的粮食、生产、贸易产出。论文把目标定义为候选城址评分分布的80%分位数；具体实例的实际目标读取 mini_goal。[论文附录A.2、表9](https://arxiv.org/html/2401.10568v2)

当前存档已把位置分和目标预先写好；实际运行的 Lua 按坐标查表，并在建城时判定：

```lua
score = map_conf[y + 1][x + 1]
success = (score >= score_goal - 0.0001)  -- 在建城事件中判定
```

所以“低分”指所选位置低于该局门槛。修路、开矿不会更新这张预置表；城市当回合的净粮食、净生产也不能直接代入，代替城址的6地块评分。分数达到门槛后还需要实际建城；在低分位置建城会立即结束任务。完整地图评分表未提供给 Agent。[建城规则及脚本证据](../../docs/tasks/development_build_city.md)

**跨海任务**按期限内是否触发我方新建城事件判成功，当前脚本没有额外核查大陆变化，且建城后只改成功标志，没有把 mini_score 从0改为1。因此用原生 success/is_mini_success 判结局，另外检查登船、航行、登陆和建城的轨迹。[跨海规则](../../docs/tasks/development_transport.md)

| 案例 | 城址分或原始分数字段 | 目标 | 原生成功标志 | 判定理由 |
| --- | ---: | ---: | ---: | --- |
| 建城93 | 6.2 | 6.2 | 1 | 在达标位置建城 |
| 建城349 | 5.6 | 6.0 | 0 | 所选城址低于目标0.4 |
| 跨海631 | 0 | 1 | 1 | 已建新城，分数字段未更新 |
| 跨海351 | 0 | 1 | 0 | 到期未建新城 |

这些是任务自己的 mini_score，与完整文明对局的综合分数分开统计。下文行为原因引用第一轮轨迹，截图仅展示相应复演的游戏状态。

## 建城成功（93）

第4回合在(7,5)建成 Weimar，城址分6.2，目标6.2，达到门槛后原生判定成功。这张图应看新城的位置；6.2衡量该位置的预设资源潜力。

[原轨迹与逐步决策](../failure_diagnosis/cases/development_build_city-normal-93/case.md)

![建城成功的原生地图状态](development_build_city-normal-93/final.png)

## 建城失败（349）

第29回合在(9,3)建成 Erfurt，但城址分5.6低于目标6.0，还差0.4，原生判定失败。因此画面里确实有城市。原轨迹决策0048–0054尝试修路、开矿或等待，理由是工程可补足0.4分；该假设与预置评分表的规则不符。决策0055在分数仍为5.6时建城，触发终局。可分析的问题是对评分机制的误解及多次反馈后的策略修正；基线说明未明示静态查表规则，需同时考虑任务说明是否充分。

[原轨迹与逐步决策](../failure_diagnosis/cases/development_build_city-normal-349/case.md)

![建城失败的原生地图状态](development_build_city-normal-349/final.png)

## 跨海建城成功（631）

第3回合移民111在(5,3)建成新城 Osnabrück，原生成功标志为1；原轨迹也有该移民的登船、船只移动、登陆与建城证据。日志仍显示 mini_score=0、mini_goal=1，这是当前脚本未同步更新分数字段，不能据此判成失败。

[原轨迹与逐步决策](../failure_diagnosis/cases/development_transport-normal-631/case.md)

![跨海建城成功的原生地图状态](development_transport-normal-631/final.png)

## 跨海建城失败（351）

到第10回合期限仍未建成目标新城，原生成功标志为0。画面中的 Hannover 是初始城市。原轨迹中已有移民因饥荒损失，之后尝试重新生产并购买移民；城市人口只有1，原生通知明确提示人口不足，盾牌达到45也无法完成移民生产。模型随后仍等待完工，最终未恢复可用于建城的移民。可分析的问题是单位维护、生产前提的联合约束，以及收到失败反馈后是否修改计划。

[原轨迹与逐步决策](../failure_diagnosis/cases/development_transport-normal-351/case.md)

![跨海建城失败的原生地图状态](development_transport-normal-351/final.png)
