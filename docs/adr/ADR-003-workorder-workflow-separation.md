# ADR-003：工单与流程任务分离

- 状态：Accepted for Demo V0.1

## 决策

- `WorkOrder` 表达业务事情本身，包括编号、标题、责任组织、当前办理人和业务状态。
- `WorkflowInstance` 表达一次流转实例。
- `WorkflowTask` 表达当前由谁办理什么任务。

三类对象独立持久化、独立维护状态，不把候选人或任务状态塞进工单操作日志，也不在 I06 提前创建流程表。

## I06 影响

- I06 只实现 WorkOrder 与 WorkOrderAction。
- `submit` 将工单从 `DRAFT` 推进到 `PENDING_DISPATCH`，但不创建 WorkflowInstance；该联动从 I07 开始，并要求处于同一事务边界。
- 后续若改变此分离决策，必须新增替代 ADR 并说明数据迁移影响。
