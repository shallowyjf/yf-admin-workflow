"""Globally unique tenant login names for unified authentication.

Revision ID: 0016_unified_login
Revises: 0015_platform_root
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_unified_login"
down_revision: str | None = "0015_platform_root"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sys_user") as batch_op:
        batch_op.add_column(sa.Column("login_name", sa.String(length=120)))

    op.execute(
        """
        UPDATE sys_user
        SET login_name = CASE
            WHEN (SELECT tenant_code FROM sys_tenant WHERE id = sys_user.tenant_id)
                = 'DEMO'
            THEN lower(username)
            ELSE lower(
                CASE
                    WHEN substr(
                        (SELECT tenant_code FROM sys_tenant
                         WHERE id = sys_user.tenant_id), 1, 5
                    ) = 'CITY_'
                    THEN substr(
                        (SELECT tenant_code FROM sys_tenant
                         WHERE id = sys_user.tenant_id), 6
                    )
                    ELSE (SELECT tenant_code FROM sys_tenant
                          WHERE id = sys_user.tenant_id)
                END || '.' || username
            )
        END
        """
    )

    with op.batch_alter_table("sys_user") as batch_op:
        batch_op.alter_column(
            "login_name",
            existing_type=sa.String(length=120),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_sys_user_login_name", ["login_name"]
        )


def downgrade() -> None:
    with op.batch_alter_table("sys_user") as batch_op:
        batch_op.drop_constraint("uq_sys_user_login_name", type_="unique")
        batch_op.drop_column("login_name")
