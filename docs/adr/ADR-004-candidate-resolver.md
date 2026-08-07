# ADR-004：统一候选人解析器

- 状态：Accepted for Demo V0.1

## 决策

流程模块只传递 `CandidateRule`，具体用户集合由 Resolver Registry 和 IAM `IdentityQueryService` 解析。

Registry 支持五种规则：

- `USER`：指定启用用户。
- `ROLE`：所有有效组织中拥有指定有效角色的启用用户；Demo 中应谨慎使用。
- `ORG`：指定有效组织内的所有启用成员。
- `ORG_ROLE`：指定组织有效成员与指定有效角色的交集。
- `ORG_POSITION`：指定组织有效成员与指定有效岗位的交集。

## 边界

- CandidateResolver 只返回去重后的用户 ID 集合，不更新任务、工单或 IAM 数据。
- workflow 候选模块依赖公开查询端口，不直接 import IAM Model 或 Repository。
- 停用用户、停用组织关系、停用组织、停用角色或停用岗位均不能成为候选人。
- 新规则通过新增 Resolver 注册，不扩展巨大 `if/elif`。
