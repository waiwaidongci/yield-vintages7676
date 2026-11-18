# 连续对照试验（增量）

在既有表基础上新增四张表，SQLAlchemy 启动时自动创建；已有数据库升级前请先备份。

- `trial_processes`：工艺名称唯一、`alpha_cap` 为工艺总误报上限。登记后不可改写，只允许另立工艺。
- `yield_trials`：一次试验的登记（对照线、试验线、冻结口径快照、期间、预留额度 `alpha`）、当前状态
  `pending/running/stopped/cancelled`、判定 `pending/continue/efficacy/manual`、累计批次与查看次数、最新证据强度。
- `trial_observations`：已纳入的完整批次。`(trial_id, batch_key)` 唯一，`batch_key = 日期|班次`；
  保存两臂聚合的分子/分母/投入与纳入时的底稿快照。批次一旦写入即冻结，底稿后续更正不回写。
- `trial_looks`：每次序贯查看的 p 值、证据强度、判定与本次新增批次；`(trial_id, look_index)` 唯一。

额度语义：试验登记即占用预留额度，取消/停试/重开均不返还；`Σ yield_trials.alpha ≤ trial_processes.alpha_cap`
即为“同一工艺多项并行试验的误报总概率受登记上限约束”（并集界，靠登记时行锁校验保证并发下不超卖）。

已有 `yield_lots / denominator_policies / yield_runs / delivery_schedules / deliveries` 结构不变，
旧报告与旧交付不受影响。
