from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CongestionLevel(StrEnum):
    FREE = "free"
    LIGHT = "light"
    DENSE = "dense"
    TRAFFIC_JAM = "traffic_jam"
    SEVERE_TRAFFIC_JAM = "severe_traffic_jam"
    UNKNOWN = "unknown"


class Coordinate(BaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class TrafficSegment(BaseModel):
    id: str
    road: str
    direction: str
    from_name: str
    to_name: str
    origin: Coordinate
    destination: Coordinate
    free_flow_duration_seconds: int | None = None
    enabled: bool = True


class SegmentsConfig(BaseModel):
    segments: list[TrafficSegment]


class MeasurementStatus(StrEnum):
    OK = "OK"
    FAIL = "FAIL"


class TrafficMeasurement(BaseModel):
    """Измерение данных TomTom Flow Segment Data API."""

    timestamp: str
    segment_id: str
    current_speed_kmh: int | None = None
    free_flow_speed_kmh: int | None = None
    current_travel_time_seconds: int | None = None
    free_flow_travel_time_seconds: int | None = None
    confidence: float | None = None
    road_closure: bool = False
    frc: str | None = None
    status: MeasurementStatus
    error_message: str | None = None
    raw_response: dict[str, Any] | None = None


class CongestionResult(BaseModel):
    segment_id: str
    current_speed_kmh: int | None = None
    free_flow_speed_kmh: int | None = None
    current_travel_time_seconds: int | None = None
    free_flow_travel_time_seconds: int | None = None
    confidence: float | None = None
    road_closure: bool = False
    congestion_ratio: float | None = None
    congestion_level: CongestionLevel


class SnapshotSummary(BaseModel):
    total_segments: int
    successful_segments: int
    failed_segments: int
    traffic_jam_segments: int = 0
    severe_traffic_jam_segments: int = 0
