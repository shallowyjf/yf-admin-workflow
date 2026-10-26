# 城市生命线系统数据权限详细设计

版本：V0.1

适用范围：权限中心、工单中心、GIS 平台、水力模型平台与后续数据中心

状态：I24–I25 已实现应用级角色、数据空间、统一资源目录、资源 ALLOW/DENY、GIS 字段策略、空间范围、坐标泛化、模拟查询与导出审计；I26 已取消重复岗位维度，系统入口、项目组织、项目成员和派单候选的页面闭环顺延为下一轮 P1

## 1. 设计目标

系统数据权限解决的不是“用户能否看到一个菜单”，而是以下问题：

- 用户能否进入某个业务系统；
- 用户在该系统中具有什么角色和功能动作；
- 用户能访问哪些项目、组织、数据空间和具体资源；
- 用户对资源能查看、编辑、计算、发布、下载还是共享；
- 返回结果需要执行哪些行级过滤、字段隐藏、脱敏、聚合或空间裁剪；
- 跨系统、服务账号和外部接口如何获得受控、可到期、可审计的数据访问；
- 授权如何申请、审批、生效、复核、撤销并在所有数据出口即时执行。

本设计遵循以下原则：

1. **系统入口不等于数据权限**：`sys_user_application` 只控制能否进入系统，不自动授予系统内数据。
2. **角色与作用域分离**：角色表达能力模板，角色授予必须带租户、系统、项目或组织作用域。
3. **项目不是所有数据的唯一容器**：项目数据绑定项目；城市主数据、业务共享数据和系统私有数据进入独立数据空间。
4. **功能权限与资源策略分离**：稳定动作使用 RBAC；具体资源、字段、空间和上下文使用资源策略。
5. **默认拒绝、显式共享**：跨租户绝对禁止；跨系统、跨项目和敏感资源必须显式授权。
6. **汇总权限不下钻**：城市领导可查看授权汇总，不自动获得原始明细、精确坐标或附件下载权限。
7. **服务端和数据出口强制执行**：前端隐藏仅改善体验，API、数据库、对象存储、GIS 服务和导出任务必须重复鉴权。
8. **授权全生命周期可审计**：申请、审批、授予、使用、变更、到期和撤销均可追溯。

## 2. 与现有模型的关系

### 2.1 可直接复用

| 现有概念 | 继续承担的职责 |
| --- | --- |
| Tenant | 城市/客户最高隔离边界 |
| Application / TenantApplication | 系统目录、租户订阅和系统入口边界 |
| UserApplicationAccess | 用户是否具备系统入口 |
| Organization / UserOrganization | 真实组织与用户组织身份 |
| Role / Permission | 功能能力模板与稳定动作编码 |
| Project / ProjectMember | 工程项目数据空间和项目角色 |
| WorkOrder / WorkflowTask | 业务处置对象和流程任务处理权 |
| RoleDataScope | 现有组织/本人范围；继续服务组织树和工单 |

### 2.2 必须新增

| 新概念 | 业务含义 |
| --- | --- |
| ApplicationRoleGrant | 同一组织成员在不同系统中具有不同角色 |
| DataSpace | 城市公共、业务共享、系统私有、项目协作、汇总和模型沙箱空间 |
| BusinessResource | 数据集、图层、设施、API、文件、指标、模型、结果等统一资源目录 |
| ResourcePolicy | 主体对资源执行动作的允许/拒绝策略 |
| FieldPolicy | 字段可见、隐藏、脱敏、坐标模糊和聚合策略 |
| DataAccessGrant | 经申请或管理操作形成的有效授权实例 |
| ServiceAccount | 系统间调用、数据同步和模型计算使用的非人身份 |
| DataAccessAudit | 查询、下载、导出、共享、发布和模型运行审计 |

现有 `RoleDataScope.scope_config` 只保存 `org_ids`。不得无限扩充该 JSON 来承担全部数据权限；复杂业务资源应进入独立资源策略模型。

## 3. 分层授权模型

### 3.1 授权判定公式

