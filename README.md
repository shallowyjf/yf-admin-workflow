# 统一权限与流程工单平台 Python Demo

这是正式系统前的可运行架构原型，用于逐轮验证 IAM、功能权限、数据范围、CandidateResolver、WorkflowTask 与 WorkOrder 的领域边界。当前代码已完成 **I17：SLA、附件与站内通知**，正在按 P1 可用业务产品路线推进。

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
.\.venv\Scripts\python.exe -m app.workorder.seed
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
.\.venv\Scripts\python.exe scripts\quality_gate.py
```

门禁统一执行 Ruff、敏感信息检查、`pytest -W error`、90% 覆盖率阈值和 Alembic 漂移检查。GitHub Actions 对每次 Push 和 Pull Request 执行同一命令。

空库发布验收（迁移、Seed、IAM 配置生效及 DMA 闭环）：

```powershell
.\.venv\Scripts\python.exe -m app.demo.release_smoke
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

页面提供登录、工作台、六个 IAM 管理与审计视图、工单列表、工单详情和我的任务共 11 个核心视图。组织、用户、角色、岗位和权限均已形成配置闭环；IAM 审计支持按实体、动作和操作人过滤。导航和动作按钮由服务层按有效权限计算，隐藏按钮不替代接口二次鉴权。

## V0.1 文档

- [Release 与人工验收](docs/RELEASE_V0.1.md)
- [API 清单](docs/API_V0.1.md)
- [架构 Review](docs/ARCHITECTURE_REVIEW_V0.1.md)
- [权限系统与工单中心差距评估](docs/PRODUCT_GAP_ASSESSMENT.md)

## 当前边界

V0.1 已形成组织、用户、角色、岗位、权限、数据范围和 IAM 审计配置闭环，并可执行标准 DMA 工单闭环。I16–I17 已补齐转派、评论、催办、SLA 时限与升级、附件安全约束和个人通知。它仍是本地 Demo：认证安全加固、授权变更治理、对象存储/外部通知、并发幂等、不可篡改审计和生产运维属于真实上线前置范围。

Demo 用户为 `admin`、`wangwu`、`zhangsan`、`lisi`、`zhaoliu`，初始密码统一为 `Demo@123456`，仅限本地演示。候选人解析演示可运行 `.\.venv\Scripts\python.exe -m app.demo.candidate_demo`。设计约束见 `AI_CODING_RULES.md`，本轮验收见 `docs/iterations/I17.md`。
