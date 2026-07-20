import asyncio
import contextlib
import logging
import signal

import httpx

from almaty_traffic.config_loader import load_segments
from almaty_traffic.congestion import compute_congestion
from almaty_traffic.database import Database
from almaty_traffic.formatter import format_snapshot_json, format_snapshot_llm
from almaty_traffic.models import SnapshotSummary
from almaty_traffic.settings import Settings
from almaty_traffic.tomtom_client import TomTomTrafficClient

logger = logging.getLogger(__name__)


def _handle_signal(sig: int, stop_event: asyncio.Event) -> None:
    logger.info("Получен сигнал %s, завершаю...", sig)
    stop_event.set()


async def run_loop(settings: Settings, interval: int) -> None:
    """Циклический сбор данных с интервалом."""
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal, sig, stop_event)

    logger.info("Запуск циклического сбора (интервал %dс)", interval)

    while not stop_event.is_set():
        try:
            await _collect_cycle(settings)
        except Exception:
            logger.exception("Ошибка цикла сбора")

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval)

    logger.info("Сбор завершён по сигналу.")


async def _collect_cycle(settings: Settings) -> None:
    """Один цикл сбора."""
    config_path = settings.segments_config
    if not config_path.exists():
        logger.error("Конфиг не найден: %s", config_path)
        return

    config_data = load_segments(config_path)
    enabled = [s for s in config_data.segments if s.enabled]
    if not enabled:
        logger.warning("Нет активных участков")
        return

    db = Database(settings.database_path)
    await db.initialize()

    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as http:
        client = TomTomTrafficClient(
            http_client=http,
            api_key=settings.tomtom_api_key,
            timeout_seconds=settings.request_timeout_seconds,
        )
        results = await client.get_segments(enabled)

    for m in results:
        await db.insert_measurement(m)

    ok_count = sum(1 for r in results if r.status.value == "OK")
    fail_count = len(results) - ok_count

    # Fallback: free_flow_duration_seconds из конфига, если API вернул None
    ff_lookup: dict[str, int] = {}
    for seg in enabled:
        if seg.free_flow_duration_seconds is not None:
            ff_lookup[seg.id] = seg.free_flow_duration_seconds

    congestions = []
    for m in results:
        if m.status.value == "OK":
            ff_time = m.free_flow_travel_time_seconds or ff_lookup.get(m.segment_id, 0)
            congestions.append(
                compute_congestion(
                    segment_id=m.segment_id,
                    current_travel_time=m.current_travel_time_seconds,
                    free_flow_travel_time=ff_time,
                    current_speed=m.current_speed_kmh,
                    free_flow_speed=m.free_flow_speed_kmh,
                    confidence=m.confidence,
                    road_closure=m.road_closure,
                )
            )

    summary = SnapshotSummary(
        total_segments=len(enabled),
        successful_segments=ok_count,
        failed_segments=fail_count,
        traffic_jam_segments=sum(
            1 for c in congestions if c.congestion_level.value == "traffic_jam"
        ),
        severe_traffic_jam_segments=sum(
            1 for c in congestions if c.congestion_level.value == "severe_traffic_jam"
        ),
    )

    json_str = format_snapshot_json(congestions, summary)
    text_str = format_snapshot_llm(congestions, summary)
    await db.insert_snapshot(json_str, text_str)

    logger.info("Цикл завершён: %d/%d участков OK", ok_count, len(enabled))