```text
允许操作 = 身份和会话有效
        ∩ 同一租户
        ∩ 租户已订阅系统
        ∩ 用户具备系统入口
        ∩ 应用级/项目级角色具备功能动作
        ∩ 项目或数据空间可访问
        ∩ 资源关系和资源策略允许
        ∩ 行级/空间范围匹配
        ∩ 字段与敏感等级策略允许
        ∩ 状态、用途、时间和环境条件允许
        ∩ 涉及流程时具备当前任务处理权
        ∩ 不存在优先级更高的 DENY
```

任何一项不满足均拒绝。资源不存在与资源不可见对外统一返回 404；已知资源但动作被拒绝的管理场景返回 403。

### 3.2 权限层次

| 层次 | 典型问题 | 主要模型 |
| --- | --- | --- |
| 身份层 | 是谁、账号是否有效 | User、Session、ServiceAccount |
| 租户层 | 属于哪个城市 | Tenant |
| 系统层 | 能否进入 GIS/水力模型 | TenantApplication、UserApplicationAccess |
| 功能层 | 能否查询、编辑、运行、发布 | Role、Permission、ApplicationRoleGrant |
| 数据空间层 | 能访问哪个共享域或项目域 | DataSpace、Project |
| 资源层 | 能访问哪个图层、数据集、模型 | BusinessResource、ResourcePolicy |
| 数据细节层 | 哪些行、字段、空间和时间 | scope_config、FieldPolicy |
| 流程层 | 当前是否轮到该用户办理 | WorkflowTask、TaskAccess |

## 4. 应用级角色授予

### 4.1 现有问题

当前角色绑定在 `UserOrganization`，项目角色绑定在 `ProjectMember`。当同一用户拥有多个系统入口时，无法稳定表达“供水 GIS 可编辑、水力模型只读、DMA 可导出”。

### 4.2 数据模型

建议新增 `iam_application_role_grant`：

```text
id
tenant_id
tenant_application_id
user_org_id
role_id
valid_from
valid_to
grant_source        # ADMIN / WORKFLOW / SYNC / EMERGENCY
workflow_instance_id
is_active
created_by
created_at / updated_at
```

约束：

- `tenant_application_id`、`user_org_id`、`role_id` 必须属于同一租户；
- 系统未订阅、入口未授权、组织成员失效或角色停用时授权不得生效；
- 唯一键建议为 `(tenant_application_id, user_org_id, role_id, valid_from)`；
- 同一用户可在不同系统中获得不同角色；
- 系统级角色不能替代项目成员资格；涉及项目资源时仍需项目授权；
- 授权到期、撤销或入口失效后，下一次请求立即失权并使策略缓存失效。

### 4.3 示例

| 用户 | 系统 | 系统角色 | 项目角色 |
| --- | --- | --- | --- |
| `water_manager` | 供水 GIS | GIS 业务管理员 | 供水项目负责人 |
| `water_manager` | 水力模型 | 模型成果查看人员 | 水力模型项目观察员 |
| `hydraulic_specialist` | 水力模型 | 模型编辑人员 | 模型建设成员 |
| `hydraulic_specialist` | 供水 GIS | 无入口；仅通过服务授权读取指定数据集 | 无 |

## 5. 数据空间设计

### 5.1 数据空间类型

| 类型 | 说明 | 示例 |
| --- | --- | --- |
| COMMON | 租户公共主数据 | 行政区划、组织、字典、统一编码 |
| DOMAIN_SHARED | 业务方向共享数据 | 供水基础管网、排水设施目录 |
| APPLICATION_PRIVATE | 系统私有数据 | DMA 监测明细、GIS 编辑库 |
| PROJECT | 项目协作数据 | 测绘成果、施工资料、项目工单 |
| AGGREGATE | 授权汇总读模型 | 城市领导指标、业务方向统计 |
| MODEL_SANDBOX | 模型试验空间 | 水力模型场景、参数和试算结果 |

### 5.2 数据模型

建议新增 `dc_data_space`：

```text
id
tenant_id
space_code
space_name
space_type
domain_type
application_id       # 可空
project_id           # 可空
owner_org_id
steward_user_id      # 数据责任人，可空
sensitivity_level
is_active
```

约束：

- COMMON 和 DOMAIN_SHARED 可以不绑定项目；
- APPLICATION_PRIVATE 必须绑定系统；
- PROJECT 必须绑定项目，并校验项目和系统归属；
- MODEL_SANDBOX 必须绑定模型系统，可选绑定项目；
- 数据空间不是实体组织，不出现在组织树中。

