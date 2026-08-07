# 统一权限与流程工单平台 Python Demo

这是正式系统前的可运行架构原型，用于逐轮验证 IAM、CandidateResolver、WorkflowTask 与 WorkOrder 的领域边界。当前代码完成 **I01：项目骨架与数据库基础**，尚未实现业务页面或权限流程。

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

I01 只建立应用工厂、配置、数据库会话、Alembic 迁移、健康检查和测试基础设施。用户、组织、角色、权限、流程和工单将在后续迭代按设计任务书逐轮实现。

设计约束见 `AI_CODING_RULES.md`，本轮验收见 `docs/iterations/I01.md`。
