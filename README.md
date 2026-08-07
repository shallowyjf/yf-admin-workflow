# 统一权限与流程工单平台 Python Demo

这是正式系统前的可运行架构原型，用于逐轮验证 IAM、功能权限、数据范围、CandidateResolver、WorkflowTask 与 WorkOrder 的领域边界。当前代码完成 **I03：功能权限与数据范围**，尚未实现登录、候选人解析或流程工单。

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

I03 已实现 Permission、RolePermission、RoleDataScope 与 `PermissionService`。角色仍只通过 UserOrganization 绑定；功能权限、数据范围和未来的流程任务处理权是三套独立判定。DataScope 返回结构化 `WorkOrderScopeFilter`，不在 Service 内拼 SQL。

登录、活动组织令牌上下文、CandidateResolver、流程任务和工单将在后续迭代实现。设计约束见 `AI_CODING_RULES.md`，本轮验收见 `docs/iterations/I03.md`。
