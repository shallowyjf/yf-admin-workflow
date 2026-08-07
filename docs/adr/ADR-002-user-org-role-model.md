# ADR-002：用户、组织、角色与岗位关系

## 状态

Accepted for Demo V0.1

## 决策

用户与组织多对多；Role 和 Position 均通过 UserOrganization 绑定，不使用 `user.org_id` 或 `user.role_id`。

## 影响

- 同一用户可加入多个组织。
- 用户在不同组织中的角色与岗位互相独立。
- 组织成员关系具有启停状态，为后续候选人过滤提供稳定数据基础。
- 后续实现若改变本决策，必须新增或替代 ADR，并说明迁移影响。
