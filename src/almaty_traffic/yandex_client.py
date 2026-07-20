import asyncio
import logging
import time
from typing import Any

import httpx

from almaty_traffic.models import MeasurementStatus, RouteMeasurement, TrafficSegment
from almaty_traffic.utils import now_almaty_iso

logger = logging.getLogger(__name__)

API_URL = "https://api.routing.yandex.net/v2/distancematrix"


class YandexDistanceMatrixClient:
    """Клиент Yandex Distance Matrix API (один запрос 1×1 на участок)."""

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

    async def _fetch_one(self, segment: TrafficSegment) -> RouteMeasurement:
        """Запрос времени движения для одного участка (матрица 1×1)."""
        origin = f"{segment.origin.latitude},{segment.origin.longitude}"
        dest = f"{segment.destination.latitude},{segment.destination.longitude}"
        now = int(time.time())

        params: dict[str, Any] = {
            "apikey": self._api_key,
            "origins": origin,
            "destinations": dest,
            "mode": "driving",
            "departure_time": now,
        }

        try:
            async with self._semaphore:
                resp = await self._http.get(API_URL, params=params, timeout=self._timeout)
        except httpx.TimeoutException as e:
            logger.warning("Таймаут запроса для участка %s", segment.id)
            return RouteMeasurement(
                timestamp=now_almaty_iso(),
                segment_id=segment.id,
                status=MeasurementStatus.FAIL,
                error_message=f"Таймаут: {e}",
            )
        except httpx.HTTPError as e:
            logger.warning("Сетевая ошибка для участка %s: %s", segment.id, e)
            return RouteMeasurement(
                timestamp=now_almaty_iso(),
                segment_id=segment.id,
                status=MeasurementStatus.FAIL,
                error_message=f"Сетевая ошибка: {e}",
            )

        if resp.status_code != 200:
            error_text = _safe_error_text(resp)
            logger.warning("HTTP %d для участка %s: %s", resp.status_code, segment.id, error_text)
            return RouteMeasurement(
                timestamp=now_almaty_iso(),
                segment_id=segment.id,
                status=MeasurementStatus.FAIL,
                error_message=f"HTTP {resp.status_code}: {error_text}",
            )

        try:
            data = resp.json()
        except Exception as e:
            logger.warning("Битый JSON для участка %s: %s", segment.id, e)
            return RouteMeasurement(
                timestamp=now_almaty_iso(),
                segment_id=segment.id,
                status=MeasurementStatus.FAIL,
                error_message=f"Битый JSON: {e}",
            )

        try:
            element = data["rows"][0]["elements"][0]
        except (KeyError, IndexError) as e:
            logger.warning("Неожиданная структура ответа для участка %s: %s", segment.id, e)
            return RouteMeasurement(
                timestamp=now_almaty_iso(),
                segment_id=segment.id,
                status=MeasurementStatus.FAIL,
                error_message=f"Неожиданная структура ответа: {e}",
                raw_response=data,
            )

        api_status = element.get("status", "FAIL")
        if api_status != "OK":
            return RouteMeasurement(
                timestamp=now_almaty_iso(),
                segment_id=segment.id,
                status=MeasurementStatus.FAIL,
                error_message=f"API status: {api_status}",
                raw_response=element,
            )

        return RouteMeasurement(
            timestamp=now_almaty_iso(),
            segment_id=segment.id,
            distance_meters=element["distance"]["value"],
            duration_seconds=element["duration"]["value"],
            status=MeasurementStatus.OK,
            raw_response=element,
        )

    async def get_routes(self, segments: list[TrafficSegment]) -> list[RouteMeasurement]:
        """Получить время движения для списка участков (параллельно, с ограничением)."""
        tasks = [self._fetch_one(seg) for seg in segments]
        return list(await asyncio.gather(*tasks))


def _safe_error_text(resp: httpx.Response) -> str:
    """Извлечь текст ошибки из ответа, не ломаясь на битом JSON."""
    try:
        data = resp.json()
        errors = data.get("errors", [])
        return "; ".join(errors) if errors else str(data)
    except Exception:
        return resp.text[:200]