## 6. 统一业务资源目录

### 6.1 资源模型

建议新增 `dc_business_resource`：

```text
id
tenant_id
data_space_id
application_id
project_id             # 可空
owner_org_id
resource_type
resource_key
resource_name
parent_resource_id     # 可空
derivation_stage       # ACQUIRED / PROCESSED / MODEL_INPUT / MODEL_RESULT / PUBLISHED
sensitivity_level
resource_tags          # JSON，只保存可治理标签
resource_version
status
created_by
created_at / updated_at
```

资源类型至少包括：

- `DATA_SOURCE`、`DATABASE`、`SCHEMA`、`TABLE`、`FIELD`、`DATASET`；
- `FILE_DIRECTORY`、`FILE`、`API`、`MESSAGE_TOPIC`、`METRIC`、`REPORT`；
- `GIS_LAYER`、`GIS_FEATURE_SET`、`ASSET_GROUP`、`SPATIAL_REGION`；
- `HYDRAULIC_MODEL`、`MODEL_VERSION`、`MODEL_SCENARIO`、`MODEL_RUN`、`MODEL_RESULT`。

### 6.2 资源归属规则

- 所有资源必须保存 `tenant_id`，不得通过当前会话临时推断后写入；
- 系统私有资源必须保存 `application_id`；
- 项目资源必须保存 `project_id` 和 `owner_org_id`；
- 资源路径、缓存键、对象存储 Key、消息主题和搜索索引必须包含租户及必要的系统/项目维度；
- 资源父子关系不能跨租户；跨系统关系只能使用显式共享关系，不得直接修改资源归属；
- 采集数据、处理数据、模型输入快照、模型计算结果和发布成果必须注册为相互独立的资源；
- 数据血缘只描述“由什么产生”，不传播访问权限；拥有上游输入资源不自动获得下游派生结果，拥有结果也不自动获得原始输入；
- 删除目录前必须检查子资源、有效授权、工单、模型版本和审计引用；有引用时只允许停用或归档。

## 7. 资源策略与字段策略

### 7.1 资源策略

建议新增 `auth_resource_policy`：

```text
id
tenant_id
subject_type          # USER / ROLE / ORG / PROJECT / APPLICATION / SERVICE_ACCOUNT
subject_id
resource_id           # 可空，与 resource_selector 二选一
resource_selector     # 标签/类型/父资源条件
action_code
effect                # ALLOW / DENY
scope_config
field_policy_id       # 可空
purpose_code          # 可空
valid_from / valid_to
priority
grant_source
workflow_instance_id  # 可空
is_active
```

解析规则：

1. 先过滤同租户、有效期和有效状态；
2. 收集用户、组织成员角色、应用角色、项目角色和服务账号策略；
3. 精确资源策略优先于父资源/标签策略；
4. 显式 `DENY` 优先于同级 `ALLOW`；
5. 敏感等级越高，要求的显式授权越具体；
6. 返回结构化授权解释，不只返回布尔值。

### 7.2 数据范围

`scope_config` 采用受控 Schema，不允许任意 SQL。首期支持：

| 范围 | 配置示例 |
| --- | --- |
| 组织 | `org_ids` |
| 项目 | `project_ids` |
| 行政区域 | `region_ids` |
| DMA 分区 | `dma_ids` |
| GIS 图层 | `layer_ids` |
| 资产组 | `asset_group_ids` |
| 资源集合 | `resource_ids` |
| 时间范围 | `time_from/time_to` |
| 数据标签 | `required_tags` |
| 对象关系 | `owner_only/creator_only/assignee_only` |

空间范围应存行政区、项目红线、DMA 或资产组的稳定 ID。复杂几何由 GIS 服务解析，权限策略不直接保存未经治理的任意空间 SQL。

### 7.3 字段策略

建议新增 `auth_field_policy` 与 `auth_field_rule`：

| 处理方式 | 说明 |
| --- | --- |
| VISIBLE | 原值可见 |
| HIDDEN | 字段不返回 |
| MASKED | 按规则脱敏 |
| GENERALIZED | 坐标或精度泛化 |
| AGGREGATED | 仅返回聚合结果 |
| HASHED | 返回稳定哈希标识 |

