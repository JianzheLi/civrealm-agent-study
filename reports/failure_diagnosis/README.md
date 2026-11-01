# 失败诊断与本地精选材料

[打开本地案例浏览入口](index.html) · [中文失败分析](analysis.md)

新增[失败共性分析](../course_report/失败共性分析.md)：用完整100局跨海对照失败与成功。63个未成功实例中54个在建城前失去全部移民且未恢复，53个曾尝试转产；对应逐局指标与证据步骤保存在common_failure_patterns.csv/json。

已下载并核对 19 个完整案例，原始文件约 0.95 GB。包含全部9个原生失败，以及代表性输出失败与成功参照。

每例保留完整观察、实际请求与输出、所有纠错、逐步命令与状态、初末状态和完整状态回放。源目录已有的SDK日志也原样保留，但SDK日志处理器可能跨场景复用，逐局证据以各自steps.jsonl和api_calls.jsonl为准。大文件位于仓库 runs/local_review/development-baseline-v5-20261101/，被Git忽略。精简解释、地图关键帧、进展图和可离线打开的HTML在本目录。

**本轮保持8K生成预算。** 这是固定预算条件下的端到端结果；不将输出失败改写为原生失败，也不把它们从总体成功率分母中删除。

| 案例 | 入选角色 | 完整局结局 | 为什么保留 |
|---|---|---|---|
| [建城349](cases/development_build_city-normal-349/case.md) | 原生失败 | 原生失败 | 唯一建城原生失败：反复探索、误把工程增产当评分提高，最后低于目标建城。 |
| [建城254](cases/development_build_city-normal-254/case.md) | 输出失败 | 输出失败 | 探索过程中普通与纠错输出连续为空，原生游戏尚未结束。 |
| [建城666](cases/development_build_city-normal-666/case.md) | 输出失败 | 输出失败 | 零环境动作即停止，隔离展示输出问题不能被归因于错误游戏操作。 |
| [建城93](cases/development_build_city-normal-93/case.md) | 成功参照 | 原生成功 | 达到目标后因移动力为零合法等待，再就地建城；避免将合理等待误标为拖延。 |
| [建城948](cases/development_build_city-normal-948/case.md) | 成功参照 | 原生成功 | 51次动作、58次调用后仍成功，包含截断JSON后的纠错恢复；与349的长轨迹失败对照。 |
| [跨海976](cases/development_transport-normal-976/case.md) | 输出失败 | 输出失败 | 已装载和载运，粮荒损失移民后的恢复阶段又发生连续空输出。 |
| [跨海351](cases/development_transport-normal-351/case.md) | 原生失败 | 原生失败 | 粮荒损失两名移民，购买生产后仍受城市人口前提限制，明确反馈后继续等待至到期。 |
| [跨海386](cases/development_transport-normal-386/case.md) | 原生失败 | 原生失败 | 已登陆的移民在建城前损失，后续重新生产受人口限制，保留全部原生失败之一。 |
| [跨海197](cases/development_transport-normal-197/case.md) | 原生失败 | 原生失败 | 跨海调用最多的失败：37次动作、59次调用，多次登陆仍未建城，展示高开销恢复过程。 |
| [跨海606](cases/development_transport-normal-606/case.md) | 原生失败 | 原生失败 | 曾登陆，但后续关键单位损失并到期；与从未登陆的失败区别阅读。 |
| [跨海650](cases/development_transport-normal-650/case.md) | 原生失败 | 原生失败 | 登陆、粮荒损失、重建与人口条件相互制约，保留全部原生失败之一。 |
| [跨海689](cases/development_transport-normal-689/case.md) | 原生失败 | 原生失败 | 两次登陆和多次粮荒损失后，重建受人口限制而失败，保留完整恢复过程。 |
| [跨海75](cases/development_transport-normal-75/case.md) | 原生失败 | 原生失败 | 两次登陆但都未完成建城，展示登陆不等于任务完成。 |
| [跨海859](cases/development_transport-normal-859/case.md) | 原生失败 | 原生失败 | 没有完成登陆，移民损失后重建受人口限制；本正式版本原生胜负已知。 |
| [跨海631](cases/development_transport-normal-631/case.md) | 成功参照 | 原生成功 | 同船载运两名移民，粮荒后仍有幸存者在登陆地建城；包含完整同一单位证据链。 |
| [跨海424](cases/development_transport-normal-424/case.md) | 成功参照 | 原生成功 | 初始粮食盈余为零、没有粮荒损失的短成功轨迹，且成功纠正一次截断JSON；展示场景条件差异。 |
| [跨海329](cases/development_transport-normal-329/case.md) | 动作语义/初始条件 | 输出失败 | 初始无运输船；前两次把plant误认为建城，随后移民损失，最后输出失败。 |
| [跨海665](cases/development_transport-normal-665/case.md) | 协议异常后成功 | 原生成功 | 一次finish_reason=stop的最终输出包含多段JSON及额外文本，严格解析失败，纠错后继续并原生成功。 |
| [跨海999](cases/development_transport-normal-999/case.md) | 未触顶空响应 | 输出失败 | 一次finish_reason=stop、5533个思考tokens即返回空内容，纠错后继续，后来才因连续触顶空输出停止；区别两种空响应。 |

## 数据与复现

- cohort_diagnostics.json、episode_diagnostics.csv：全体200局的失败类型、调用统计与初始条件分组。
- common_failure_patterns.csv/json：完整100局跨海的共性统计、指标定义、关键单位损失与登陆/人口提示证据；由scripts/analyze_common_failure_patterns.py只读生成。
- local_case_index.csv/json：精选案例的原始服务器路径和本地相对路径。
- cases/<episode>/：逐决策HTML/Markdown、timeline.json、真实进展图、玩家可见地图关键帧与原始任务说明。
- rule_evidence.txt、action_evidence.txt：原生评分和plant/build_city动作区别的源码片段。
- download_receipt.json：下载时间、逐例文件数与字节数核对；不使用额外哈希。

在服务器加载 scripts/env.sh 后运行 python scripts/prepare_failure_review.py 可重建统计与案例页面；本地 python3 scripts/download_review_cases.py 下载/恢复精选原始文件并重建浏览目录。

精选规则见 selected_cases.json；这是按问题选例，不是新的随机样本，不得据其比例替代全体200局统计。原始JSON中仍保留服务器路径，文件未为本地展示而改写。
