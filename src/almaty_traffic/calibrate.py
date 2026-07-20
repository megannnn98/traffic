import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

from almaty_traffic.database import Database
from almaty_traffic.settings import Settings

logger = logging.getLogger(__name__)

NIGHT_START_HOUR = 2
NIGHT_END_HOUR = 5
PERCENTILE = 20


async def calibrate_free_flow(
    settings: Settings,
    days: int = 14,
) -> dict[str, int]:
    """Рассчитать базовое время как перцентиль ночных измерений."""
    db = Database(settings.database_path)
    await db.initialize()

    config_path = settings.segments_config
    with config_path.open() as f:
        config = yaml.safe_load(f)

    tz = ZoneInfo(settings.timezone)
    results: dict[str, int] = {}

    for seg in config.get("segments", []):
        seg_id = seg["id"]
        measurements = await db.get_measurements(seg_id, hours=days * 24)

        night_durations = []
        for m in measurements:
            if m.duration_seconds is None:
                continue
            try:
                dt = datetime.fromisoformat(m.timestamp)
                local_dt = dt.astimezone(tz)
                if NIGHT_START_HOUR <= local_dt.hour < NIGHT_END_HOUR:
                    night_durations.append(m.duration_seconds)
            except (ValueError, TypeError):
                continue

        if night_durations:
            night_durations.sort()
            idx = int(len(night_durations) * PERCENTILE / 100)
            idx = min(idx, len(night_durations) - 1)
            results[seg_id] = night_durations[idx]
            logger.info(
                "Участок %s: базовое время %ds (ночных измерений: %d)",
                seg_id,
                results[seg_id],
                len(night_durations),
            )
        else:
            logger.warning("Участок %s: нет ночных измерений за %d дней", seg_id, days)
            if seg.get("free_flow_duration_seconds"):
                results[seg_id] = seg["free_flow_duration_seconds"]

    return results


async def apply_calibration(
    settings: Settings,
    results: dict[str, int],
    write_config: bool = False,
) -> None:
    """Применить результаты калибровки."""
    config_path = settings.segments_config

    if write_config:
        backup_path = config_path.with_suffix(".yaml.bak")
        import shutil

        shutil.copy2(config_path, backup_path)
        logger.info("Резервная копия: %s", backup_path)

        with config_path.open() as f:
            config = yaml.safe_load(f)

        for seg in config.get("segments", []):
            if seg["id"] in results:
                seg["free_flow_duration_seconds"] = results[seg["id"]]

        with config_path.open("w") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        logger.info("Конфиг обновлён: %s", config_path)

    for seg_id, duration in results.items():
        typer_echo(f"{seg_id}: {duration}s")


def typer_echo(msg: str) -> None:
    """Обёртка для вывода (избегает циклического импорта typer)."""
    import sys

    print(msg, file=sys.stdout)
