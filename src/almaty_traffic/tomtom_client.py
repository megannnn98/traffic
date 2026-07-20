import asyncio
import logging
from typing import Any

import httpx

from almaty_traffic.models import MeasurementStatus, TrafficMeasurement, TrafficSegment
from almaty_traffic.utils import now_almaty_iso

logger = logging.getLogger(__name__)

API_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"


class TomTomTrafficClient:
    """Клиент TomTom Flow Segment Data API."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        api_key: str,
        timeout_seconds: float = 15.0,
        max_concurrent: int = 5,
    ) -> None:
        self._http = http_client
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def _fetch_one(self, segment: TrafficSegment) -> TrafficMeasurement:
        """Запрос данных для одной точки (road segment)."""
        point = f"{segment.origin.latitude},{segment.origin.longitude}"

        params: dict[str, Any] = {
            "key": self._api_key,
            "point": point,
            "unit": "kmph",
        }

        try:
            async with self._semaphore:
                resp = await self._http.get(API_URL, params=params, timeout=self._timeout)
        except httpx.TimeoutException as e:
            logger.warning("Таймаут запроса для участка %s", segment.id)
            return TrafficMeasurement(
                timestamp=now_almaty_iso(),
                segment_id=segment.id,
                status=MeasurementStatus.FAIL,
                error_message=f"Таймаут: {e}",
            )
        except httpx.HTTPError as e:
            logger.warning("Сетевая ошибка для участка %s: %s", segment.id, e)
            return TrafficMeasurement(
                timestamp=now_almaty_iso(),
                segment_id=segment.id,
                status=MeasurementStatus.FAIL,
                error_message=f"Сетевая ошибка: {e}",
            )

        if resp.status_code != 200:
            error_text = _safe_error_text(resp)
            logger.warning("HTTP %d для участка %s: %s", resp.status_code, segment.id, error_text)
            return TrafficMeasurement(
                timestamp=now_almaty_iso(),
                segment_id=segment.id,
                status=MeasurementStatus.FAIL,
                error_message=f"HTTP {resp.status_code}: {error_text}",
            )

        try:
            data = resp.json()
        except Exception as e:
            logger.warning("Битый JSON для участка %s: %s", segment.id, e)
            return TrafficMeasurement(
                timestamp=now_almaty_iso(),
                segment_id=segment.id,
                status=MeasurementStatus.FAIL,
                error_message=f"Битый JSON: {e}",
            )

        flow_data = data.get("flowSegmentData")
        if flow_data is None:
            return TrafficMeasurement(
                timestamp=now_almaty_iso(),
                segment_id=segment.id,
                status=MeasurementStatus.FAIL,
                error_message="Ответ не содержит flowSegmentData",
                raw_response=data,
            )

        return TrafficMeasurement(
            timestamp=now_almaty_iso(),
            segment_id=segment.id,
            current_speed_kmh=flow_data.get("currentSpeed"),
            free_flow_speed_kmh=flow_data.get("freeFlowSpeed"),
            current_travel_time_seconds=flow_data.get("currentTravelTime"),
            free_flow_travel_time_seconds=flow_data.get("freeFlowTravelTime"),
            confidence=flow_data.get("confidence"),
            road_closure=flow_data.get("roadClosure", False),
            frc=flow_data.get("frc"),
            status=MeasurementStatus.OK,
            raw_response=flow_data,
        )

    async def get_segments(self, segments: list[TrafficSegment]) -> list[TrafficMeasurement]:
        """Получить данные для списка участков (параллельно, с ограничением)."""
        tasks = [self._fetch_one(seg) for seg in segments]
        return list(await asyncio.gather(*tasks))


def _safe_error_text(resp: httpx.Response) -> str:
    """Извлечь текст ошибки из ответа, не ломаясь на битом JSON."""
    try:
        data = resp.json()
        detailed: dict[str, str] = data.get("detailedError", {})
        msg = detailed.get("message")
        return msg if msg else str(data)
    except Exception:
        return resp.text[:200]
