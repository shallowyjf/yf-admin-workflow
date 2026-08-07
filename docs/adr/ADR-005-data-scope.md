# ADR-005：功能权限与数据范围分离

- 状态：Accepted
- 适用迭代：I03 及以后

## 决策

功能权限、数据范围、对象策略和流程任务处理权必须分别判定：

1. `PermissionService.has_permission()` 使用稳定的 `permission_code` 判断用户在当前活动组织内能否执行某类动作。
2. `PermissionService.work_order_scope()` 返回 `WorkOrderScopeFilter`，只描述可见数据范围，不直接拼接 SQL。
3. 工单 Repository 在后续迭代中把结构化过滤器转换为 SQLAlchemy 条件。
4. 涉及流程任务的动作还必须独立通过 TaskAccess；功能权限或数据可见性不能替代任务处理权。

## 数据范围语义

| 类型 | 语义 |
| --- | --- |
| `ALL` | 不限制组织和本人条件 |
| `ORG` | 当前活动组织 |
| `ORG_AND_CHILD` | 当前活动组织及所有有效下级组织 |
| `SELF` | 当前用户创建或负责的数据 |
| `CUSTOM` | `scope_config.org_ids` 配置的组织集合 |

同一用户在当前组织可能拥有多个角色，范围按“或”合并，`ALL` 优先。没有功能权限、没有范围配置或活动组织关系无效时，结果为无数据。

## 约束

- 授权判断不使用角色名称、组织名称等展示字段。
- DataScope 按 `role_id + permission_code` 配置，使同一角色对不同功能可拥有不同范围。
- I03 不实现登录态、CandidateResolver、流程任务或工单表。
