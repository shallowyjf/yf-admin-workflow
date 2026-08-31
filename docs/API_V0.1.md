# V0.1 API 清单

交互式文档位于 `/docs`，所有业务接口除登录和健康检查外均使用 `yf_session` Cookie 鉴权，并在 Service 层按当前活动组织二次鉴权。

| 领域 | 方法与路径 | 能力 |
| --- | --- | --- |
| System | `GET /health` | 应用、数据库、版本与迭代健康状态 |
| Auth | `POST /auth/login`、`POST /auth/logout` | 登录、退出 |
| Auth | `GET /auth/me`、`POST /auth/active-org` | 当前用户、有效权限和活动组织切换 |
| City Lifeline | `GET /api/lifeline/structure` | 当前账号可见的系统、项目、参与组织、成员角色与默认权限矩阵 |
| City Lifeline | `GET/POST /api/lifeline/projects` | 可见项目列表、新建项目 |
| City Lifeline | `GET/PUT/DELETE /api/lifeline/projects/{id}` | 项目详情、编辑、仅空项目安全删除 |
| City Lifeline | `PUT /api/lifeline/projects/{id}/organizations` | 原子替换项目参与组织与牵头方 |
| City Lifeline | `PUT /api/lifeline/projects/{id}/members` | 原子替换项目成员与项目角色 |
| City Lifeline | `GET /api/lifeline/projects/{id}/authorization-explain` | 解释用户项目授权链 |
| City Lifeline | `PUT /api/lifeline/users/{id}/applications` | 配置用户生命线系统入口 |
| Data permission | `GET /api/data-permissions/spaces` | 只返回当前账号通过完整授权链的数据空间 |
| Data permission | `GET /api/data-permissions/resources`、`GET /api/data-permissions/resources/{id}` | 按系统、操作过滤可访问资源及资源详情 |
| Data permission | `GET /api/data-permissions/resources/{id}/authorization-explain` | 返回入口、应用角色、操作权限、ALLOW/DENY 与最终决策 |
| Data permission | `POST /api/data-permissions/spaces`、`POST /api/data-permissions/resources` | 管理员创建数据空间与资源目录 |
| Data permission | `PUT /api/data-permissions/applications/{id}/roles` | 给组织成员配置系统内角色 |
| Data permission | `POST /api/data-permissions/resources/{id}/policies` | 配置角色级资源 ALLOW/DENY 策略 |
| GIS permission | `GET /api/gis/resources/{id}/features` | 按角色空间范围裁剪设施、字段和坐标精度 |
| GIS permission | `POST /api/gis/resources/{id}/exports`、`GET /api/gis/exports` | 创建并查询当前用户隔离的模拟导出审计任务 |
| GIS permission | `POST /api/gis/resources/{id}/fields` | 配置 GIS 图层字段目录 |
| GIS permission | `PUT /api/gis/fields/{id}/policy` | 配置角色字段 VISIBLE/MASKED/HIDDEN 策略 |
| GIS permission | `POST /api/gis/resources/{id}/spatial-scopes` | 配置角色行政区、DMA、项目红线等空间范围和坐标精度 |
| Auth | `POST /auth/active-application`、`POST /auth/active-project` | 切换活动生命线系统和工程项目 |
| Organization | `GET/POST /api/orgs` | 列表、新增 |
| Organization | `GET /api/orgs/tree` | 组织树 |
| Organization | `GET/PUT/DELETE /api/orgs/{id}` | 详情、编辑、安全删除 |
| Organization | `POST /api/orgs/{id}/status` | 启停 |
| User | `GET/POST /api/users` | 列表、新增 |
| User | `GET/PUT /api/users/{id}` | 详情、资料编辑 |
| User | `POST /api/users/{id}/status` | 启停并撤销会话 |
| User | `POST /api/users/{id}/password` | 管理员重置密码并撤销会话 |
| User | `PUT /api/users/{id}/memberships` | 原子替换多组织角色/岗位关系 |
| Role | `GET/POST /api/roles` | 列表、新增 |
| Role | `GET/PUT /api/roles/{id}` | 详情、编辑 |
| Role | `POST /api/roles/{id}/status` | 启停 |
| Role | `PUT /api/roles/{id}/authorization` | 原子替换 Permission + DataScope |
| Position | `GET/POST /api/positions` | 列表、新增 |
| Position | `GET/PUT/DELETE /api/positions/{id}` | 详情、编辑、安全删除 |
| Position | `POST /api/positions/{id}/status` | 启停 |
| Permission | `GET/POST /api/permissions` | 字典列表、新增 |
| Permission | `GET/PUT/DELETE /api/permissions/{id}` | 详情、描述编辑、安全删除 |
| Audit | `GET /api/iam/audit-logs` | 按实体、动作、操作人分页过滤 |
| Work order | `GET/POST /api/workorders` | 数据范围内列表、新建 |
| Work order | `GET /api/workorders/{id}` | 详情 |
| Work order | `POST /api/workorders/{id}/submit` | 提交 |
| Work order | `POST /api/workorders/{id}/dispatch` | 派单 |
| Work order | `POST /api/workorders/{id}/claim` | 候选人认领 |
| Work order | `POST /api/workorders/{id}/result` | 提交处理结果 |
| Work order | `POST /api/workorders/{id}/transfer` | 将处理中工单转给当前组织的有效处理人 |
| Work order | `POST /api/workorders/{id}/comments` | 追加协作评论 |
| Work order | `POST /api/workorders/{id}/urge` | 对在途工单发起催办并留痕 |
| Work order | `POST /api/workorders/sla/evaluate` | 在当前数据范围内执行 SLA 超时检查与升级 |
| Attachment | `POST/GET /api/workorders/{id}/attachments` | 安全上传、查询附件 |
| Attachment | `GET /api/workorders/{id}/attachments/{attachment_id}/download` | 数据范围鉴权后下载已通过扫描的附件 |
| Work order | `POST /api/workorders/{id}/review` | 通过或驳回 |
| Work order | `POST /api/workorders/{id}/close` | 关闭 |
| Work order | `GET /api/workorders/{id}/timeline` | 动作时间线 |
| Workflow | `GET /api/tasks/mine` | 当前用户候选/已分配任务 |
| Notification | `GET /api/notifications` | 当前用户站内通知 |
| Notification | `POST /api/notifications/{id}/read` | 通知已读回执 |
| Operations | `GET/POST /api/saved-views`、`DELETE /api/saved-views/{id}` | 用户隔离的筛选视图 |
| Work order | `GET /api/workorders/search` | DataScope 内服务端分页、组合筛选与排序 |
| Work order | `POST /api/workorders/batch/dispatch`、`POST /api/workorders/batch/urge` | 逐条鉴权的批量动作与部分成功报告 |
| IAM operations | `GET /api/iam/batch/search` | 组织、用户、角色服务端分页 |
| IAM operations | `GET /api/iam/batch/export`、`POST /api/iam/batch/import` | JSON 导出、逐行导入与错误报告 |

OpenAPI 是请求字段、返回结构与状态码的唯一机器可读契约。本文件用于发布范围导航，不复制 Schema。
