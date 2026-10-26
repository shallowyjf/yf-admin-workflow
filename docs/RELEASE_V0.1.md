# V0.1 Demo Release 与人工验收

## 发布基线

- Python 3.12、FastAPI、SQLAlchemy 2、Alembic、SQLite。
- 版本 `0.1.0`，当前增量迭代 `I26`。
- 本地演示账号初始密码均为 `Demo@123456`，禁止复用于任何真实环境。

## 从空目录数据库启动

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.iam.seed
.\.venv\Scripts\python.exe -m app.project.seed
.\.venv\Scripts\python.exe -m app.data_permission.seed
.\.venv\Scripts\python.exe -m app.gis_permission.seed
.\.venv\Scripts\python.exe -m app.workflow.seed
.\.venv\Scripts\python.exe -m app.workorder.seed
.\.venv\Scripts\python.exe scripts\quality_gate.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

若只验收发布链路，运行 `.\.venv\Scripts\python.exe -m app.demo.release_smoke`；它使用临时空库，不污染 `var/demo.db`。

## 人工验收清单

1. 打开 `/health`，确认 `status=ok`、`database=ok`、`iteration=I26`。
2. 在统一登录中心使用 `admin` 和初始密码登录，确认 `/auth/me` 返回江城市租户，且 IAM 页面只展示当前租户数据。
3. 打开 `/portal`，确认五类业务方向、六个业务系统、六个工程项目和对应驾驶舱入口完整显示。
4. 切换活动生命线系统和工程项目，确认只能选择账号已授权入口和已参加项目；使用管理员完成项目新增、编辑、参与组织和成员角色配置。
3. 用 `admin` 创建自定义 Permission；创建角色并配置 Permission + ORG DataScope；创建用户并绑定 PIPE_OPERATION 和组织内角色。
4. 切换到新用户，确认只显示被授权导航，直接调用未授权 API 返回 403；停用成员/角色/用户后权限立即失效。
5. 用 `wangwu` 创建并提交 DMA 工单，派给 PIPE_OPERATION；用 `lisi` 认领并提交结果；再用 `wangwu` 复核通过并关闭。
6. 用 `zhaoliu` 竞争认领同一任务，确认被拒绝；检查工单时间线包含七个标准动作。
7. 回到 `/iam/audit`，按实体、动作和 `admin` 过滤，确认 IAM 写操作可追踪。
8. 打开 `/docs`，抽查 50 个业务路径，并验证分页、保存视图、批量工单和 IAM 导入导出接口。
9. 用 `dma_specialist` 打开 `/data-resources`，确认可见采集/处理数据但不可见模型结果；用 `hydraulic_specialist` 确认只看到水力模型资源与计算结果。
10. 用 `dma_specialist` 打开供水管网图层空间预览，确认只返回 DMA_07/DMA_12、坐标按 1km 泛化且敏感字段不出现；用 `water_manager` 确认全范围精确坐标，并验证普通导出允许、敏感字段导出拒绝。

## 发布判定

代码门禁、空库验收与上述人工主路径均通过，才可标记为 V0.1 Demo Release。生产化前置项与后续五轮建议见 `PRODUCT_GAP_ASSESSMENT.md`。
