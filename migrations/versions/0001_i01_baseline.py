"""I01 database baseline.

Revision ID: 0001_i01
Revises:
Create Date: 2026-08-07
"""

from collections.abc import Sequence

revision: str = "0001_i01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Reserve the initial revision; business tables begin in I02."""


def downgrade() -> None:
    """Return to the pre-I01 baseline."""
