# 实现模块

共用 Python 包 civstudy：env 负责原生观察和动作；agent 负责统一请求和逐调用记账；runner 负责采集与尝试保留；supervisor 负责两任务进程和首五局确认；analysis 负责表格、标签、案例和图表；replay 从完整决策轨迹生成玩家可见状态视频，供 analysis 调用。当前配置覆盖两个发展任务，其余任务先补 TaskSpec。运行方式见 ../docs/development_run.md。
