import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from almaty_traffic.models import MeasurementStatus, RouteMeasurement

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
  distance_meters INTEGER,
  duration_seconds INTEGER,
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

    async def insert_measurement(self, m: RouteMeasurement) -> None:
        async with self._conn() as conn:
            await conn.execute(
                """INSERT INTO measurements
                   (timestamp, segment_id, distance_meters, duration_seconds,
                    status, error_message, raw_response)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    m.timestamp,
                    m.segment_id,
                    m.distance_meters,
                    m.duration_seconds,
                    m.status.value,
                    m.error_message,
                    json.dumps(m.raw_response, ensure_ascii=False) if m.raw_response else None,
                ),
            )

    async def get_measurements(
        self, segment_id: str, hours: int = 24, timezone: str = "Asia/Almaty"
    ) -> list[RouteMeasurement]:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        cutoff = (datetime.now(ZoneInfo(timezone)) - timedelta(hours=hours)).isoformat()

        async with self._conn() as conn:
            cursor = await conn.execute(
                """SELECT timestamp, segment_id, distance_meters, duration_seconds,
                          status, error_message, raw_response
                   FROM measurements
                   WHERE segment_id = ?
                     AND timestamp >= ?
                   ORDER BY timestamp""",
                (segment_id, cutoff),
            )
            rows = await cursor.fetchall()

        return [
            RouteMeasurement(
                timestamp=row["timestamp"],
                segment_id=row["segment_id"],
                distance_meters=row["distance_meters"],
                duration_seconds=row["duration_seconds"],
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
