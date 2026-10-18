"""CLI end-to-end tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _env(tmp_path: Path) -> dict:
    env = dict(os.environ)
    env["REHEALTH_OFFLINE"] = "1"
    env["REHEALTH_DB_PATH"] = str(tmp_path / "cli.db")
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("DEEPSEEK_API_KEY", None)
    env.pop("REHEALTH_API_KEY", None)
    return env


def test_cli_runs_offline_and_writes_outputs(tmp_path):
    out_dir = tmp_path / "out"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "simulate.py"),
            "--offline",
            "--days",
            "5",
            "--seed",
            "3",
            "--out",
            str(out_dir),
        ],
        cwd=str(REPO_ROOT),
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Simulation complete" in proc.stdout
    assert "Research use only" in proc.stdout

    trajectories = list(out_dir.glob("trajectory_*.json"))
    assert trajectories, "CLI must write a trajectory JSON file"
    payload = json.loads(trajectories[0].read_text(encoding="utf-8"))
    assert payload["meta"]["simulation_days"] == 5
    assert payload["meta"]["mode"] == "offline"
    assert len(payload["trajectory"]) == 5
    assert payload["meta"]["seed"] == 3

    assert list(out_dir.glob("report_*.txt"))


def test_cli_is_reproducible_for_the_same_seed(tmp_path):
    counter = {"n": 0}

    def run_once() -> dict:
        counter["n"] += 1
        out_dir = tmp_path / f"run_{counter['n']}"
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "simulate.py"),
                "--offline",
                "--days",
                "7",
                "--seed",
                "11",
                "--start-date",
                "2026-01-05",
                "--out",
                str(out_dir),
                "--quiet",
            ],
            cwd=str(REPO_ROOT),
            env=_env(tmp_path),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(next(out_dir.glob("trajectory_*.json")).read_text(encoding="utf-8"))

    assert run_once()["trajectory"] == run_once()["trajectory"]


def test_cli_version():
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "simulate.py"), "--version"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    assert "healthagent 0.2.0" in proc.stdout


def test_cli_rejects_unknown_plan(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "simulate.py"), "--plan", "nope", "--quiet"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
