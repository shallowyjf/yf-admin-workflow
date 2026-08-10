"""Ownership-enforced saved-view use cases."""

from .models import SavedView
from .repository import SavedViewRepository


class SavedViewError(Exception):
    pass


class SavedViewService:
    MODULES = frozenset({"WORKORDERS", "ORGANIZATIONS", "USERS", "ROLES"})

    def __init__(self, repository: SavedViewRepository) -> None:
        self.repository = repository

    def list(self, user_id: int, module: str) -> list[SavedView]:
        return self.repository.list(user_id, self._module(module))

    def save(
        self,
        user_id: int,
        module: str,
        name: str,
        filters: dict,
        is_default: bool,
    ) -> SavedView:
        normalized_module = self._module(module)
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 80:
            raise SavedViewError("view name must contain 1..80 characters")
        if len(str(filters)) > 4000:
            raise SavedViewError("saved filters are too large")
        entity = self.repository.get_by_name(
            user_id, normalized_module, normalized_name
        )
        if entity is None:
            entity = SavedView(
                user_id=user_id,
                module=normalized_module,
                name=normalized_name,
                filters_json=filters,
            )
            self.repository.add(entity)
        entity.filters_json = filters
        if is_default:
            for item in self.repository.list(user_id, normalized_module):
                item.is_default = False
        entity.is_default = is_default
        self.repository.commit()
        self.repository.refresh(entity)
        return entity

    def delete(self, user_id: int, saved_view_id: int) -> None:
        entity = self.repository.get(saved_view_id)
        if entity is None or entity.user_id != user_id:
            raise SavedViewError("saved view not found")
        self.repository.delete(entity)
        self.repository.commit()

    def _module(self, module: str) -> str:
        normalized = module.strip().upper()
        if normalized not in self.MODULES:
            raise SavedViewError("unsupported saved-view module")
        return normalized
