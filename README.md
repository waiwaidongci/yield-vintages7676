# 砚泉试制良率口径簿

试制批次一次通过/返工/报废→冻结口径版本与加权透视→主管复核交付；历史快照不随口径改写

## 业务场景与工作流
模拟客户：砚泉研究协作组，12位业务与分析人员。每月研究明细先从`yield-vintages-202611.csv`录入底稿，经口径冻结、Python核算、负责人复核后向业务阅读者交付站内CSV。原有流程依靠人工表格抄算，痛点为口径版本难追溯、重复计算易错、复核与交付脱节。

模块：业务总览、业务底稿、新建口径版本、异步核算与复核、定时交付、站内收件箱、审计、连续对照试验。底稿可新增/修改/删除；口径仅新增版本；报告提交时冻结来源与版本并保存SHA256。定时交付引用已复核报告快照，worker到期写入数据库，业务阅读者下载。

## 算法口径
版本化良率分母规则、加权汇总与按线/班次差异归因。分母规则手算；大批小批汇总不能均值；更新规则旧run不变。

口径版本冻结 · 汇总按分母加权。输入：业务底稿与口径JSON；输出：summary、透视rows、method、warnings。算法实现在`backend/src/services/calculation.py`，输入校验在`validation.py`。固定seed=42，240条合成数据；未对接真实业务系统。修改源数据和新建因子/口径不会改变已提交报告。

## 连续对照试验（避免反复挑线误报）
工艺试验每天看良率、反复挑线容易误报。连续对照页把“看数据”本身纳入统计口径：

1. **开试前登记**：工艺总误报上限（不可改写）、对照线、试验线、冻结口径、期间、本试验预留额度。任何一项越界（预留合计超过工艺上限）直接拒绝登记/启动，旧报告与旧试验照常。
2. **完整批次为观察单位**：同一日期+班次下对照线与试验线都有有效底稿记录才算一个完整批次；缺臂、字段不合法的批次跳过并计数，不纳入也不报错。
3. **随时查看不放大误报**：每纳入一个新完整批次做一次序贯查看（单侧 mSPRT，预登记先验尺度 τ=0.05）。似然比为非负鞅，任意时刻查看、随时提前停试都不增加总误报率。证据强度 = 1 − p，停试阈值 = 本试验预留额度。
4. **多项并行仍受上限约束**：同一工艺的多项试验各自预留额度，额度在登记时即占用；Σ预留 ≤ 工艺总误报上限，由并集界保证任何一项误报的合计概率不超过登记上限。
5. **额度不返还**：取消、提前停试、重开都不返还已占用额度；重开沿用原预留额度，已纳入批次与查看历史保留，后续新批次接着分析。
6. **底稿并发更正**：已纳入批次的聚合值（分子/分母/快照）随批次冻结，底稿后续更正只影响尚未成批或后续新批次。
7. **中断与并发安全**：批次有 `(trial_id, batch_key)` 唯一约束，计算中断后重试按已落库批次续算，不会重复采样；worker 与人工同时推进同一试验时用行锁 + 版本号，只有一人真正写入，另一人返回“未推进”而不重复记查看。

页面展示待开试→进行中→已停止的状态轨道、对照/试验良率、证据强度进度条、本试验预留额度与工艺剩余额度，以及每次查看的 p 值、证据强度与当时判定。worker 每 5 秒自动推进进行中的试验；也可在页面手动“纳入新完整批次并查看”。

## 一天的验收剧本
1. 09:00 admin查看240条seed底稿与具名业务期间。
2. 09:10 analyst添加`yield-vintages-202611.csv`的一条具名业务记录。
3. 09:20 admin在口径版本页登记新版本；旧版本保留。
4. 09:30 analyst命名“十一月核算”并选择期间/版本排队。
5. 09:31 Redis worker真实执行Python计算，展示汇总/透视与口径边界。
6. 09:40 admin核对数值后填写至少4字复核说明。
7. 09:45 admin建立60秒周期计划，worker到期生成站内持久化交付。
8. 09:46 viewer在站内收件箱下载交付CSV；审计页查看操作者与时间。
9. 09:50 admin在连续对照页登记工艺总误报上限 0.05，再登记对照线/试验线/口径与预留 0.02。
10. 09:55 analyst开试；worker 每 5 秒纳入新的完整批次并序贯查看，页面显示证据强度与剩余额度。证据达到预留额度后自动停试；也可随时提前停试，已用额度不返还。