字段策略示例：普通工程人员看设施名称和状态；项目经理可看管径、材质和埋深；安全授权人员才能看关键设施精确坐标和完整运行参数。

## 8. 权限编码设计

### 8.1 通用数据中心权限

```text
data:catalog:view
data:metadata:view
data:resource:register
data:resource:manage
data:classification:manage
data:ingest
data:process
data:quality:manage
data:preview
data:query
data:write
data:download
data:export
data:publish
data:share
data:api:consume
data:access:apply
data:access:approve
data:access:revoke
data:audit:view
data:lineage:view
```

### 8.2 GIS 权限

```text
gis:dashboard:view
gis:layer:view
gis:layer:manage
gis:feature:create
gis:feature:update
gis:feature:delete
gis:spatial:query
gis:dataset:export
gis:service:consume
gis:sensitive-location:view
```

### 8.3 水力模型权限

```text
hydraulic:model:view
hydraulic:model:edit
hydraulic:model:manage
hydraulic:version:create
hydraulic:scenario:create
hydraulic:scenario:update
hydraulic:run:view-status
hydraulic:run:execute
hydraulic:run:cancel
hydraulic:result:view
hydraulic:result:export
hydraulic:calibration:manage
hydraulic:version:publish
hydraulic:version:approve
```

权限编码只表达动作，不为每个数据集创建一条 Permission。具体资源由 `ResourcePolicy` 绑定，避免权限字典无限膨胀。

## 9. GIS 系统数据权限

### 9.1 权限层次

```text
供水 GIS 系统入口
  → 供水项目/数据空间
    → 图层/数据集
      → 行政区/DMA/项目红线
        → 设施或资产组
          → 字段与精确坐标
            → 查看/编辑/发布/导出/API
```

### 9.2 强制执行点

- 驾驶舱组件按系统和资源策略显示；
- 图层目录接口过滤不可发现资源；
- WMS/WFS/WMTS、矢量瓦片和空间查询服务验证短期令牌及资源范围；
- 编辑接口重新读取设施归属，不信任前端传入的图层、项目或组织 ID；
- 导出任务独立校验 `gis:dataset:export`，生成带审计和有效期的下载地址；
- 无精确坐标权限时返回泛化坐标或聚合网格，不在前端拿到原值后再隐藏。

## 10. 水力模型系统数据权限

### 10.1 资源层次

```text
水力模型
  → 模型版本
    → 计算场景
      → 输入数据快照
        → 模型运行任务
          → 计算结果
            → 成果报告/发布版本
```

### 10.2 职责分离

- 模型编辑人员可修改草稿模型，但不能审批或发布生产版本；
- 模型运行人员可执行和取消计算，但不能修改基础模型；
- 模型审核人员审批发布，不应同时拥有当前版本的最终编辑权；
- 业务查看人员只读取已批准的成果；
- 模型、输入快照、参数、执行人、运行日志和结果必须形成数据血缘；
- 授权撤销后不得下载新结果，已经运行的异步任务按提交时授权快照完成，但结果领取时再次实时鉴权。

### 10.3 采集/处理数据与模型结果隔离

数据人员可查看采集或处理后的监测数据，但不能因此查看模型计算结果。输入和输出必须使用独立资源、独立动作和独立策略：

```text
监测采集数据 ACQUIRED
  → 清洗/校核数据 PROCESSED
    → 模型输入快照 MODEL_INPUT
      → 模型运行 MODEL_RUN
        → 模型详细结果 MODEL_RESULT
          → 审批发布成果 PUBLISHED
```

权限不沿箭头自动传播。数据血缘允许授权用户知道“某结果由哪个输入版本产生”，但血缘元数据本身不能成为读取结果或反查原始数据的通道。

建议角色矩阵：

