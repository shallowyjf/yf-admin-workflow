"""Persistence checks for system health."""

from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session


class HealthRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def database_ready(self) -> bool:
        with self._session_factory() as session:
            return session.scalar(text("SELECT 1")) == 1
