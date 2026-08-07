# 统一权限与流程工单平台 Python Demo

这是正式系统前的可运行架构原型，用于逐轮验证 IAM、CandidateResolver、WorkflowTask 与 WorkOrder 的领域边界。当前代码完成 **I02：IAM 基础模型**，尚未实现 Permission、登录或流程工单。

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
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests migrations
```

## 当前边界

I02 已实现 User、Organization、Role、Position、UserOrganization，以及组织内角色和岗位关系。角色与岗位只能通过 UserOrganization 绑定，User 模型不存在 `org_id` 或 `role_id`。Permission、DataScope、登录、候选人、流程和工单将在后续迭代实现。

设计约束见 `AI_CODING_RULES.md`，本轮验收见 `docs/iterations/I02.md`。
