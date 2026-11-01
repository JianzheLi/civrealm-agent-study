# 部署与运行入口

sync.py push 上传当前源码并准备独立 SDK；sync.py pull 仅下载精简报告。env.sh 配置服务器 CPU 运行环境。launch_remote.py 读取环境密钥或隐藏输入，经 SSH stdin 交给 receive_launch.py 启动监督进程。bootstrap_remote.py 只修改本项目 SDK。运行步骤见 ../docs/development_run.md。

prepare_failure_review.py 在服务器读取已完成的200局，生成进一步诊断和selected_cases.json指定的逐步页面，不发起模型请求。本地 download_review_cases.py 下载精选完整原始记录与视频至 runs/local_review/，核对文件数/字节数后生成离线浏览目录。说明见 ../reports/failure_diagnosis/README.md。

analyze_common_failure_patterns.py 在服务器只读正式100局跨海轨迹，统计关键移民损失、登陆后损失、恢复操作与人口提示时序；生成 reports/failure_diagnosis/common_failure_patterns.csv/json。不调用模型。共性分析正文见 ../reports/course_report/失败共性分析.md。
