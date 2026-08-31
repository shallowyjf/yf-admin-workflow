"""Tenant-safe persistence for GIS authorization."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.data_permission.models import BusinessResource

from .models import (
    GISExportJob,
    GISFeature,
    ResourceField,
    ResourceFieldPolicy,
    SpatialScopeGrant,
)


class GISPermissionRepository:
    def __init__(self, session: Session, tenant_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def add(self, entity):
        self.session.add(entity)
        return entity

    def commit(self) -> None:
        self.session.commit()

    def refresh(self, entity) -> None:
        self.session.refresh(entity)

    def get_gis_resource(self, resource_id: int) -> BusinessResource | None:
        return self.session.scalar(
            select(BusinessResource).where(
                BusinessResource.id == resource_id,
                BusinessResource.tenant_id == self.tenant_id,
                BusinessResource.resource_type == "GIS_LAYER",
                BusinessResource.status == "ACTIVE",
            )
        )

    def get_field(self, resource_id: int, field_code: str) -> ResourceField | None:
        return self.session.scalar(
            select(ResourceField).where(
                ResourceField.tenant_id == self.tenant_id,
                ResourceField.resource_id == resource_id,
                ResourceField.field_code == field_code,
            )
        )

    def get_field_by_id(self, field_id: int) -> ResourceField | None:
        return self.session.scalar(
            select(ResourceField).where(
                ResourceField.id == field_id,
                ResourceField.tenant_id == self.tenant_id,
            )
        )

    def list_fields(self, resource_id: int) -> list[ResourceField]:
        return list(
            self.session.scalars(
                select(ResourceField)
                .where(
                    ResourceField.tenant_id == self.tenant_id,
                    ResourceField.resource_id == resource_id,
                    ResourceField.is_active.is_(True),
                )
                .order_by(ResourceField.id)
            )
        )

    def get_field_policy(
        self, role_id: int, resource_field_id: int
    ) -> ResourceFieldPolicy | None:
        return self.session.scalar(
            select(ResourceFieldPolicy).where(
                ResourceFieldPolicy.tenant_id == self.tenant_id,
                ResourceFieldPolicy.role_id == role_id,
                ResourceFieldPolicy.resource_field_id == resource_field_id,
            )
        )

    def list_field_policies(
        self, resource_id: int, role_ids: set[int]
    ) -> list[ResourceFieldPolicy]:
        if not role_ids:
            return []
        return list(
            self.session.scalars(
                select(ResourceFieldPolicy)
                .join(ResourceField)
                .where(
                    ResourceFieldPolicy.tenant_id == self.tenant_id,
                    ResourceFieldPolicy.role_id.in_(role_ids),
                    ResourceFieldPolicy.is_active.is_(True),
                    ResourceField.resource_id == resource_id,
                    ResourceField.is_active.is_(True),
                )
                .options(selectinload(ResourceFieldPolicy.resource_field))
            )
        )

    def get_spatial_grant(
        self,
        role_id: int,
        resource_id: int,
        scope_type: str,
        scope_value: str,
    ) -> SpatialScopeGrant | None:
        return self.session.scalar(
            select(SpatialScopeGrant).where(
                SpatialScopeGrant.tenant_id == self.tenant_id,
                SpatialScopeGrant.role_id == role_id,
                SpatialScopeGrant.resource_id == resource_id,
                SpatialScopeGrant.scope_type == scope_type,
                SpatialScopeGrant.scope_value == scope_value,
            )
        )

    def list_spatial_grants(
        self, resource_id: int, role_ids: set[int]
    ) -> list[SpatialScopeGrant]:
        if not role_ids:
            return []
        return list(
            self.session.scalars(
                select(SpatialScopeGrant)
                .where(
                    SpatialScopeGrant.tenant_id == self.tenant_id,
                    SpatialScopeGrant.resource_id == resource_id,
                    SpatialScopeGrant.role_id.in_(role_ids),
                    SpatialScopeGrant.is_active.is_(True),
                )
                .order_by(SpatialScopeGrant.id)
            )
        )

    def get_feature(self, resource_id: int, feature_key: str) -> GISFeature | None:
        return self.session.scalar(
            select(GISFeature).where(
                GISFeature.tenant_id == self.tenant_id,
                GISFeature.resource_id == resource_id,
                GISFeature.feature_key == feature_key,
            )
        )

    def list_features(self, resource_id: int) -> list[GISFeature]:
        return list(
            self.session.scalars(
                select(GISFeature)
                .where(
                    GISFeature.tenant_id == self.tenant_id,
                    GISFeature.resource_id == resource_id,
                    GISFeature.status == "ACTIVE",
                )
                .order_by(GISFeature.id)
            )
        )

    def list_export_jobs(self, requested_by: int | None = None) -> list[GISExportJob]:
        statement = (
            select(GISExportJob)
            .where(GISExportJob.tenant_id == self.tenant_id)
            .options(selectinload(GISExportJob.resource))
        )
        if requested_by is not None:
            statement = statement.where(GISExportJob.requested_by == requested_by)
        return list(
            self.session.scalars(
                statement.order_by(GISExportJob.created_at.desc(), GISExportJob.id.desc())
            )
        )
