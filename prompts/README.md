# 基础提示词

baseline_v1.txt 为共用基础提示词；两个任务的规则由 configs/development_tasks.json 提供。最近四次动作与反馈每局清空，不使用上一局的计划或额外反思。基础配置冻结后不按任务失败临时修改提示词。
