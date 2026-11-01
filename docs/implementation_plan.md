# 第一轮实现目录、模块职责与执行计划

本文把现有研究协议落实为代码和数据组织方案。当前正式环境允许各成员使用自己的本地部署，但每次运行必须记录环境版本、代码版本、配置、提示词和实例清单。环境检查、单局 Agent 和可恢复批次已实现；分析与可视化部分仍是后续计划。

## 1. 目录结构

```text
civrealm-agent-study/
├── .gitignore
├── README.md
├── CONTRIBUTING.md
├── pyproject.toml                         # 已有：安装信息与依赖范围
├── configs/
│   ├── README.md
│   ├── first_round.yaml                   # 已有：共享首轮参数草案
│   ├── local.example.yaml                 # 已有：本机连接与版本模板
│   ├── local.yaml                         # 本机文件，Git 忽略
│   └── instances/
│       ├── junhaozhang_first_round.yaml   # 已有：古代陆战的 100 局清单
│       └── songluo_first_round.yaml       # 已有：守城的 100 局清单
├── prompts/
│   ├── README.md
│   ├── baseline.md                        # 已有：统一基础提示词
│   └── correction.md                      # 已有：一次输出纠错提示词
├── src/
│   ├── README.md
│   └── civrealm_agent_study/
│       ├── __init__.py
│       ├── config.py                      # 已有：加载和校验共享/本机配置
│       ├── env.py                         # 已有：CivRealm 连接和环境适配
│       ├── agent.py                       # 已有：DeepSeek 请求与输出解析
│       ├── runner.py                      # 已有：逐局决策循环和停止条件
│       ├── batch.py                       # 已有：可恢复批次和精简汇总
│       ├── trace.py                       # 已有：逐步/API/结果记录和原子写入
│       └── analysis.py                    # 计划：逐局表、汇总和案例索引
├── scripts/
│   ├── README.md
│   ├── check_environment.py               # 已有：本机版本与链路自检
│   ├── smoke_episode.py                   # 已有：无 API 的单局短链路
│   ├── run_episode.py                     # 已有：运行一个指定实例
│   ├── run_batch.py                       # 已有：按 manifest 运行与恢复批次
│   └── summarize.py                       # 计划：生成精简结果与统计
├── docs/
│   ├── implementation_plan.md             # 本文
│   ├── video_recording.md                  # 正式展示短视频规范
│   ├── interfaces.md
│   ├── logging_spec.md
│   ├── experiment_protocol.md
│   └── tasks/
│       ├── battle_ancient_era.md
│       └── battle_defend_city.md
├── reports/
│   ├── README.md
│   └── <run_id>/                          # 计划：可提交的精简结果和图
└── runs/                                  # 本机原始轨迹，Git 忽略
    ├── <run_id>/
    │   ├── manifest.json
    │   └── episodes/
    │       └── <episode_id>/
    │           ├── steps.jsonl
    │           ├── api_calls.jsonl
    │           └── episode_result.json
    └── batches/<batch_id>/
        ├── batch_manifest.json
        ├── episode_results.jsonl
        ├── episode_results.csv
        └── batch_status.json
```

新增文件时保持这一分层，不为单个成员复制一套 runner，也不建立 `songluo_agent/` 一类个人 pipeline。

## 2. 配置与版本职责

`configs/first_round.yaml` 保存可共享的实验语义：任务、模型参数、历史、输出协议、纠错、网络重试、原生终局、2,000 env steps、日志和存储规则。状态为 `development`，基础提示词和可运行代码完成后才改为冻结版本。

`configs/local.yaml` 保存本机路径、连接方式和环境指纹，并由 Git 忽略。它不能保存 API Key，只保存环境变量名称。runner 在每次运行开始时将解析后的非秘密字段复制到 `manifest.json`，所以原始结果仍能追溯本机环境。

`configs/instances/<member>_first_round.yaml` 的显式列表是运行依据，seed 只是来源记录；加载器按 `local.member` 选择清单。每个任务列表的前 5 个实例用于链路与日志确认，也计入该任务 100 局；若验证期间改变基础配置，受影响实例使用冻结后的版本重采集，旧 attempt 保留。

## 3. 计划模块的功能

### config.py

- 合并共享配置和本机配置，不把本机值写回共享 YAML。
- 校验任务、模型、实例数量、ID 唯一性、路径和必需字段。
- 计算配置、prompt 和实例清单的 SHA-256，写入 RunManifest。
- 检查 `DEEPSEEK_API_KEY` 是否存在，但不读取到日志。

### env.py

- 连接已经启动的 CivRealm/Freeciv 服务，不强制负责启动 Docker。
- 按 task type、normal 和 instance ID reset 环境。
- 输出玩家可见 observation、events、task metrics 和有序 legal actions。
- 把 action ID 精确映射回当步原生命令，每次只提交一个环境动作。
- 返回原生成功、失败或未决状态，不用分数自行覆盖 `is_mini_success`。

### agent.py

- 通过统一入口调用 `deepseek-flash`，保存实际返回模型标识。
- 构造任务说明、当前观察、最近 4 次动作与当步 legal actions。
- 解析 JSON 中的 `action_id` 和简短 `reason`。
- 沿用 CivRealm 基础 Agent 的 actor 调度：每回合按环境顺序处理第一个尚未规划的 actor，模型只在该 actor 的合法动作中选择；进入新游戏回合后清空调度状态。
- JSON 或编号非法时最多纠错一次；仍失败返回 output failure，不执行 fallback。
- 网络错误最多重试一次；网络尝试和输出纠错分别记账。

