"""Executable standard DMA work-order closed-loop demonstration."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import Database
from app.iam.authorization import PermissionService
from app.iam.repository import IAMRepository
from app.iam.seed import seed_iam
from app.iam.service import IAMService
from app.workflow.domain import TaskAlreadyClaimed
from app.workflow.factory import build_workflow_service
from app.workflow.repository import WorkflowRepository
from app.workflow.seed import seed_workflow
from app.workorder.domain import InvalidWorkOrderTransition
from app.workorder.repository import WorkOrderRepository
from app.workorder.service import (
    CreateWorkOrderCommand,
    WorkOrderActor,
    WorkOrderService,
)


@dataclass(frozen=True)
class DmaDemoResult:
    work_order_id: int
    work_order_no: str
    status_path: tuple[str, ...]
    candidate_usernames: tuple[str, ...]
    claimed_by: str
    second_claim_conflict: bool
    timeline_actions: tuple[str, ...]
    final_status: str


def _required(entity, label: str):
    if entity is None:
        raise RuntimeError(f"missing demo seed entity: {label}")
    return entity


def run_dma_demo(session: Session) -> DmaDemoResult:
    iam_repository = IAMRepository(session)
    iam_service = IAMService(iam_repository)
    seed_iam(iam_service)
    workflow_repository = WorkflowRepository(session)
    seed_workflow(workflow_repository)
    workflow_service = build_workflow_service(session)
    work_order_service = WorkOrderService(
        WorkOrderRepository(session),
        PermissionService(iam_repository),
        workflow_service,
    )

    wangwu = _required(iam_service.get_user("wangwu"), "wangwu")
    lisi = _required(iam_service.get_user("lisi"), "lisi")
    zhaoliu = _required(iam_service.get_user("zhaoliu"), "zhaoliu")
    regulator = _required(iam_service.get_user("regulator"), "regulator")
    dispatch_org = _required(
        iam_service.get_organization("DISPATCH_CENTER"),
        "DISPATCH_CENTER",
    )
    pipe_org = _required(
        iam_service.get_organization("PIPE_OPERATION"),
        "PIPE_OPERATION",
    )
    regulator_org = _required(
        iam_service.get_organization("REGULATOR"),
        "REGULATOR",
    )
    wangwu_actor = WorkOrderActor(wangwu.id, dispatch_org.id)
    lisi_actor = WorkOrderActor(lisi.id, pipe_org.id)
    zhaoliu_actor = WorkOrderActor(zhaoliu.id, pipe_org.id)
    regulator_actor = WorkOrderActor(regulator.id, regulator_org.id)

    work_order = work_order_service.create(
        CreateWorkOrderCommand(
            title="DMA07 压力异常",
            work_order_type="DMA_PRESSURE_ANOMALY",
            source_type="DMA_MONITORING",
            source_id="DMA07",
            priority="HIGH",
            asset_type="DMA_ZONE",
            asset_id="DMA07",
            location="DMA07 分区",
            description="夜间最小流量和压力曲线异常",
        ),
        wangwu_actor,
    )
    status_path = [work_order.status]
    work_order = work_order_service.submit(
        work_order.id,
        wangwu_actor,
        "提交调度处置",
    )
    status_path.append(work_order.status)
    work_order = work_order_service.dispatch(
        work_order.id,
        pipe_org.id,
        wangwu_actor,
        "派给管网运行部抢修人员",
    )
    status_path.append(work_order.status)

    lisi_tasks = [
        task
        for task in workflow_service.list_my_tasks(lisi.id)
        if task.instance.business_id == work_order.id
        and task.task_type == "HANDLE"
    ]
    zhaoliu_tasks = [
        task
        for task in workflow_service.list_my_tasks(zhaoliu.id)
        if task.instance.business_id == work_order.id
        and task.task_type == "HANDLE"
    ]
    if len(lisi_tasks) != 1 or len(zhaoliu_tasks) != 1:
        raise RuntimeError("DMA handle task is not visible to both repairers")
    candidate_ids = {
        candidate.resolved_user_id for candidate in lisi_tasks[0].candidates
    }
    if candidate_ids != {lisi.id, zhaoliu.id}:
        raise RuntimeError(
            f"unexpected DMA candidates: {sorted(candidate_ids)}"
        )

    work_order = work_order_service.claim(
        work_order.id,
        lisi_actor,
        "李四认领",
    )
    status_path.append(work_order.status)
    second_claim_conflict = False
    try:
        work_order_service.claim(work_order.id, zhaoliu_actor, "赵六竞争认领")
    except (InvalidWorkOrderTransition, TaskAlreadyClaimed):
        second_claim_conflict = True
    if not second_claim_conflict:
        raise RuntimeError("second DMA claim unexpectedly succeeded")

    work_order = work_order_service.submit_result(
        work_order.id,
        lisi_actor,
        "已定位并修复 DMA07 漏点，压力恢复正常",
        "提交处理结果",
        regulator_org.id,
    )
    status_path.append(work_order.status)
    work_order = work_order_service.review(
        work_order.id,
        regulator_actor,
        "APPROVE",
        "复核通过",
    )
    status_path.append(work_order.status)
    work_order = work_order_service.close(
        work_order.id,
        wangwu_actor,
        "DMA07 异常闭环",
    )
    status_path.append(work_order.status)
    timeline = work_order_service.timeline(work_order.id, wangwu_actor)

    return DmaDemoResult(
        work_order_id=work_order.id,
        work_order_no=work_order.work_order_no,
        status_path=tuple(status_path),
        candidate_usernames=("lisi", "zhaoliu"),
        claimed_by="lisi",
        second_claim_conflict=second_claim_conflict,
        timeline_actions=tuple(action.action_type for action in timeline),
        final_status=work_order.status,
    )


def main() -> None:
    database = Database(get_settings().database_url)
    try:
        with database.session_factory() as session:
            result = run_dma_demo(session)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
