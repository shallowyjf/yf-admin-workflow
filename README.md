# 统一权限与流程工单平台 Python Demo

这是正式系统前的可运行架构原型，用于逐轮验证 SaaS 租户、城市生命线多系统、工程项目数据权限、IAM、CandidateResolver、WorkflowTask 与 WorkOrder 的领域边界。当前代码已完成 **I25：GIS 空间、字段与导出权限**。

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
.\.venv\Scripts\python.exe -m app.project.seed
.\.venv\Scripts\python.exe -m app.data_permission.seed
.\.venv\Scripts\python.exe -m app.gis_permission.seed
.\.venv\Scripts\python.exe -m app.auth.platform_seed
.\.venv\Scripts\python.exe -m app.workflow.seed
.\.venv\Scripts\python.exe -m app.workorder.seed
```

## 运行

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

访问：

- 健康检查：<http://127.0.0.1:8000/health>
- 统一登录中心：<http://127.0.0.1:8000/login>
- 租户应用导航：<http://127.0.0.1:8000/portal>
- 页面工作台：<http://127.0.0.1:8000/dashboard>
- 组织权限树：<http://127.0.0.1:8000/iam/organizations>
- 项目进度驾驶舱：<http://127.0.0.1:8000/project-progress>
- 数据资源权限：<http://127.0.0.1:8000/data-resources>
- GIS 权限预览：从数据资源页点击 GIS 图层的“空间预览”
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

完整入口流程：所有身份统一从 `/login` 输入用户名和密码，不再输入租户编码。平台 Root 使用 `root / Root@123456` 登录后选择城市；租户用户由全局唯一登录名自动定位所属城市，管理员进入应用导航，工程人员默认进入工单中心。

多城市同名业务账号使用不同的全局登录名：江城市保留 `admin`、`lisi`；海州市使用 `haizhou.admin`、`haizhou.lisi`；云州市使用 `yunzhou.admin`、`yunzhou.lisi`。组织与业务页面仍显示租户内账号 `admin`、`lisi`。

访问登录页后，可使用以下统一初始密码 `Demo@123456`：

- `admin`：查看组织、用户、角色、岗位、权限等系统视图；
- `owner_leader`：查看当前城市获授权的全部业务系统与项目；
- `water_drainage_leader`：查看供水 DMA、供水水力模型和排水三个系统及项目；
- `water_manager`：供水 GIS 系统管理员，登录后直达供水驾驶舱；
- `drainage_manager`：排水 GIS 系统管理员，登录后直达排水驾驶舱；
- `gas_manager`：燃气 GIS 系统管理员，登录后直达燃气驾驶舱；
- `heating_manager`：供热 GIS 系统管理员，登录后直达供热驾驶舱；
- `road_manager`：道路 GIS 系统管理员，登录后直达道路驾驶舱；
- `dma_specialist`：只查看供水 DMA 系统及对应项目；
- `hydraulic_specialist`：只查看供水水力模型系统及对应项目；
- `owner_pm`：供水甲方项目经理；
- `supervisor_engineer`：供水监理工程师；
- `software_delivery`：软件供应商交付工程师；
- `wangwu`：创建、提交、派单、复核和关闭工单；
- `regulator`：查看监管项目并执行复核；
- `lisi`：查看本人参加的供水、排水、供热项目，认领工单并提交处理结果；
- `platform_ops`：查看平台运维范围内的项目与审计信息。

页面提供平台城市选择、租户应用导航、燃气/供水/排水/供热/道路 GIS 静态驾驶舱、组织权限树、用户/角色/岗位列表及详情、IAM 管理与审计视图、项目进度、工单列表、工单详情和我的任务。专属业务管理员登录后直达本业务驾驶舱且不能访问其他业务驾驶舱；组织树由服务端按当前角色数据范围裁剪；系统入口、项目成员和组织角色共同形成“城市租户—业务系统—工程项目—实体组织”的授权闭环。导航和动作按钮由服务层按有效权限计算，隐藏按钮不替代接口二次鉴权。

## V0.1 文档

- [Release 与人工验收](docs/RELEASE_V0.1.md)
- [API 清单](docs/API_V0.1.md)
- [架构 Review](docs/ARCHITECTURE_REVIEW_V0.1.md)
- [权限系统与工单中心差距评估](docs/PRODUCT_GAP_ASSESSMENT.md)
- [系统数据权限详细设计](docs/SYSTEM_DATA_PERMISSION_DESIGN.md)
- [I24–I28 系统数据权限迭代路线](docs/iterations/ROADMAP_I24_I28_DATA_PERMISSION.md)

## 当前边界

V0.1 已形成组织、用户、角色、岗位、权限、数据范围和 IAM 审计配置闭环，并可执行标准 DMA 工单闭环。城市按租户隔离，业务方向由系统 `domain_type` 分类，系统入口逐用户授权，项目再叠加参与组织和项目成员角色；同一供水业务下的 DMA 与水力模型可独立授权。它仍是本地 Demo：实时数据汇聚、空间资源权限、认证安全加固、授权治理、对象存储/外部通知、不可篡改审计和生产运维属于真实上线前置范围。

Demo 城市租户编码为 `DEMO`（江城市）、`CITY_HAIZHOU`（海州市）、`CITY_YUNZHOU`（云州市），初始密码统一为 `Demo@123456`，仅限本地演示。完整账号与授权矩阵见 `docs/PERMISSION_WORKORDER_REQUIREMENTS.md`。
