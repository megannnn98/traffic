from pathlib import Path

import pytest
import yaml

from almaty_traffic.config_loader import load_segments, validate_config, validate_segments
from almaty_traffic.models import TrafficSegment


@pytest.fixture
def valid_segments_yaml(tmp_path: Path) -> Path:
    data = {
        "segments": [
            {
                "id": "seg1",
                "road": "проспект Абая",
                "direction": "восток",
                "from_name": "Назарбаева",
                "to_name": "Сейфуллина",
                "origin": {"latitude": 43.2381, "longitude": 76.9452},
                "destination": {"latitude": 43.2384, "longitude": 76.9281},
                "free_flow_duration_seconds": 240,
                "enabled": True,
            }
        ]
    }
    path = tmp_path / "segments.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True))
    return path


def test_load_segments_valid(valid_segments_yaml: Path) -> None:
    config = load_segments(valid_segments_yaml)
    assert len(config.segments) == 1
    assert config.segments[0].id == "seg1"


def test_validate_config_valid(valid_segments_yaml: Path) -> None:
    ok, errors = validate_config(valid_segments_yaml)
    assert ok is True
    assert errors == []


def test_validate_config_not_found(tmp_path: Path) -> None:
    ok, errors = validate_config(tmp_path / "missing.yaml")
    assert ok is False
    assert "не найден" in errors[0]


def test_validate_config_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("{{bad yaml: [")
    ok, errors = validate_config(path)
    assert ok is False
    assert "YAML" in errors[0] or "парсинга" in errors[0]


def test_validate_config_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("")
    ok, errors = validate_config(path)
    assert ok is False


def _make_segment(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "seg1",
        "road": "проспект",
        "direction": "восток",
        "from_name": "А",
        "to_name": "Б",
        "origin": {"latitude": 43.0, "longitude": 76.0},
        "destination": {"latitude": 43.1, "longitude": 76.1},
        "free_flow_duration_seconds": 100,
        "enabled": True,
    }
    base.update(overrides)
    return base


def test_validate_segments_duplicate_ids() -> None:
    data = {
        "segments": [
            _make_segment(id="dup"),
            _make_segment(id="dup"),
        ]
    }
    errors = validate_segments([TrafficSegment.model_validate(s) for s in data["segments"]])
    assert any("Дублирующийся ID" in e for e in errors)


def test_validate_segments_no_active() -> None:
    data = {
        "segments": [
            _make_segment(enabled=False),
        ]
    }
    errors = validate_segments([TrafficSegment.model_validate(s) for s in data["segments"]])
    assert any("активного участка" in e for e in errors)


def test_validate_config_bad_coordinates(tmp_path: Path) -> None:
    data = {
        "segments": [
            _make_segment(
                origin={"latitude": 999, "longitude": 76.0},
            )
        ]
    }
    path = tmp_path / "bad_coords.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True))
    ok, errors = validate_config(path)
    assert ok is False


def test_validate_config_negative_free_flow(tmp_path: Path) -> None:
    data = {
        "segments": [
            _make_segment(free_flow_duration_seconds=-10),
        ]
    }
    path = tmp_path / "neg.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True))
    ok, errors = validate_config(path)
    assert ok is False


def test_validate_config_zero_free_flow(tmp_path: Path) -> None:
    data = {
        "segments": [
            _make_segment(free_flow_duration_seconds=0),
        ]
    }
    path = tmp_path / "zero.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True))
    ok, errors = validate_config(path)
    assert ok is False