| 角色 | 采集数据 | 处理数据 | 模型输入快照 | 运行状态 | 模型详细结果 | 发布成果 |
| --- | --- | --- | --- | --- | --- | --- |
| 数据采集人员 | 写入/质量查看 | 无或只读 | 无 | 无 | 无 | 无 |
| 数据治理人员 | 查看 | 处理/校核 | 可生成快照 | 无 | **无** | 按需查看汇总 |
| 模型运行人员 | 仅授权输入 | 仅授权输入 | 查看 | 执行/查看状态 | 按角色决定 | 无 |
| 模型分析人员 | 仅授权输入 | 仅授权输入 | 查看 | 查看 | 查看/分析 | 提交发布 |
| 模型审核人员 | 必要摘要 | 必要摘要 | 查看版本 | 查看 | 查看 | 审批 |
| 业务领导 | 无原始明细 | 无原始明细 | 无 | 无 | 无详细结果 | 查看授权汇总 |

强制规则：

- `data:query` 只能用于获授权的采集/处理资源，不等价于 `hydraulic:result:view`；
- `hydraulic:run:view-status` 只返回任务状态、耗时和错误摘要，不返回结果载荷；
- `hydraulic:run:execute` 不自动授予 `hydraulic:result:view` 或 `hydraulic:result:export`；
- 模型服务账号可以对输入资源执行 `READ`、对结果空间执行受限 `CREATE/WRITE`，无需拥有结果的人类可读权限；
- 模型结果归属于水力模型系统或模型沙箱，不归属于监测数据中心；
- 模型详细结果可以比原始监测数据具有更高敏感等级，例如管网薄弱点、爆管风险和调度方案；
- 向数据人员开放结果时，应另行发布经过审批的汇总指标资源，而不是扩大详细结果策略；
- 结果详情、结果文件、报表、导出、搜索索引和缓存都必须检查结果资源策略，不能只检查输入数据权限。

## 11. 跨系统共享与服务账号

### 11.1 显式共享

跨系统共享不得通过相同 `domain_type`、相同组织或前端切换实现。以水力模型读取 GIS 管网为例：

```text
GIS 注册供水管网数据集
→ 数据责任人发布可共享版本
→ 水力模型服务账号申请指定字段/区域/项目
→ 审批生成 DataAccessGrant
→ API 网关签发短期作用域令牌
→ 水力模型读取不可变数据快照
→ 记录调用、版本、用途和结果血缘
→ 到期或撤销后停止新调用
```

### 11.2 服务账号

建议新增 `sys_service_account`：

- 服务账号必须绑定租户和所属系统；
- 不允许交互式登录，不复用个人管理员账号；
- 凭据使用密钥托管和定期轮换；
- 只获得调用所需最小资源与动作；
- 令牌携带租户、系统、授权 ID 和过期时间，资源服务仍要重新校验；
- 调用量、失败、导出和异常访问进入审计及告警。

## 12. 数据权限申请与工单流程

数据权限申请使用独立业务对象 `dc_access_request`，复用 WorkflowInstance/WorkflowTask，不直接把每个申请伪装成普通维修工单。

标准流程：

```text
DRAFT → SUBMITTED → OWNER_REVIEW → SECURITY_REVIEW
      → APPROVED → ACTIVE → EXPIRING → EXPIRED/REVOKED
```

申请内容至少包括：资源、动作、用途、主体、范围、字段、是否导出、有效期和预期调用量。

- 普通数据由数据责任人审批；
- 敏感数据增加安全审批；
- 高敏导出或跨系统共享要求双人审批；
- 审批通过生成不可手工篡改来源的 `DataAccessGrant`；
- 到期自动失效，并通知使用人和数据责任人；
- 使用中的长期授权进入定期复核；
- 紧急授权必须短时有效、说明原因并事后复核。

数据缺失、延迟、字段异常、坐标错误、模型输入异常和接口中断继续使用工单中心处理，并通过 `source_resource_id` 关联数据资源。

## 13. 驾驶舱与系统入口调整

当前按 `domain_type` 汇总业务驾驶舱的方式仅适合静态 Demo。真实数据接入后：

1. 业务方向总览只读取授权汇总读模型；
2. 具体系统驾驶舱按 `application_id` 独立鉴权；
3. 每个指标、图层、事件列表和下钻链接绑定 `resource_id`；
4. 用户只拥有供水水力模型入口时，不能因此获得供水 GIS 原始图层；
5. 同时拥有两个系统入口也不代表两个系统的数据自动互通；
6. 城市领导的汇总权限不自动提供原始工单、附件、精确坐标或模型薄弱点明细。