### runner.py

- 组织 reset、决策、执行、反馈、历史更新和终局检查。
- 原生终局优先；最多 2,000 次 env.step，不设置每局 API 调用上限。
- 区分 native success/failure、output/execution failure、step limit、interrupted 和 infrastructure error。
- 基础设施异常保留 attempt；策略失败不为提高成功率而重跑。
- 预算阈值只阻止开始下一局，不中断已开始的一局。

### trace.py

- 写 RunManifest、StepRecord、ApiCallRecord 和 EpisodeResult。
- 保存实际发送的 messages、原始 content、解析过程、动作映射和环境反馈。
- 使用临时文件加原子替换保存逐局汇总，避免中断产生伪完整结果。
- API usage 缺失记为 unknown，不计成零。

### analysis.py

- 从 EpisodeResult 生成 `episode_results.csv` 和任务汇总。
- 统计原生结局、停止原因、env steps、回合、API 调用、token、耗时和费用。
- 为战斗任务导出双方伤亡、Leader、城市归属和关键步骤索引。
- success@K 从完整轨迹后处理，不把 K 当作运行停止线。

## 4. 数据流

```text
共享 YAML + 本机 YAML + 实例 manifest
                    ↓
              配置校验与哈希
                    ↓
任务存档 → 玩家观察 → 有序合法动作 → DeepSeek JSON
                                         ↓
原生动作 ← action_id 校验与映射 ← 一次纠错（仅在需要时）
    ↓
环境反馈与原生指标 → 四类记录 → 逐局结果 → 批次汇总与案例
```

隐藏地图、完整存档坐标和研究者全局信息不进入模型输入。研究者可以用原始存档核验规则，但必须与 Agent 当时可见证据分开保存。

## 5. 实施阶段和验收条件

### 阶段 0：规则与配置记录

完成两份 battle TaskSpec、共享配置、本机模板和两个 100 局实例清单。验收：YAML 可解析，列表各 100 个且无重复，TaskSpec 链接有效。

### 阶段 1：环境自检和无 API 链路

实现 `config.py`、`env.py` 和 `check_environment.py`。使用每个任务清单的第一个实例 reset，输出任务、回合、metrics、actors 和 legal actions，不调用模型。验收：两个任务均能稳定 reset，输入不含隐藏状态。

### 阶段 2：记录一个真实环境动作

实现最小 `trace.py` 和 `smoke_episode.py`，使用明确标注的测试策略从当步 legal actions 中确定性选择第一个动作并执行一步。该策略只验证管线，不进入正式结果。验收：动作前后观察、原生命令、反馈和未决/终局状态能在同一 episode 关联；无 API 时调用账本为空。

### 阶段 3：单次模型决策

先创建 `prompts/baseline.md` 和 `prompts/correction.md`，再实现 `agent.py` 和最小 `runner.py`，对两个任务各执行一次模型决策。验收：实际 prompt、请求参数、实际模型标识、usage、延迟、JSON、action mapping 和执行反馈均可追溯，没有静默 fallback。

### 阶段 4：每任务前 5 个验证场景

按实例 manifest 顺序运行前 5 个场景，检查完整终局、日志恢复、费用和可视化字段；不要求全程录像。验收：10 局都有 EpisodeResult 和完整轨迹，基础设施异常与策略失败正确区分。若修改基础配置，创建新版本并重采受影响场景。

### 阶段 5：冻结第一轮版本

补齐依赖与真实运行入口，审核并锁定 prompt，把配置状态从 `development` 改为 `frozen`，记录代码 commit、prompt/config/manifest hash 和模型核对日期。验收：从干净环境能够按文档复现一个指定实例。

### 阶段 6：两个 battle 任务各 100 局

按 manifest 继续运行剩余实例，中断后只运行未完成或基础设施失败的 attempt。验收：每任务 planned=100，started、native finished、各类失败、截断、基础设施异常和未运行数量均可对账。

### 阶段 7：分析与交付

生成逐局表、任务汇总、问题标签、案例索引、图表和关键帧/短回放。轨迹分析后每任务选择一个可追溯案例，制作约 3–5 分钟的正式展示视频；剪辑片段和回放必须标注，不冒充完整连续录像。古代陆战单列 Leader 死亡与敌军清零，守城单列提前歼敌成功与守到期限成功。所有图表和视频可回到 run ID、episode ID 和证据步骤。

## 6. 当前边界

- 当前已经具备单局与可恢复批量运行入口，并完成真实短程 API 链路验证；正式前 5 个完整终局和 100 局采集尚未开始，展示视频在轨迹分析后选例制作。
- 各成员可以使用本地环境，但跨任务差异同时可能包含环境版本差异；报告必须附环境指纹，不能把差异全部归因于任务。
- Python 版本暂不要求完全一致，但必须记录；依赖和行为异常时以实际 manifest 排查。
- `configs/local.yaml`、`runs/`、凭据和完整轨迹不上传 Git。
- 所有新实现先满足两个 battle 任务的真实纵向链路，同时保持公共接口，不加入 battle 专用自动策略。
