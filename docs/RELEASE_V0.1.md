# V0.1 Demo Release 与人工验收

## 发布基线

- Python 3.12、FastAPI、SQLAlchemy 2、Alembic、SQLite。
- 版本 `0.1.0`，当前增量迭代 `I17`。
- 本地演示账号初始密码均为 `Demo@123456`，禁止复用于任何真实环境。

## 从空目录数据库启动

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.iam.seed
.\.venv\Scripts\python.exe -m app.workflow.seed
.\.venv\Scripts\python.exe -m app.workorder.seed
.\.venv\Scripts\python.exe scripts\quality_gate.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

若只验收发布链路，运行 `.\.venv\Scripts\python.exe -m app.demo.release_smoke`；它使用临时空库，不污染 `var/demo.db`。

## 人工验收清单

1. 打开 `/health`，确认 `status=ok`、`database=ok`、`iteration=I17`。
2. 用 `admin` 登录，创建临时岗位和自定义 Permission；创建角色并配置 Permission + ORG DataScope；创建用户并绑定 PIPE_OPERATION、角色和岗位。
3. 切换到新用户，确认只显示被授权导航，直接调用未授权 API 返回 403；停用成员/角色/用户后权限立即失效。
4. 用 `wangwu` 创建并提交 DMA 工单，派给 PIPE_OPERATION；用 `lisi` 认领并提交结果；再用 `wangwu` 复核通过并关闭。
5. 用 `zhaoliu` 竞争认领同一任务，确认被拒绝；检查工单时间线包含七个标准动作。
6. 回到 `/iam/audit`，按实体、动作和 `admin` 过滤，确认 IAM 写操作可追踪。
7. 打开 `/docs`，抽查 42 个业务路径，并验证 SLA、附件和通知接口。

## 发布判定

代码门禁、空库验收与上述人工主路径均通过，才可标记为 V0.1 Demo Release。生产化前置项与后续五轮建议见 `PRODUCT_GAP_ASSESSMENT.md`。
