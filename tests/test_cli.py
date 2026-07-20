from pathlib import Path

import yaml
from typer.testing import CliRunner

from almaty_traffic.cli import app

runner = CliRunner()


def _write_segments(path: Path, segments: list[dict[str, object]]) -> None:
    path.write_text(yaml.dump({"segments": segments}, allow_unicode=True))


def _valid_segment(seg_id: str = "seg1") -> dict[str, object]:
    return {
        "id": seg_id,
        "road": "проспект",
        "direction": "восток",
        "from_name": "А",
        "to_name": "Б",
        "origin": {"latitude": 43.0, "longitude": 76.0},
        "destination": {"latitude": 43.1, "longitude": 76.1},
        "free_flow_duration_seconds": 100,
        "enabled": True,
    }


def test_validate_config_valid(tmp_path: Path) -> None:
    cfg = tmp_path / "segments.yaml"
    _write_segments(cfg, [_valid_segment()])
    result = runner.invoke(app, ["validate-config", "--config", str(cfg)])
    assert result.exit_code == 0
    assert "валидна" in result.output


def test_validate_config_invalid(tmp_path: Path) -> None:
    cfg = tmp_path / "segments.yaml"
    _write_segments(cfg, [_valid_segment(), _valid_segment("seg1")])
    result = runner.invoke(app, ["validate-config", "--config", str(cfg)])
    assert result.exit_code == 1
    assert "Дублирующийся ID" in result.output


def test_validate_config_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate-config", "--config", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 1
