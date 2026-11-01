# OpenRouter：DeepSeek V4.1 Flash 1017

`configs/development_openrouter.json` 是可显式选用的配置，使用同一组发展任务和实例，32 条动作历史、16K 输出、high 思考，以及独立 run_id。单次请求超时设为 600 秒，为较长生成和排队留时间；这与直连配置的 180 秒不同，须在报告中说明。

- 接口：`https://openrouter.ai/api/v1/chat/completions`
- 模型：`deepseek/deepseek-v4.1-flash-1017`
- 密钥：只读取进程环境中的 `OPENROUTER_API_KEY`；不会退回读取 `DEEPSEEK_API_KEY`。
- 参数：`reasoning.effort=high`、`max_tokens=16384`、`top_p=1`、JSON 输出；要求服务商支持所传参数。
- 路由：使用同一模型的默认服务商路由，不配置其他模型 fallback；实际服务商可能变化。

这是供应商接口适配，动作选择、输入内容、JSON 纠错次数、游戏规则和环境不改变。默认 `development.json`、原监督入口及旧报告仍使用 DeepSeek 直连 4 条历史＋8K。

## 安全设置密钥与启动

先按自己的部署设置游戏服务、Python 环境、SDK 和代码版本记录。密钥只在本机或自己的服务器终端输入，不粘贴进聊天、源码、配置或 PR。以下在 Bash 中执行；输入不回显，密钥不进入命令历史：

```bash
read -r -s -p 'OpenRouter API key: ' OPENROUTER_API_KEY
export OPENROUTER_API_KEY
printf '\n'
python scripts/collect_config.py \
  --config configs/development_openrouter.json \
  --task development_build_city --limit 5
unset OPENROUTER_API_KEY
```

这个命令会实际调用收费模型，只运行该任务前 5 个场景，不自动进入 100 局。`collect_config.py` 将配置以 Python 参数传给共享 runner，清除命令行参数后才导入游戏 SDK，避免 SDK 误读 `--config`。现有运行会按各自启动时的配置继续。

跨海任务使用 `development_transport`。战斗或外交负责人复制这组供应商参数到自己的配置，保留任务、目标与实例清单，并选择独立 run_id。不要把发展任务清单直接用于其他任务。

原监督、远程启动和分析脚本仍绑定原配置；本入口不自动部署 SDK，也不自动生成新批次汇总。原始记录在新 run_id 下，后续分析需显式指定自己的数据与报告目录。

## 调用与费用记录

每次实际请求仍写入 `api_calls.jsonl`。OpenRouter 记录包含：

- 请求模型、实际返回模型、实际发送的 reasoning/provider 参数。
- `gateway`、`provider`、`response_id`，便于核对服务商和请求。
- `usage_raw` 保存返回用量，`usage` 映射报告明确给出的缓存命中/未命中字段；未提供的不补零。
- `usage.cost` 作为单次已报告费用，标记 `openrouter_reported`；缺失记 unknown，不套用官方直连价格。
- `finish_reason`、HTTP 状态、供应商数字错误码及数字形式的 `Retry-After` 秒数。HTTP 200 响应体内的 error 也归为接口失败，已返回的计费信息仍保留。

日志不保存请求认证头、完整错误响应体或错误消息。密钥只用于客户端鉴权。

## 错误和验证边界

SDK 隐式重试仍关闭（`max_retries=0`），JSON 输出纠错保留原规则；未新增请求级退避。接口异常沿用共享 runner 的基础设施异常处理，可能重新尝试整局。因此大量 429 时应先降并发，不应把接口失败解释成游戏策略失败。OpenRouter 并发与额度不能直接沿用 DeepSeek 官方直连的限制。

配置及路由偏好会随 run manifest 冻结；更换供应商、模型、输出/历史预算或超时应使用新 run_id。默认路由的实际服务商可变化，须按账本核查，不能声称等同于官方直连。

离线测试使用模拟 HTTP 响应，验证参数、密钥隔离、纠错、用量、HTTP 200 内嵌错误与 429 记录。它们不证明真实高并发稳定性或游戏胜率。项目原有的截图/状态观察和历史规则不因接入 OpenRouter 而改变。

## 官方文档

- [模型与服务商](https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017)
- [OpenAI SDK 接入](https://openrouter.ai/docs/guides/community/openai-sdk)
- [推理预算](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
- [路由参数](https://openrouter.ai/docs/guides/routing/provider-selection)
- [错误处理](https://openrouter.ai/docs/api/reference/errors-and-debugging)
