# V0.1 架构 Review

## 结论

设计资料中的核心边界没有静默偏移，V0.1 可以作为权限、候选任务和工单闭环的架构原型冻结。自动约束测试与空库验收已纳入每次质量门禁。

| 审查项 | 结论与证据 |
| --- | --- |
| 模块边界 | Router 无 SQL/Commit；Service 编排事务；Repository 封装查询。自动扫描全部 `*router.py`。 |
| IAM 关系模型 | User 不含组织、角色、岗位快捷外键；关系落在 UserOrganization 及关联表。 |
| 授权 | 稳定 Permission Code + 当前活动组织 + DataScope；修改后下一请求生效。 |
| 组织树 | `org_path` 支持子树范围与移动；循环、活动关系、业务引用有保护。 |
| 工单状态 | 唯一状态赋值入口为 WorkOrder 领域模型调用状态机。 |
| 流程边界 | Workflow 核心不导入 IAM；CandidateResolver 走端口，Factory 作为组合根注入 IAM 适配器。 |
| 任务访问 | 候选人、已分配人和任务状态共同约束 Claim/Handle/Review，不能仅依赖页面按钮。 |
| 数据范围 | WorkOrder 查看采用结构化 Scope Filter；任务动作按任务访问权约束，符合 ADR-005/I08 决策。 |
| 审计 | IAM 配置和工单动作均留痕；密码值、会话 Token 不写入审计。 |
| 迁移与初始化 | Alembic 从空库到 Head，IAM/Workflow Seed 幂等，Release Smoke 可配置 IAM 并闭环 DMA。 |

## 已接受的 Demo 限制

- SQLite 只验证模型和流程，不代表生产并发结论。
- Workflow 定义由 Seed 提供，尚无可视化设计、发布版本和回滚。
- 页面为服务端模板原型，未建设独立前端组件库与无障碍规范。
- 会话认证适合本地演示，生产安全前置条件见 ADR-006。

## 自动证据

运行 `.\.venv\Scripts\python.exe scripts\quality_gate.py` 可重复生成静态检查、敏感信息、全量回归、覆盖率和迁移一致性结果；运行 `.\.venv\Scripts\python.exe -m app.demo.release_smoke` 验证空库发布链路。
