"""Tests for the optional matplotlib visualiser (skipped without matplotlib)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

import visualize  # noqa: E402
from healthagent import SimulationEngine  # noqa: E402


def _payload() -> dict:
    result = SimulationEngine(seed=1, offline=True).run_simulation(
        simulation_days=14, start_date=datetime(2026, 1, 5)
    )
    return result.to_dict()


def test_plot_trajectory_writes_a_png(tmp_path):
    payload = _payload()
    json_path = tmp_path / "trajectory_20260101_000000.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    chart = visualize.plot_trajectory(str(json_path), payload, payload["trajectory"])
    chart_path = Path(chart)
    assert chart_path.exists()
    assert chart_path.suffix == ".png"
    assert chart_path.stat().st_size > 10_000
    assert chart_path.name.startswith("trajectory_20260101_000000")


def test_find_latest_trajectory_returns_none_for_empty_dir(tmp_path):
    assert visualize.find_latest_trajectory(str(tmp_path)) is None


def test_find_latest_trajectory_picks_a_file(tmp_path):
    target = tmp_path / "trajectory_a.json"
    target.write_text("{}", encoding="utf-8")
    assert visualize.find_latest_trajectory(str(tmp_path)) == str(target)


def test_empty_trajectory_is_rejected(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"trajectory": []}', encoding="utf-8")
    with pytest.raises(ValueError):
        visualize.load_payload(str(path))
