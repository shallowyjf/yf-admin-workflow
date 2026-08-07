# 统一权限与流程工单平台 Python Demo

这是正式系统前的可运行架构原型，用于逐轮验证 IAM、功能权限、数据范围、CandidateResolver、WorkflowTask 与 WorkOrder 的领域边界。当前代码完成 **I06：WorkOrder 领域**，尚未实现流程实例或任务。

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

I06 已实现工单主表、动作时间线、业务编号、创建/提交、列表/详情/时间线 API，以及落到 SQLAlchemy 查询的真实 DataScope。工单只在领域实体内部执行 `DRAFT → PENDING_DISPATCH`，Router、Service 和 Repository 不直接赋值状态。

Demo 用户为 `admin`、`wangwu`、`zhangsan`、`lisi`、`zhaoliu`，初始密码统一为 `Demo@123456`，仅限本地演示。候选人解析演示可运行 `.\.venv\Scripts\python.exe -m app.demo.candidate_demo`。流程实例和任务将在后续迭代实现。设计约束见 `AI_CODING_RULES.md`，本轮验收见 `docs/iterations/I06.md`。
