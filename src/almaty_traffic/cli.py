import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import httpx
import typer

from almaty_traffic.config_loader import load_segments, validate_config
from almaty_traffic.congestion import compute_congestion
from almaty_traffic.database import Database
from almaty_traffic.formatter import format_snapshot_json, format_snapshot_llm
from almaty_traffic.models import (
    CongestionLevel,
    CongestionResult,
    SnapshotSummary,
    TrafficMeasurement,
    TrafficSegment,
)
from almaty_traffic.scheduler import run_loop
from almaty_traffic.settings import ApiKeyFilter, Settings, load_settings
from almaty_traffic.tomtom_client import TomTomTrafficClient

app = typer.Typer(name="almaty-traffic", help="Сервис сбора и текстового описания пробок Алматы")

logger = logging.getLogger(__name__)


@app.command(name="validate-config")
def validate_config_cmd(
    config: Path | None = typer.Option(None, "--config", "-c", help="Путь к segments.yaml"),
) -> None:
    """Проверяет конфигурационный файл segments.yaml."""
    settings = load_settings()
    config_path = config or settings.segments_config
    success, errors = validate_config(config_path)
    if success:
        typer.echo(f"✓ Конфигурация валидна: {config_path}")
    else:
        typer.echo(f"✗ Ошибки в конфигурации ({config_path}):", err=True)
        for error in errors:
            typer.echo(f"  — {error}", err=True)
        raise typer.Exit(1)


@app.command()
def collect(
    config: Path | None = typer.Option(None, "--config", "-c"),
) -> None:
    """Один цикл сбора: конфиг → API → БД → snapshot."""
    settings = load_settings()
    config_path = config or settings.segments_config

    if not settings.tomtom_api_key:
        typer.echo("Ошибка: переменная окружения TOMTOM_API_KEY не задана.", err=True)
        raise typer.Exit(1)

    success, errors = validate_config(config_path)
    if not success:
        typer.echo(f"Ошибка конфигурации: {errors}", err=True)
        raise typer.Exit(1)

    config_data = load_segments(config_path)
    enabled = [s for s in config_data.segments if s.enabled]

    if not enabled:
        typer.echo("Нет активных участков.", err=True)
        raise typer.Exit(1)

    exit_code = asyncio.run(_collect_async(settings, enabled, config_path))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _collect_async(
    settings: Settings, segments: list[TrafficSegment], config_path: Path
) -> int:
    """Собрать данные. Возвращает 0 при успехе, 1 при полном провале."""
    db = Database(settings.database_path)
    await db.initialize()

    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as http:
        client = TomTomTrafficClient(
            http_client=http,
            api_key=settings.tomtom_api_key,
            timeout_seconds=settings.request_timeout_seconds,
        )
        results = await client.get_segments(segments)

    ok_count = sum(1 for r in results if r.status.value == "OK")
    fail_count = sum(1 for r in results if r.status.value != "OK")

    for m in results:
        await db.insert_measurement(m)

    # Fallback: free_flow_duration_seconds из конфига, если API вернул None
    ff_lookup: dict[str, int] = {}
    for seg in segments:
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
        total_segments=len(segments),
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

    typer.echo(f"Сбор завершён: {ok_count}/{len(segments)} участков успешно.")
    if fail_count:
        typer.echo(f"Ошибок: {fail_count}", err=True)

    typer.echo(text_str)

    return 1 if ok_count == 0 and fail_count > 0 else 0


@app.command()
def report(
    output_format: str = typer.Option("llm", "--format", "-f", help="Формат: llm, json, text"),
    only_congested: bool = typer.Option(False, "--only-congested", help="Только проблемные"),
) -> None:
    """Последняя сводка из БД."""
    settings = load_settings()
    db = Database(settings.database_path)

    async def _get() -> dict[str, str] | None:
        await db.initialize()
        return await db.get_latest_snapshot()

    snapshot = asyncio.run(_get())
    if not snapshot:
        typer.echo("Нет данных. Запустите collect для сбора данных.")
        return

    if output_format == "json":
        typer.echo(snapshot["json_payload"])
        return

    if only_congested:
        typer.echo(_render_llm_from_json(snapshot["json_payload"], only_congested=True))
        return

    typer.echo(snapshot["text_payload"])


def _render_llm_from_json(json_payload: str, only_congested: bool) -> str:
    """Восстановить CongestionResult/SnapshotSummary из сохранённого JSON-снимка."""
    data = json.loads(json_payload)
    results = [
        CongestionResult(
            segment_id=s["id"],
            current_speed_kmh=s["current_speed_kmh"],
            free_flow_speed_kmh=s["free_flow_speed_kmh"],
            current_travel_time_seconds=s["current_travel_time_seconds"],
            free_flow_travel_time_seconds=s["free_flow_travel_time_seconds"],
            confidence=s["confidence"],
            road_closure=s["road_closure"],
            congestion_ratio=s["congestion_ratio"],
            congestion_level=CongestionLevel(s["congestion_level"]),
        )
        for s in data["segments"]
    ]
    summary = SnapshotSummary(**data["summary"])
    timestamp = datetime.fromisoformat(data["timestamp"])
    return format_snapshot_llm(results, summary, only_congested=only_congested, timestamp=timestamp)


@app.command()
def history(
    segment_id: str = typer.Argument(help="ID участка"),
    hours: int = typer.Option(24, "--hours", "-h", help="Период в часах"),
) -> None:
    """История измерений участка."""
    settings = load_settings()
    db = Database(settings.database_path)

    async def _get() -> list[TrafficMeasurement]:
        await db.initialize()
        return await db.get_measurements(segment_id, hours)

    measurements = asyncio.run(_get())
    if not measurements:
        typer.echo(f"Нет данных для участка '{segment_id}' за последние {hours}ч.")
        return

    typer.echo(f"История участка '{segment_id}' за {hours}ч ({len(measurements)} записей):")
    for m in measurements:
        speed = f"{m.current_speed_kmh} км/ч" if m.current_speed_kmh is not None else "N/A"
        typer.echo(f"  {m.timestamp}  {speed}  {m.status.value}")


@app.command()
def run(
    interval: int = typer.Option(300, "--interval", "-i", help="Интервал сбора в секундах"),
) -> None:
    """Циклический сбор данных."""
    settings = load_settings()
    asyncio.run(run_loop(settings, interval))


@app.command()
def calibrate(
    days: int = typer.Option(14, "--days", "-d", help="Период анализа в днях"),
    write_config: bool = typer.Option(False, "--write-config", help="Записать в YAML"),
) -> None:
    """Калибровка базового времени по ночным измерениям."""
    settings = load_settings()
    from almaty_traffic.calibrate import apply_calibration, calibrate_free_flow

    results = asyncio.run(calibrate_free_flow(settings, days))
    if not results:
        typer.echo("Нет данных для калибровки.")
        return

    asyncio.run(apply_calibration(settings, results, write_config))


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", "-v", help="Показать версию"),
    log_level: str = typer.Option("INFO", "--log-level", help="Уровень логирования"),
) -> None:
    """Сервис сбора и текстового описания пробок Алматы."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    settings = load_settings()
    api_filter = ApiKeyFilter(settings.tomtom_api_key)
    logging.getLogger("httpx").addFilter(api_filter)
    logging.getLogger("httpcore").addFilter(api_filter)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if version:
        from almaty_traffic import __version__

        typer.echo(f"almaty-traffic {__version__}")
        raise typer.Exit()
