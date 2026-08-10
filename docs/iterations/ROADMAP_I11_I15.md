# I11–I15：IAM 配置闭环与 V0.1 冻结路线图

## 规划决策

设计任务书原定 I11 为测试与质量门禁、I12 为架构 Review 与冻结。I10 验收后新增了“权限中心需要可配置”的明确需求，因此增加四轮 IAM 管理能力，并将原质量门禁与架构冻结合并到 I15。该调整不改变 User–Organization–Role–Position 关系模型、Permission + DataScope 授权模型或 WorkOrder/Workflow 边界。

## I11：IAM 管理基础与组织 CRUD

状态：已完成。

交付范围：

- 组织查询、新增、编辑、父级调整、排序、启停和安全删除。
- `system:org:create/update/status/delete` 稳定权限编码。
- 组织移动时原子更新整棵子树的 `org_path`。
- 子组织、成员、活动父子关系和业务外键引用保护。
- 通用 IAM 管理审计表，为后续用户、角色、岗位变更复用。
- REST API、Jinja 页面动作、权限按钮和友好错误提示。

验收重点：管理员完成组织全生命周期；非管理员 API 与页面写操作均为 403；每次成功变更产生审计记录。

## I12：用户生命周期与多组织关系

状态：已完成。

交付范围：

- 用户新增、基础资料编辑、启停和管理员重置密码。
- 维护 UserOrganization，多组织成员关系只能有一个主组织。
- 在具体 UserOrganization 下绑定/解绑 Role 与 Position，不在 User 上新增快捷外键。
- 停用用户或成员关系后，登录、有效权限和 CandidateResolver 立即失效。
- 用户管理 REST API、页面表单和审计记录。

验收重点：一个用户在两个组织拥有不同角色/岗位；切换 active_org 后权限随组织变化；停用用户不能登录或成为新候选人。

## I13：角色授权与 DataScope 闭环

状态：已完成。

交付范围：

- 角色新增、编辑和启停。
- 批量授予/撤销 Permission。
- 为每个已授权 Permission 配置 ALL、ORG、ORG_AND_CHILD、SELF 或 CUSTOM。
- CUSTOM 只接受存在且有效的组织，撤销权限时同步清理对应 DataScope。
- 角色授权 REST API、页面矩阵和审计记录。

验收重点：授权修改后无需重新登录即可在下次请求生效；权限与 DataScope 缺一不可；CUSTOM 数据范围精确过滤。

## I14：岗位与权限字典维护、IAM 联调

交付范围：

- 岗位新增、编辑、启停和安全删除。
- Permission 字典查询、初始化、新增和描述编辑；已被角色引用的稳定编码不可删除或改码。
- 组织、用户、角色、岗位、权限五个页面统一交互和友好错误模型。
- IAM 审计查询视图，按实体、动作和操作人过滤。
- 完整 IAM 权限矩阵、越权和关系约束回归。

验收重点：系统管理员能从页面完成完整 IAM 配置；业务角色只能访问被授权能力；所有关键变更可审计。

## I15：质量门禁、架构 Review 与 V0.1 冻结

交付范围：

- 补齐 Unit、Service Integration、API/UI E2E 边界用例。
- 固化 pytest、Ruff、Alembic、依赖方向和敏感信息检查脚本。
- 对照设计资料审查命名、状态机、数据模型、权限与候选人边界。
- 执行 IAM 配置 + 标准 DMA 全量人工回归。
- 更新 README、ADR、API 清单、初始化与 Release 文档，形成 V0.1 Demo Release。

验收重点：全量门禁一键执行；架构约束无静默偏差；空库可迁移、可 Seed、可完成 IAM 配置与 DMA 闭环。
