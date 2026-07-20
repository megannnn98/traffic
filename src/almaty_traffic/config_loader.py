from pathlib import Path

import yaml
from pydantic import ValidationError

from almaty_traffic.models import SegmentsConfig, TrafficSegment


def load_segments(path: Path) -> SegmentsConfig:
    """Загружает и валидирует segments.yaml."""
    with path.open() as f:
        data = yaml.safe_load(f)
    return SegmentsConfig.model_validate(data)


def validate_segments(segments: list[TrafficSegment]) -> list[str]:
    """Проверяет бизнес-правила сегментов. Возвращает список ошибок."""
    errors: list[str] = []
    seen_ids: set[str] = set()

    active_count = 0
    for seg in segments:
        if seg.id in seen_ids:
            errors.append(f"Дублирующийся ID: {seg.id}")
        seen_ids.add(seg.id)

        if seg.free_flow_duration_seconds is not None and seg.free_flow_duration_seconds <= 0:
            errors.append(
                f"Участок '{seg.id}': free_flow_duration_seconds должно быть положительным"
            )

        if seg.enabled:
            active_count += 1

    if active_count == 0:
        errors.append("Нет ни одного активного участка (enabled: true)")

    return errors


def validate_config(path: Path) -> tuple[bool, list[str]]:
    """Полная валидация конфигурационного файла. (успех, ошибки)."""
    if not path.exists():
        return False, [f"Файл не найден: {path}"]

    try:
        config = load_segments(path)
    except yaml.YAMLError as e:
        return False, [f"Ошибка парсинга YAML: {e}"]
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " → ".join(str(x) for x in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return False, errors

    errors = validate_segments(config.segments)
    return len(errors) == 0, errors
