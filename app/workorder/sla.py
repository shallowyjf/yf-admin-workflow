"""SLA business-calendar calculations and default policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from .domain import WorkOrderValidationError


@dataclass(frozen=True)
class DefaultSlaPolicy:
    priority: str
    response_minutes: int
    resolve_minutes: int
    calendar_code: str


DEFAULT_SLA_POLICIES = (
    DefaultSlaPolicy("URGENT", 10, 60, "24X7"),
    DefaultSlaPolicy("HIGH", 30, 240, "BUSINESS_HOURS"),
    DefaultSlaPolicy("NORMAL", 60, 480, "BUSINESS_HOURS"),
)


class SlaCalendar:
    BUSINESS_START = time(9, 0)
    BUSINESS_END = time(18, 0)

    @classmethod
    def add_minutes(
        cls,
        started_at: datetime,
        minutes: int,
        calendar_code: str,
    ) -> datetime:
        if minutes <= 0:
            raise WorkOrderValidationError("SLA minutes must be positive")
        if calendar_code == "24X7":
            return started_at + timedelta(minutes=minutes)
        if calendar_code != "BUSINESS_HOURS":
            raise WorkOrderValidationError(
                f"unsupported SLA calendar: {calendar_code}"
            )

        current = cls._next_business_time(started_at)
        remaining = minutes
        while remaining:
            end_of_day = datetime.combine(current.date(), cls.BUSINESS_END)
            available = int((end_of_day - current).total_seconds() // 60)
            consumed = min(remaining, available)
            current += timedelta(minutes=consumed)
            remaining -= consumed
            if remaining:
                current = cls._next_business_time(
                    datetime.combine(current.date() + timedelta(days=1), cls.BUSINESS_START)
                )
        return current

    @classmethod
    def _next_business_time(cls, value: datetime) -> datetime:
        current = value
        while current.weekday() >= 5:
            current = datetime.combine(
                current.date() + timedelta(days=1),
                cls.BUSINESS_START,
            )
        if current.time() < cls.BUSINESS_START:
            return datetime.combine(current.date(), cls.BUSINESS_START)
        if current.time() >= cls.BUSINESS_END:
            return cls._next_business_time(
                datetime.combine(
                    current.date() + timedelta(days=1),
                    cls.BUSINESS_START,
                )
            )
        return current
