import asyncio
import logging
from pathlib import Path

import httpx
import typer

from almaty_traffic.config_loader import load_segments, validate_config
from almaty_traffic.congestion import compute_congestion
from almaty_traffic.database import Database
from almaty_traffic.formatter import format_snapshot_json, format_snapshot_llm
from almaty_traffic.models import RouteMeasurement, TrafficSegment
from almaty_traffic.scheduler import run_loop
from almaty_traffic.settings import ApiKeyFilter, Settings, load_settings
from almaty_traffic.yandex_client import YandexDistanceMatrixClient

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

    if not settings.yandex_api_key:
        typer.echo("Ошибка: YANDEX_API_KEY не задан.", err=True)
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
        client = YandexDistanceMatrixClient(
            http_client=http,
            api_key=settings.yandex_api_key,
            timeout_seconds=settings.request_timeout_seconds,
        )
        results = await client.get_routes(segments)

    ok_count = sum(1 for r in results if r.status.value == "OK")
    fail_count = sum(1 for r in results if r.status.value != "OK")

    for m in results:
        await db.insert_measurement(m)

    congestions = []
    for m in results:
        if m.status.value == "OK" and m.duration_seconds is not None:
            seg = next((s for s in segments if s.id == m.segment_id), None)
            ff = seg.free_flow_duration_seconds if seg and seg.free_flow_duration_seconds else 0
            congestions.append(compute_congestion(m.segment_id, m.duration_seconds, ff))

    from almaty_traffic.models import SnapshotSummary

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
    elif output_format == "llm":
        typer.echo(snapshot["text_payload"])
    else:
        typer.echo(snapshot["text_payload"])


@app.command()
def history(
    segment_id: str = typer.Argument(help="ID участка"),
    hours: int = typer.Option(24, "--hours", "-h", help="Период в часах"),
) -> None:
    """История измерений участка."""
    settings = load_settings()
    db = Database(settings.database_path)

    async def _get() -> list[RouteMeasurement]:
        await db.initialize()
        return await db.get_measurements(segment_id, hours)

    measurements = asyncio.run(_get())
    if not measurements:
        typer.echo(f"Нет данных для участка '{segment_id}' за последние {hours}ч.")
        return

    typer.echo(f"История участка '{segment_id}' за {hours}ч ({len(measurements)} записей):")
    for m in measurements:
        dur = f"{m.duration_seconds}с" if m.duration_seconds else "N/A"
        typer.echo(f"  {m.timestamp}  {dur}  {m.status.value}")


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
    api_filter = ApiKeyFilter(settings.yandex_api_key)
    logging.getLogger("httpx").addFilter(api_filter)
    logging.getLogger("httpcore").addFilter(api_filter)
    # Понижаем уровень httpx до WARNING, чтобы URL с API-ключом не попадал в логи
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if version:
        from almaty_traffic import __version__

        typer.echo(f"almaty-traffic {__version__}")
        raise typer.Exit()