## 快速启动
```sh
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```
前端 http://localhost:18253 ，后端 http://localhost:19253/docs ，数据库宿主端口17753。中文父目录可用。恰好5服务frontend/backend/worker/db/redis；均有真实healthcheck。停止并清空演示数据：`docker compose down -v --remove-orphans`。

|角色|邮箱|密码|权限|
|---|---|---|---|
|admin|admin@demo.local|Demo2026!|全部底稿、口径版本、核算、复核、调度|
|analyst|analyst@demo.local|Demo2026!|底稿增改删、核算、导出；无复核/调度/口径写权限|
|viewer|viewer@demo.local|Demo2026!|只读；仅可下载已复核报告与站内交付|

## 工程结构与开发
Python3.11/FastAPI/SQLAlchemy/Redis，MySQL8；前端原生HTML/CSS/JS ES modules，Nginx代理`/api/`剥前缀至后端。`frontend/src`按api/stores/pages/components/hooks/utils/router/constants/types拆分；`backend/src`按models/schemas/services/controllers/routes/middlewares/config/utils/constants拆分；`backend/scripts/seed_demo.py`自然键幂等且不覆盖用户修改。SQLAlchemy启动创建初始结构，迁移说明在backend/migrations（002 为连续对照试验增量）。

后端开发：在backend安装requirements，设置DATABASE_URL/REDIS_URL/JWT_SECRET，`uvicorn src.main:app --reload`；前端可用Nginx或带同等代理的静态开发服务器。前后端全部业务计算在Python。

环境变量：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、JWT_SECRET（部署替换）、DATABASE_URL、REDIS_URL、SEED_DEMO。`.env`不入Git。数据库/Redis/共享产物为命名卷。共享角色枚举admin/analyst/viewer与状态queued/running/completed/failed分别定义于backend/src/constants/enums.py和frontend/src/constants/enums.js。两个中间件：统一可恢复校验错误、每IP每分钟360请求限流。

## 已知边界
定时分发为站内收件箱；一名worker轮询执行，无外部邮件。调度发送已复核固定报告快照，不自动重算新数据。时间显示Asia/Shanghai。报告导出适合小型数据；底稿全量加载240行演示数据。Google Fonts不可用时回退serif。后端API以专属字段对象收发，页面通过业务输入控件编辑，不要求用户写JSON。新增来源期间自动可选；专属字段和算法严格校验。JWT演示有效期2小时。

已知边界补充：连续对照的停试检验为单侧（只判定试验线更优），试验线更差时证据强度保持 0、不自动停试，由执行者判断是否提前停试。mSPRT 的先验尺度 τ 为全局预登记常数，不随试验调整；若工艺改善量级显著不同，应另立工艺额度而不是修改既有登记。工艺额度上限登记后不可改写，重开试验不改变已占用额度。

MIT License。

## 实际实体映射
来源记录（Source，专属业务字段校验）、口径版本（Policy）、核算报告（Run）、交付计划（Schedule）、交付（Delivery）均经数据库→模型→请求schema→service→route/controller→frontend API→store→page。Period为已有来源期间字典，在任务期间选择器使用；不单独作为复杂度计数。底稿JSON为小型多字段单记录存储，不虚构未落库的子实体。

实际表：期间字典 yield_periods；专属来源 yield_lots；冻结口径 denominator_policies；异步报告 yield_runs；工艺额度 trial_processes；试验登记 yield_trials；已纳入批次 trial_observations（`trial_id+batch_key` 唯一）；序贯查看历史 trial_looks（`trial_id+look_index` 唯一）。
