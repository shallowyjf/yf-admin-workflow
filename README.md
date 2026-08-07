# 统一权限与流程工单平台 Python Demo

这是正式系统前的可运行架构原型，用于逐轮验证 IAM、功能权限、数据范围、CandidateResolver、WorkflowTask 与 WorkOrder 的领域边界。当前代码完成 **I04：登录与 RequestContext**，尚未实现候选人解析或流程工单。

## 环境

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- SQLite
- pytest

## 初始化

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.iam.seed
```

## 运行

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

访问：

- 健康检查：<http://127.0.0.1:8000/health>
- OpenAPI：<http://127.0.0.1:8000/docs>

## 回归测试与质量检查

```powershell
.\.venv\Scripts\python.exe -m pytest -W error
.\.venv\Scripts\python.exe -m ruff check app tests migrations
.\.venv\Scripts\python.exe -m alembic check
```

## 当前边界

I04 已实现安全密码哈希、数据库端 Session、HttpOnly Cookie、`RequestContext`、当前用户查询与活动组织切换。角色仍只通过 UserOrganization 绑定；切换组织后角色与权限会从数据库重新计算，不写入 Cookie。

Demo 用户为 `admin`、`wangwu`、`zhangsan`、`lisi`、`zhaoliu`，初始密码统一为 `Demo@123456`，仅限本地演示。CandidateResolver、流程任务和工单将在后续迭代实现。设计约束见 `AI_CODING_RULES.md`，本轮验收见 `docs/iterations/I04.md`。
