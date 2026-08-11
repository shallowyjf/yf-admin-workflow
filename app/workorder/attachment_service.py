"""Permission-checked work-order attachment use cases."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from typing import Protocol

from app.iam.authorization import PermissionService
from app.project.service import ProjectActor, ProjectService

from .domain import (
    WorkOrderActionType,
    WorkOrderNotFound,
    WorkOrderPermissionDenied,
    WorkOrderValidationError,
)
from .models import WorkOrderAction, WorkOrderAttachment
from .repository import WorkOrderRepository
from .service import WorkOrderActor


class AttachmentScanner(Protocol):
    def scan(self, filename: str, content_type: str, content: bytes) -> None: ...


class BasicAttachmentScanner:
    SIGNATURES = {
        "application/pdf": b"%PDF",
        "image/png": b"\x89PNG\r\n\x1a\n",
        "image/jpeg": b"\xff\xd8\xff",
    }

    def scan(self, filename: str, content_type: str, content: bytes) -> None:
        if content.startswith((b"MZ", b"\x7fELF")):
            raise WorkOrderValidationError("executable attachment is not allowed")
        if b"EICAR" in content.upper():
            raise WorkOrderValidationError("attachment security scan failed")
        signature = self.SIGNATURES.get(content_type)
        if signature is not None and not content.startswith(signature):
            raise WorkOrderValidationError(
                f"attachment content does not match {content_type}"
            )
        if content_type == "text/plain":
            try:
                content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise WorkOrderValidationError(
                    "text attachment must use UTF-8"
                ) from error


class WorkOrderAttachmentService:
    PERMISSION = "workorder:attachment"
    MAX_SIZE_BYTES = 5 * 1024 * 1024
    ALLOWED_TYPES = {
        ".jpeg": "image/jpeg",
        ".jpg": "image/jpeg",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".txt": "text/plain",
    }

    def __init__(
        self,
        repository: WorkOrderRepository,
        permission_service: PermissionService,
        scanner: AttachmentScanner | None = None,
        *,
        project_service: ProjectService | None = None,
    ) -> None:
        self.repository = repository
        self.permission_service = permission_service
        self.scanner = scanner or BasicAttachmentScanner()
        self.project_service = project_service

    def upload(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> WorkOrderAttachment:
        work_order = self._visible(work_order_id, actor, self.PERMISSION)
        normalized_name = self._filename(filename)
        extension = PurePosixPath(normalized_name).suffix.lower()
        expected_type = self.ALLOWED_TYPES.get(extension)
        if expected_type is None or content_type != expected_type:
            raise WorkOrderValidationError(
                "attachment type must be PDF, PNG, JPEG, or UTF-8 text"
            )
        if not content:
            raise WorkOrderValidationError("attachment must not be empty")
        if len(content) > self.MAX_SIZE_BYTES:
            raise WorkOrderValidationError("attachment exceeds 5 MiB limit")
        self.scanner.scan(normalized_name, content_type, content)
        attachment = WorkOrderAttachment(
            work_order_id=work_order.id,
            uploader_id=actor.user_id,
            filename=normalized_name,
            content_type=content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            scan_status="CLEAN",
            content_blob=content,
        )
        self.repository.add(attachment)
        self.repository.flush()
        self.repository.add(
            WorkOrderAction(
                work_order_id=work_order.id,
                action_type=WorkOrderActionType.ATTACHMENT_UPLOAD.value,
                operator_id=actor.user_id,
                from_status=work_order.status,
                to_status=work_order.status,
                comment=normalized_name,
                payload_json={
                    "attachment_id": attachment.id,
                    "content_type": content_type,
                    "size_bytes": len(content),
                    "sha256": attachment.sha256,
                },
            )
        )
        self.repository.commit()
        self.repository.refresh(attachment)
        return attachment

    def list_for_work_order(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
    ) -> list[WorkOrderAttachment]:
        work_order = self._visible(work_order_id, actor, "workorder:view")
        return self.repository.list_attachments(work_order.id)

    def download(
        self,
        work_order_id: int,
        attachment_id: int,
        actor: WorkOrderActor,
    ) -> WorkOrderAttachment:
        work_order = self._visible(work_order_id, actor, "workorder:view")
        attachment = self.repository.get_attachment(attachment_id)
        if attachment is None or attachment.work_order_id != work_order.id:
            raise WorkOrderNotFound(f"attachment not found: {attachment_id}")
        if attachment.scan_status != "CLEAN":
            raise WorkOrderPermissionDenied("attachment is not cleared for download")
        return attachment

    def _visible(
        self,
        work_order_id: int,
        actor: WorkOrderActor,
        permission_code: str,
    ):
        if not self.permission_service.has_permission(
            actor.user_id,
            permission_code,
            actor.active_org_id,
        ):
            raise WorkOrderPermissionDenied(f"missing permission: {permission_code}")
        scope = self.permission_service.work_order_scope(
            actor.user_id,
            permission_code,
            actor.active_org_id,
        )
        work_order = self.repository.get_visible(work_order_id, scope)
        if work_order is None:
            raise WorkOrderNotFound(f"work order not found: {work_order_id}")
        if self.project_service is not None and self.project_service.repository.list_projects():
            if (
                actor.tenant_id is None or actor.application_id is None
                or actor.project_id is None or work_order.tenant_id != actor.tenant_id
                or work_order.application_id != actor.application_id
                or work_order.project_id != actor.project_id
            ):
                raise WorkOrderPermissionDenied(
                    "attachment does not belong to the active project context"
                )
            try:
                self.project_service.require_operational_permission(
                    actor.project_id, ProjectActor(actor.user_id, actor.active_org_id),
                    permission_code, allow_archived=permission_code == "workorder:view",
                )
            except Exception as error:
                raise WorkOrderPermissionDenied(str(error)) from error
        return work_order

    @staticmethod
    def _filename(value: str) -> str:
        normalized = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not normalized or normalized in {".", ".."} or len(normalized) > 255:
            raise WorkOrderValidationError("invalid attachment filename")
        return normalized
