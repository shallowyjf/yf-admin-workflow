# 统一权限与流程工单平台 Python Demo

这是正式系统前的可运行架构原型，用于逐轮验证 IAM、功能权限、数据范围、CandidateResolver、WorkflowTask 与 WorkOrder 的领域边界。当前代码完成 **I05：CandidateResolver**，尚未实现工单或流程任务。

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

I05 已实现 USER、ROLE、ORG、ORG_ROLE、ORG_POSITION 五类候选人解析器、Resolver Registry 和 IAM `IdentityQueryService`。解析结果只包含有效用户及有效组织关系，并统一去重；workflow 候选模块不直接查询 IAM 表。

Demo 用户为 `admin`、`wangwu`、`zhangsan`、`lisi`、`zhaoliu`，初始密码统一为 `Demo@123456`，仅限本地演示。候选人解析演示可运行 `.\.venv\Scripts\python.exe -m app.demo.candidate_demo`。流程任务和工单将在后续迭代实现。设计约束见 `AI_CODING_RULES.md`，本轮验收见 `docs/iterations/I05.md`。