建议入口结构：

```text
供水业务方向总览（授权汇总）
├── 供水 GIS 系统驾驶舱
├── DMA 漏损系统驾驶舱
└── 水力模型系统驾驶舱
```

## 14. 数据出口强制执行

| 数据出口 | 必须执行的控制 |
| --- | --- |
| 业务 API | 服务端重算租户、系统、资源、动作和字段策略 |
| PostgreSQL | 应用过滤 + RLS 双层防护 |
| GIS 服务 | 图层、空间范围、字段和瓦片令牌校验 |
| 对象存储 | 租户/系统/资源前缀、私有桶、短期签名 URL |
| 查询引擎 | 行级过滤、列级隐藏/脱敏、结果行数限制 |
| 搜索索引 | 文档写入资源范围标签，查询时强制过滤 |
| 缓存 | Key 包含租户、系统、资源和策略版本 |
| 消息平台 | Topic/Consumer 按租户和系统隔离 |
| 导出服务 | 独立权限、审批、水印、有效期、下载审计 |

高敏租户或系统可以使用独立 Schema/数据库/KMS Key，但独立存储不能替代应用鉴权。

## 15. 授权解释与审计

### 15.1 授权解释

统一接口返回：

```json
{
  "allowed": false,
  "subject": {"type": "USER", "id": 1001},
  "context": {"tenant_id": 1, "application_id": 2, "project_id": 11},
  "action": "gis:dataset:export",
  "resource_id": 9001,
  "checks": [
    {"code": "TENANT_MATCH", "passed": true},
    {"code": "APPLICATION_ENTRY", "passed": true},
    {"code": "FUNCTION_PERMISSION", "passed": true},
    {"code": "RESOURCE_POLICY", "passed": true},
    {"code": "EXPORT_ALLOWED", "passed": false}
  ],
  "matched_policy_ids": [301],
  "denied_by_policy_ids": [402]
}
```

普通用户只获得可理解的拒绝原因；策略 ID、内部条件和敏感元数据仅授权管理员可见。

### 15.2 审计事件

至少记录：

- 数据目录发现、元数据查看；
- 查询、预览、下载、导出；
- GIS 图层访问、空间查询和编辑；
- 模型编辑、运行、取消、审批和发布；
- 跨系统 API 调用；
- 权限申请、审批、授予、变更、撤销和到期；
- 管理员策略模拟和授权解释；
- 批量操作、高敏数据和异常拒绝。

审计内容应包含主体、服务账号、租户、系统、项目、资源、动作、策略版本、结果、数据量、客户端、用途和 Trace ID。生产环境使用追加写、签名或外送存储防止篡改。

## 16. 建议 API

### 16.1 控制面

```text
GET/POST        /api/data-spaces
GET/PUT         /api/data-spaces/{id}
GET/POST        /api/data-resources
GET/PUT         /api/data-resources/{id}
GET/POST        /api/resource-policies
GET/PUT/DELETE  /api/resource-policies/{id}
POST            /api/resource-authorization/explain
GET/POST        /api/service-accounts
POST            /api/data-access-requests
POST            /api/data-access-requests/{id}/submit
POST            /api/data-access-grants/{id}/revoke
```

### 16.2 数据面

```text
POST /api/data-query
POST /api/data-export-jobs
GET  /api/data-export-jobs/{id}
GET  /api/gis/layers
POST /api/gis/spatial-query
POST /api/hydraulic/models/{id}/runs
GET  /api/hydraulic/runs/{id}/results
```

控制面接口负责策略和授权；数据面接口负责执行。两者都不得相信客户端传入的租户和归属信息。

## 17. 缓存与即时失权

- 策略缓存 Key 至少包含 `tenant_id/subject_id/application_id/action/resource_id/policy_version`；
- 用户、组织成员、角色、系统入口、项目成员、资源策略、字段策略或有效期变化时发布失效事件；
- 撤销后新请求立即拒绝；
- 已创建的下载地址使用短有效期，撤销高敏授权时支持服务端黑名单；
- 异步模型任务提交时保存授权快照，领取结果时再次实时鉴权；
- 搜索索引和汇总读模型需要记录授权版本，避免旧索引扩大可见范围。

## 18. 回归测试设计

