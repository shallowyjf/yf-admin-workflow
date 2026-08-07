# 统一权限与流程工单平台 Python Demo

这是正式系统前的可运行架构原型，用于逐轮验证 IAM、功能权限、数据范围、CandidateResolver、WorkflowTask 与 WorkOrder 的领域边界。当前代码完成 **I09：DMA 完整业务闭环**。

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
.\.venv\Scripts\python.exe -m app.workflow.seed
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

## 标准 DMA 演示

以下命令会使用 Seed 用户在当前数据库新建一张 `DMA07 压力异常` 工单，依次执行提交、派单、李四认领、赵六竞争认领、处理、复核和关闭，并输出状态路径、候选人及完整时间线：

```powershell
.\.venv\Scripts\python.exe -m app.demo.dma_workflow_demo
```

## 当前边界

I09 已把 IAM、CandidateResolver、WorkflowTask、WorkOrder 和时间线串联为可重复运行的标准 DMA 演示。派单后的工单同时对当前责任组织和原所属组织可见，保证调度中心能够复核、关闭并读取完整时间线。

Demo 用户为 `admin`、`wangwu`、`zhangsan`、`lisi`、`zhaoliu`，初始密码统一为 `Demo@123456`，仅限本地演示。候选人解析演示可运行 `.\.venv\Scripts\python.exe -m app.demo.candidate_demo`。I10 将新增 Jinja2 + HTMX 演示页面和 Dashboard。设计约束见 `AI_CODING_RULES.md`，本轮验收见 `docs/iterations/I09.md`。
