# 模块与日志接口

_设计契约，尚未实现为 Python 类。可以采用数据类或字典；字段语义须一致。_

详细记录、计数和存储规范以 [logging_spec.md](logging_spec.md) 为准。这里说明环境、Agent、执行器与记录模块之间交接什么。

## RunManifest：运行条件

runner 汇总任务、场景清单与划分、代码/提示词/方法版本、模型参数、可控随机设置、停止规则、运行顺序、单次计价来源和输出位置。首轮全组统一使用最新发布的 DeepSeek，分别记录官方参考版本、核对日期、请求别名与实际返回标识。每次运行的轨迹关联对应 manifest，不在同一版本名下静默改变参数。

## TaskSpec：任务定义

| 字段 | 含义 |
| --- | --- |
| task_type / difficulty | 官方任务名，本轮全部 normal |
| objective | 向各比较版本提供的相同任务目标与规则 |
| rules_source | 任务脚本、存档或上游版本来源 |
| visible_information | 玩家可见范围及不能提供的隐藏状态 |
| score_definition / success_definition | 原生分数和目标含义、原生胜负条件 |
| native_turn_limit | 场景自身回合期限及其到期判定 |
| relevant_actions | 分析动作与任务关系的说明；若用于筛选合法动作，须列为方法变化 |

## StepContext：一次决策的输入

| 字段 | 含义 |
| --- | --- |
| run_id / episode_id / attempt_id / decision_id | 运行、局、尝试与决策标识 |
| env_step / game_turn | 本局已提交动作数与当前原生回合 |
| task_type / difficulty / instance_id / game_seed | 场景及可控游戏随机设置；不能固定时明确记录 |
| observation / events | 当前玩家可见观察和事件 |
| legal_actions | 当前有序动作编号到原生命令的映射 |
| task_metrics | 原生小游戏反馈，保留其语义 |
| history | 方法可读的近期动作、进展和反馈 |
| resource_context | 本局剩余环境步数、已用调用和耗时；没有虚构的剩余 API 次数 |

动作编号只对当前映射有效。输入整理后实际发送给模型的 messages 也要保存，不能仅保存整理前的完整观察。

## Decision：Agent 返回

- action_id：当前合法动作列表中的编号。
- reason：简短选择依据。
- expected_effect：可选，预期可观察变化。
- chat：可选，实际要发送的消息和目标。
- call_ids：产生该选择的决策、纠错及额外方法调用关联。

不要求内部思维链。执行器不根据理由补做未选择的策略动作；每次有效选择提交一个原生动作，聊天另计。

## ExecutionResult：环境执行反馈

返回实际原生命令、聊天、时间、明确的执行/拒绝/未知响应、下一观察和事件、任务指标、原生终局以及运行异常。命令被接受不等于任务成功；条约提案或聊天不等于条约执行。

## StepRecord 与 ApiCallRecord：完整证据

StepRecord 合并本次决策的玩家观察、实际请求上下文、legal_actions、原始最终 content、解析和纠错、Decision、实际命令及环境反馈。没有成功提交动作的输出失败也需要保留决策记录。

ApiCallRecord 由统一 API 入口对每次实际请求尝试生成，带 call_id、用途、关联 decision_id、时间、模型、参数、usage、完成原因、错误及费用。实际重试逐次记录；usage 未知要标记，不把它当作零成本。

## EpisodeResult：逐局汇总

| 类别 | 内容 |
| --- | --- |
| 条件 | 方法、代码/提示词/配置版本、任务、难度、ID、随机设置和 run/episode/attempt 标识 |
| 原生状态 | 原生任务/玩家状态、成功字段、mini_score 和 mini_goal |
| 停止 | 原生终局、输出/执行失败、step_limit、interrupted 或 infrastructure_error |
| 游戏资源 | 初始/最终原生回合、经过回合、env_steps、结束回合动作数、聊天数 |
| 模型资源 | 全部请求及用途计数、token、缓存、单局费用估算和未知用量标记 |
| 时间与证据 | 总耗时、请求耗时统计、完整轨迹和账本位置 |

统计计数以 [日志规范](logging_spec.md) 为准。原生状态与运行停止原因独立保存，未决状态不能因 runner 停止而变成原生失败。分析标签另存并关联证据，不修改原始记录。为案例图和回放保留玩家可见地图、位置、原生指标和关键事件，详见 [首轮分析指南](first_round_analysis.md)。
