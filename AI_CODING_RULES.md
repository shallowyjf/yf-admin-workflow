# AI_CODING_RULES

以下规则对所有 AI Coding 迭代有效。

## 强制

- Router -> Service -> Repository。
- 禁止 Router 直接 ORM Query/commit。
- 禁止 `user.role_id`、`user.org_id`。
- 禁止通过角色显示名/组织名判断授权。
- WorkOrder.status 只能经 StateMachine + WorkOrderService 改变。
- Workflow 不得直接查询 IAM 数据表；使用 IdentityQueryService/Port。
- WorkOrder / WorkflowInstance / WorkflowTask 必须分离。
- 新增权限、状态、候选人规则必须新增 pytest。
- 发生设计冲突时输出 `Decision Needed`，不要静默改模型。

## V0.1 禁止提前引入

Redis、Celery、Kafka/RabbitMQ、微服务、BPMN 引擎、Keycloak、Vue 前后端分离、多租户。