### 18.1 基础隔离

- 跨租户资源 ID 伪造返回 404；
- 同租户跨系统无入口返回拒绝；
- 有系统入口但无资源策略时只能进入空系统，不返回业务数据；
- 同业务方向中拥有一个系统入口不能看到另一个系统原始资源；
- 项目成员退出或项目归档后立即禁止新数据动作。

### 18.2 角色和资源

- 同一用户在 GIS 可编辑、在水力模型只读；
- 角色有动作但资源未授权时拒绝；
- 资源授权但角色无动作时拒绝；
- 精确资源 DENY 覆盖父目录 ALLOW；
- 组织、应用和项目角色组合后授权解释结果稳定。

### 18.3 行、字段和空间

- 只返回授权行政区、DMA、项目红线或资产组；
- 未授权字段不进入 API 响应和导出文件；
- 无精确坐标权限时不能从瓦片、查询或导出旁路获得原始坐标；
- 汇总权限不能下钻原始明细；
- 时间范围到期后历史查询和新导出按策略拒绝。

### 18.4 数据出口

- 页面隐藏后直接调用 API 仍返回拒绝；
- 修改图层、资源、项目或对象存储 Key 不能越权；
- WMS/WFS/瓦片、搜索、缓存、对象存储和导出均执行同一授权边界；
- 导出权限与查询权限独立；
- 下载 URL 过期、撤销和重复使用符合策略。

### 18.5 跨系统和服务账号

- 水力模型服务账号只能读取授权 GIS 数据集和字段；
- 数据人员可查看采集/处理数据但无 `hydraulic:result:view` 时，结果列表、详情、文件、报表和导出均不可见；
- 拥有 `hydraulic:run:view-status` 或 `hydraulic:run:execute` 不自动获得模型结果载荷；
- 输入数据授权不沿血缘传播到模型结果，结果授权也不反向传播到原始监测数据；
- 服务账号可以读取输入并写入结果，但不能通过交互式接口读取或导出结果；
- 数据人员需要业务成果时，只能读取单独发布并授权的汇总资源；
- 个人账号凭据不能作为系统集成凭据；
- 服务账号停用或密钥轮换后旧令牌失效；
- 跨系统共享到期后新调用失败，既有审计和模型血缘保留。

### 18.6 流程与审计

- 未审批申请不生成有效授权；
- 敏感导出缺少双人审批时拒绝；
- 到期授权自动失效，紧急授权触发事后复核；
- 查询、下载、导出、共享、模型运行和拒绝事件均可审计；
- 授权解释可返回命中的角色、资源策略、字段策略和拒绝条件。

每轮继续执行迁移升降级、空库升级、Seed 幂等、API/UI 正反例、跨边界伪造、Warnings-as-errors、Ruff、敏感信息扫描和覆盖率不低于 90%。

## 19. 实施边界与优先级

### P0：真实数据接入前必须完成

- 应用级角色授予；
- 业务方向总览与具体系统驾驶舱拆分；
- 统一数据空间和资源目录；
- 资源查看、查询、下载和导出分离；
- GIS/API/对象存储服务端强制鉴权；
- 服务账号、短期令牌和数据访问审计；
- PostgreSQL RLS 或等价的数据库二次隔离。

### P1：形成可运营的数据权限产品

- 字段分级、脱敏和空间范围；
- 数据权限申请、审批、有效期和自动回收；
- 授权解释、影响分析和策略模拟；
- 跨系统资源共享、数据快照和血缘；
- 高权限职责分离和定期复核。

### P2：规模化治理

- 标签驱动策略、批量授权和组织同步；
- 异常授权检测、权限使用分析和零使用回收；
- 高敏租户独立存储与 KMS；
- 多查询引擎、GIS 服务和数据湖策略适配。

## 20. 最终边界

权限中心负责“谁可以在什么条件下对哪些资源执行什么动作”；数据中心负责“资源是什么、在哪里、如何查询和交付”；工单与流程中心负责“授权和数据问题如何申请、审批、处置、到期和回收”。

三者共享身份、租户、系统、项目、组织和审计上下文，但不得相互替代。数据中心不能只依赖权限中心页面隐藏，权限中心也不保存或直接处理全部业务数据。
