"""Deterministic demo data for the first product iteration."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock
from typing import Any


ZONES: list[dict[str, Any]] = [
    {
        "id": "central",
        "name": "中心城区 DMA",
        "short_name": "中心城区",
        "supply": 5.31,
        "leakage": 6.2,
        "pressure": 0.36,
        "alarms": 0,
        "online_rate": 99.4,
        "status": "healthy",
        "status_text": "运行平稳",
        "position": {"x": 43, "y": 45},
    },
    {
        "id": "east",
        "name": "东城 DMA",
        "short_name": "东城片区",
        "supply": 4.76,
        "leakage": 10.8,
        "pressure": 0.29,
        "alarms": 2,
        "online_rate": 97.8,
        "status": "alert",
        "status_text": "重点关注",
        "position": {"x": 72, "y": 40},
    },
    {
        "id": "north",
        "name": "北城 DMA",
        "short_name": "北城片区",
        "supply": 3.98,
        "leakage": 8.1,
        "pressure": 0.31,
        "alarms": 1,
        "online_rate": 98.9,
        "status": "warning",
        "status_text": "持续观察",
        "position": {"x": 46, "y": 20},
    },
    {
        "id": "south",
        "name": "南城 DMA",
        "short_name": "南城片区",
        "supply": 4.37,
        "leakage": 6.7,
        "pressure": 0.38,
        "alarms": 2,
        "online_rate": 98.6,
        "status": "warning",
        "status_text": "工单处理中",
        "position": {"x": 50, "y": 74},
    },
]


EVENTS: list[dict[str, Any]] = [
    {
        "id": "EVT-260807-01",
        "zone_id": "east",
        "severity": "high",
        "severity_text": "高",
        "type": "夜间小流量异常",
        "location": "东城 DMA-03 / 青云路",
        "occurred_at": "2026-08-07 02:18",
        "status": "pending",
        "status_text": "待确认",
        "description": "连续 40 分钟最小夜流高于近 7 日基线 31%，建议核查阀门与疑似漏点。",
    },
    {
        "id": "EVT-260807-02",
        "zone_id": "south",
        "severity": "medium",
        "severity_text": "中",
        "type": "压力越下限",
        "location": "南城 DMA-02 / 临江小区",
        "occurred_at": "2026-08-07 07:42",
        "status": "processing",
        "status_text": "处理中",
        "description": "早高峰末梢压力降至 0.19 MPa，调度员已安排二供泵房联查。",
        "ack_by": "调度中心",
        "updated_at": "2026-08-07 08:05",
    },
    {
        "id": "EVT-260806-09",
        "zone_id": "north",
        "severity": "medium",
        "severity_text": "中",
        "type": "远传设备离线",
        "location": "北城 DMA-01 / 计量井 N17",
        "occurred_at": "2026-08-06 23:06",
        "status": "pending",
        "status_text": "待确认",
        "description": "流量计连续 2 个采集周期无数据，平台已自动切换估算值。",
    },
    {
        "id": "EVT-260806-07",
        "zone_id": "east",
        "severity": "low",
        "severity_text": "低",
        "type": "瞬时流量波动",
        "location": "东城 DMA-01 / 迎宾大道",
        "occurred_at": "2026-08-06 18:21",
        "status": "resolved",
        "status_text": "已关闭",
        "description": "施工临时取水造成短时波动，已核实并归档。",
        "ack_by": "管网运行部",
        "updated_at": "2026-08-06 19:10",
    },
]


TREND_LABELS = ["00:00", "03:00", "06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]
BASE_FLOW = [612, 548, 721, 932, 884, 896, 1012, 805]
BASE_PRESSURE = [0.37, 0.38, 0.34, 0.31, 0.33, 0.32, 0.29, 0.35]


class DemoRepository:
    """Small in-memory repository with deterministic state for demos and tests."""

    def __init__(self) -> None:
        self._zones = deepcopy(ZONES)
        self._events = deepcopy(EVENTS)
        self._lock = Lock()

    @property
    def zones(self) -> list[dict[str, Any]]:
        return deepcopy(self._zones)

    def list_events(self, zone_id: str | None = None) -> list[dict[str, Any]]:
        events = self._events
        if zone_id and zone_id != "all":
            events = [event for event in events if event["zone_id"] == zone_id]
        return deepcopy(events)

    def acknowledge_event(self, event_id: str, operator: str) -> dict[str, Any] | None:
        with self._lock:
            event = next((item for item in self._events if item["id"] == event_id), None)
            if event is None:
                return None
            if event["status"] == "pending":
                event["status"] = "processing"
                event["status_text"] = "处理中"
                event["ack_by"] = operator
                event["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            return deepcopy(event)


def build_overview(repository: DemoRepository, zone_id: str) -> dict[str, Any] | None:
    zones = repository.zones
    if zone_id == "all":
        selected = zones
        name = "全域供水"
        multiplier = 1.0
    else:
        zone = next((item for item in zones if item["id"] == zone_id), None)
        if zone is None:
            return None
        selected = [zone]
        name = zone["name"]
        multiplier = zone["supply"] / 18.42

    supply = round(sum(item["supply"] for item in selected), 2)
    weighted_leakage = round(
        sum(item["leakage"] * item["supply"] for item in selected) / supply, 1
    )
    pressure = round(sum(item["pressure"] for item in selected) / len(selected), 2)
    alarms = sum(item["alarms"] for item in selected)
    online_rate = round(sum(item["online_rate"] for item in selected) / len(selected), 1)
    events = repository.list_events(zone_id)

    return {
        "scope": {"id": zone_id, "name": name},
        "metrics": {
            "supply": {"value": supply, "unit": "万 m³", "delta": 2.4, "direction": "up"},
            "leakage": {
                "value": weighted_leakage,
                "unit": "%",
                "delta": -0.6,
                "direction": "down",
            },
            "pressure": {"value": pressure, "unit": "MPa", "delta": 0.01, "direction": "up"},
            "alarms": {"value": alarms, "unit": "条", "delta": 2, "direction": "up"},
            "online_rate": {"value": online_rate, "unit": "%"},
        },
        "trend": {
            "labels": TREND_LABELS,
            "flow": [round(value * multiplier) for value in BASE_FLOW],
            "pressure": [round(value + (pressure - 0.34), 2) for value in BASE_PRESSURE],
        },
        "zones": zones,
        "events": events,
        "summary": {
            "pending": sum(event["status"] == "pending" for event in events),
            "processing": sum(event["status"] == "processing" for event in events),
            "resolved": sum(event["status"] == "resolved" for event in events),
        },
        "updated_at": "2026-08-07 09:30",
    }
