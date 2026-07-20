import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from almaty_traffic.models import MeasurementStatus, TrafficMeasurement

_SCHEMA = """
CREATE TABLE IF NOT EXISTS segments (
  id TEXT PRIMARY KEY,
  road TEXT NOT NULL,
  direction TEXT NOT NULL,
  from_name TEXT NOT NULL,
  to_name TEXT NOT NULL,
  origin_lat REAL NOT NULL,
  origin_lon REAL NOT NULL,
  destination_lat REAL NOT NULL,
  destination_lon REAL NOT NULL,
  free_flow_duration_seconds INTEGER,
  enabled INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  segment_id TEXT NOT NULL,
  current_speed_kmh INTEGER,
  free_flow_speed_kmh INTEGER,
  current_travel_time_seconds INTEGER,
  free_flow_travel_time_seconds INTEGER,
  confidence REAL,
  road_closure INTEGER NOT NULL DEFAULT 0,
  frc TEXT,
  status TEXT NOT NULL,
  error_message TEXT,
  raw_response TEXT,
  FOREIGN KEY(segment_id) REFERENCES segments(id)
);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  json_payload TEXT NOT NULL,
  text_payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_measurements_timestamp
ON measurements(timestamp);

CREATE INDEX IF NOT EXISTS idx_measurements_segment_timestamp
ON measurements(segment_id, timestamp);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path

    @asynccontextmanager
    async def _conn(self) -> AsyncIterator[aiosqlite.Connection]:
        conn = await aiosqlite.connect(self._path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
            await conn.commit()
        finally:
            await conn.close()

    async def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with self._conn() as conn:
            await conn.executescript(_SCHEMA)

    async def insert_measurement(self, m: TrafficMeasurement) -> None:
        async with self._conn() as conn:
            await conn.execute(
                """INSERT INTO measurements
                   (timestamp, segment_id, current_speed_kmh, free_flow_speed_kmh,
                    current_travel_time_seconds, free_flow_travel_time_seconds,
                    confidence, road_closure, frc, status, error_message, raw_response)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    m.timestamp,
                    m.segment_id,
                    m.current_speed_kmh,
                    m.free_flow_speed_kmh,
                    m.current_travel_time_seconds,
                    m.free_flow_travel_time_seconds,
                    m.confidence,
                    1 if m.road_closure else 0,
                    m.frc,
                    m.status.value,
                    m.error_message,
                    json.dumps(m.raw_response, ensure_ascii=False) if m.raw_response else None,
                ),
            )

    async def get_measurements(
        self, segment_id: str, hours: int = 24, timezone: str = "Asia/Almaty"
    ) -> list[TrafficMeasurement]:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        cutoff = (datetime.now(ZoneInfo(timezone)) - timedelta(hours=hours)).isoformat()

        async with self._conn() as conn:
            cursor = await conn.execute(
                """SELECT timestamp, segment_id, current_speed_kmh, free_flow_speed_kmh,
                          current_travel_time_seconds, free_flow_travel_time_seconds,
                          confidence, road_closure, frc, status, error_message, raw_response
                   FROM measurements
                   WHERE segment_id = ?
                     AND timestamp >= ?
                   ORDER BY timestamp""",
                (segment_id, cutoff),
            )
            rows = await cursor.fetchall()

        return [
            TrafficMeasurement(
                timestamp=row["timestamp"],
                segment_id=row["segment_id"],
                current_speed_kmh=row["current_speed_kmh"],
                free_flow_speed_kmh=row["free_flow_speed_kmh"],
                current_travel_time_seconds=row["current_travel_time_seconds"],
                free_flow_travel_time_seconds=row["free_flow_travel_time_seconds"],
                confidence=row["confidence"],
                road_closure=bool(row["road_closure"]),
                frc=row["frc"],
                status=MeasurementStatus(row["status"]),
                error_message=row["error_message"],
                raw_response=json.loads(row["raw_response"]) if row["raw_response"] else None,
            )
            for row in rows
        ]

    async def insert_snapshot(self, json_payload: str, text_payload: str) -> None:
        from almaty_traffic.utils import now_almaty_iso

        async with self._conn() as conn:
            await conn.execute(
                "INSERT INTO snapshots (timestamp, json_payload, text_payload) VALUES (?, ?, ?)",
                (now_almaty_iso(), json_payload, text_payload),
            )

    async def get_latest_snapshot(self) -> dict[str, str] | None:
        async with self._conn() as conn:
            cursor = await conn.execute(
                "SELECT json_payload, text_payload FROM snapshots ORDER BY id DESC LIMIT 1"
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return {"json_payload": row["json_payload"], "text_payload": row["text_payload"]}
