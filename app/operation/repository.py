"""Saved-view persistence."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SavedView


class SavedViewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, user_id: int, module: str) -> list[SavedView]:
        return list(
            self.session.scalars(
                select(SavedView)
                .where(SavedView.user_id == user_id, SavedView.module == module)
                .order_by(SavedView.is_default.desc(), SavedView.name)
            )
        )

    def get(self, saved_view_id: int) -> SavedView | None:
        return self.session.get(SavedView, saved_view_id)

    def get_by_name(self, user_id: int, module: str, name: str) -> SavedView | None:
        return self.session.scalar(
            select(SavedView).where(
                SavedView.user_id == user_id,
                SavedView.module == module,
                SavedView.name == name,
            )
        )

    def add(self, entity: SavedView) -> None:
        self.session.add(entity)

    def delete(self, entity: SavedView) -> None:
        self.session.delete(entity)

    def commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def refresh(self, entity: SavedView) -> None:
        self.session.refresh(entity)
