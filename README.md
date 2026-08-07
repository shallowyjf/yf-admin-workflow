# 统一权限与流程工单平台 Python Demo

这是正式系统前的可运行架构原型，用于逐轮验证 IAM、功能权限、数据范围、CandidateResolver、WorkflowTask 与 WorkOrder 的领域边界。当前代码完成 **I11：组织管理 CRUD 与 IAM 审计**。

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
- 演示登录页：<http://127.0.0.1:8000/login>
- 页面工作台：<http://127.0.0.1:8000/dashboard>
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

## 页面演示

访问登录页后，可使用以下统一初始密码 `Demo@123456`：

- `admin`：查看组织、用户、角色、岗位、权限等系统视图；
- `wangwu`：创建、提交、派单、复核和关闭工单；
- `lisi`：查看候选任务、认领工单并提交处理结果。

页面提供登录、工作台、五个 IAM 管理视图、工单列表、工单详情和我的任务共 10 个核心视图。组织管理已经支持新增、编辑、调整父级与排序、启停和安全删除；导航和动作按钮由服务层按有效权限计算，隐藏按钮不替代接口二次鉴权。

## 当前边界

I11 在 I10 页面基础上增加组织管理闭环和 IAM 审计日志。组织编码创建后不可修改；删除前检查子组织、成员关系和数据库业务引用。用户、角色、岗位和权限字典的写操作按 `docs/iterations/ROADMAP_I11_I15.md` 在后续迭代完成。

Demo 用户为 `admin`、`wangwu`、`zhangsan`、`lisi`、`zhaoliu`，初始密码统一为 `Demo@123456`，仅限本地演示。候选人解析演示可运行 `.\.venv\Scripts\python.exe -m app.demo.candidate_demo`。设计约束见 `AI_CODING_RULES.md`，本轮验收见 `docs/iterations/I11.md`。
