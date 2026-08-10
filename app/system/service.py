"""System health use cases."""

from dataclasses import dataclass

from .repository import HealthRepository


@dataclass(frozen=True)
class HealthStatus:
    status: str
    database: str
    iteration: str = "I14"
    version: str = "0.1.0"


class HealthService:
    def __init__(self, repository: HealthRepository) -> None:
        self._repository = repository

    def check(self) -> HealthStatus:
        database_status = "ok" if self._repository.database_ready() else "unavailable"
        return HealthStatus(
            status="ok" if database_status == "ok" else "degraded",
            database=database_status,
        )
