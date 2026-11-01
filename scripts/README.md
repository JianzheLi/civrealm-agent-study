# 部署与运行入口

sync.py push 上传当前源码并准备独立 SDK；sync.py pull 仅下载精简报告。env.sh 配置服务器 CPU 运行环境。launch_remote.py 读取环境密钥或隐藏输入，经 SSH stdin 交给 receive_launch.py 启动监督进程。bootstrap_remote.py 只修改本项目 SDK。运行步骤见 ../docs/development_run.md。

prepare_failure_review.py 在服务器读取已完成的200局，生成进一步诊断和selected_cases.json指定的逐步页面，不发起模型请求。本地 download_review_cases.py 下载精选完整原始记录与视频至 runs/local_review/，核对文件数/字节数后生成离线浏览目录。说明见 ../reports/failure_diagnosis/README.md。

analyze_common_failure_patterns.py 在服务器只读正式100局跨海轨迹，统计关键移民损失、登陆后损失、恢复操作与人口提示时序；生成 reports/failure_diagnosis/common_failure_patterns.csv/json。不调用模型。共性分析正文见 ../reports/course_report/失败共性分析.md。

原生游戏截图：在服务器加载 scripts/env.sh 后运行 `python -m civstudy.native_examples --output-root runs/native_examples_next`。输出目录使用新名字；`--cases` 可只选某些示例。浏览器目录通过 `--browser-root` 指定，当前服务器为 runtime/tools/browser，复用已有 Chromium 和配套动态库。该入口不读取 API 密钥，不调用模型，仅在新的游戏会话中重放已有动作，关闭弹窗、放大地图后截图。精简截图与来源说明生成到 reports/native_examples/，不替换正式实验或简化状态回放。
