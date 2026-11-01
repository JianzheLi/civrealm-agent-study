# 直接影响采集的检查

test_records.py 用模拟接口检查聊天与游戏动作分开计数、两次无效输出仍留完整记录、原生成功不依赖分数达标、宽停止线保留原生未知状态。模拟数据不进入实验报告。

在服务器加载现有环境后运行：

```bash
source scripts/env.sh
python -m unittest discover -s tests -v
```

原生独立SDK、128步限制移除及跨回合通知保留由 python -m civstudy.probe 检查；真实链路由每任务前5局确认。仅修改报告文字时不重复付费采集。
