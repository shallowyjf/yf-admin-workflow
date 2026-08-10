# V0.1 API 清单

交互式文档位于 `/docs`，所有业务接口除登录和健康检查外均使用 `yf_session` Cookie 鉴权，并在 Service 层按当前活动组织二次鉴权。

| 领域 | 方法与路径 | 能力 |
| --- | --- | --- |
| System | `GET /health` | 应用、数据库、版本与迭代健康状态 |
| Auth | `POST /auth/login`、`POST /auth/logout` | 登录、退出 |
| Auth | `GET /auth/me`、`POST /auth/active-org` | 当前用户、有效权限和活动组织切换 |
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
| Work order | `POST /api/workorders/{id}/review` | 通过或驳回 |
| Work order | `POST /api/workorders/{id}/close` | 关闭 |
| Work order | `GET /api/workorders/{id}/timeline` | 动作时间线 |
| Workflow | `GET /api/tasks/mine` | 当前用户候选/已分配任务 |

OpenAPI 是请求字段、返回结构与状态码的唯一机器可读契约。本文件用于发布范围导航，不复制 Schema。
