# ADR-006：V0.1 安全与事务边界

状态：Accepted with production prerequisites

## 背景

V0.1 需要冻结可演示的权限与工单闭环，同时避免把 Demo 的安全条件误认为生产条件。

## 决策

- Router 只负责协议转换、认证上下文和错误映射；业务写入由 Service 控制事务，Repository 封装持久化。
- 用户不保存 `org_id`、`role_id`、`position_id` 快捷字段，授权以当前有效 `UserOrganization` 下的角色和数据范围实时计算。
- WorkOrder 状态只能通过领域状态机变更；Workflow 核心只依赖候选人/身份端口，`workflow.factory` 是允许连接 IAM 的组合根。
- 会话只存 Token 哈希，密码使用带随机盐的密码哈希；权限编码稳定，关键 IAM 写操作记录操作者和前后值。
- 质量门禁固定检查静态规范、敏感信息、90% 覆盖率、告警、迁移漂移和空库发布路径。

## 生产前置条件

本决策不宣称 Demo 已达到互联网生产安全标准。真实部署前必须补齐 HTTPS/Secure Cookie、CSRF、登录限速与锁定、企业身份源/MFA、密钥托管、授权审批与职责分离、不可篡改审计、PostgreSQL 并发验证、备份恢复和可观测性。多租户仍不在 V0.1 范围内。
