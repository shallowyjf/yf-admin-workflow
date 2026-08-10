"""Shared pagination value objects."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PageResult[T]:
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)
