#!/usr/bin/env python3
"""visualize.py - plot a ReHealth AI simulation trajectory.

Usage:
    python visualize.py [path/to/trajectory_YYYYmmdd_HHMMSS.json]

If no path is given, the newest ``outputs/trajectory_*.json`` file is used.
The chart is saved next to the input JSON as ``<same_name>_chart.png``.

matplotlib is an optional dependency (``pip install matplotlib`` or the
``plot`` extra). All labels are English to avoid missing CJK fonts.
"""

from __future__ import annotations

import glob
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(REPO_ROOT, "outputs")

INSTALL_HINT = (
    "matplotlib is required for visualization.\n"
    "Install it with:  python -m pip install matplotlib\n"
    "or install the optional extra:  pip install -e \".[plot]\""
)


def _load_pyplot():
    """Import matplotlib lazily so the other scripts do not need it."""
    try:
        import matplotlib
    except ImportError:
        print(INSTALL_HINT, file=sys.stderr)
        sys.exit(2)

    # Non-interactive backend: works on CI and headless machines.
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def find_latest_trajectory(output_dir: str = DEFAULT_OUTPUT_DIR):
    """Return the newest trajectory_*.json under output_dir, or None."""
    candidates = glob.glob(os.path.join(output_dir, "trajectory_*.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: (os.path.getmtime(path), path))


def _field(day: dict, key: str, default=None):
    value = day.get(key, default)
    return default if value is None else value


def _series(trajectory: list[dict], key: str) -> list[float]:
    values = []
    for day in trajectory:
        try:
            values.append(float(_field(day, key)))
        except (TypeError, ValueError):
            values.append(float("nan"))
    return values


def _baseline(meta: dict) -> dict:
    """Baseline values used for the dashed reference lines."""
    baseline = meta.get("baseline") or {}
    return {
        "sleep_hours": baseline.get("sleep_hours"),
        "hrv": baseline.get("hrv"),
        "resting_hr": baseline.get("resting_hr"),
    }


def _signed(value, decimals: int = 1) -> str:
    """Format a signed number without a misleading "-0.0" for tiny values."""
    number = float(value)
    if abs(number) < 0.5 * 10 ** (-decimals):
        number = 0.0
    return f"{number:+.{decimals}f}"


def _summary_title(summary: dict) -> str:
    parts = []
    rate = summary.get("compliance_rate")
    if rate is not None:
        parts.append(f"Compliance {float(rate):.1%}")
    avg_sleep = summary.get("average_sleep_hours")
    if avg_sleep is not None:
        parts.append(f"Avg sleep {float(avg_sleep):.1f} h")
    sleep_improvement = summary.get("sleep_improvement")
    if sleep_improvement is not None:
        parts.append(f"Sleep {_signed(sleep_improvement)} h")
    hrv_change = summary.get("hrv_change")
    if hrv_change is not None:
        parts.append(f"HRV {_signed(hrv_change)} ms")
    hr_change = summary.get("resting_hr_change")
    if hr_change is not None:
        parts.append(f"Resting HR {_signed(hr_change)} bpm")
    if not parts:
        return "ReHealth AI simulation"
    return "ReHealth AI simulation - " + " | ".join(parts)


def load_payload(path: str) -> tuple[dict, list[dict]]:
    # utf-8-sig tolerates a BOM that some editors/PowerShell add on Windows.
    with open(path, "r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("trajectory JSON must contain an object at the top level")
    trajectory = payload.get("trajectory") or []
    if not trajectory:
        raise ValueError("trajectory JSON contains no daily states")
    trajectory = sorted(trajectory, key=lambda day: day.get("day", 0))
    return payload, trajectory


def plot_trajectory(json_path: str, payload: dict, trajectory: list[dict]) -> str:
    plt = _load_pyplot()

    meta = payload.get("meta") or {}
    summary = payload.get("summary") or {}
    baseline = _baseline(meta)

    days = [_field(day, "day") for day in trajectory]
    sleep = _series(trajectory, "sleep_hours")
    hrv = _series(trajectory, "hrv")
    resting_hr = _series(trajectory, "resting_hr")
    compliance = [1.0 if _field(day, "compliance") else 0.0 for day in trajectory]
    reminders = [
        _field(day, "day") for day in trajectory if _field(day, "intervention_triggered")
    ]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(_summary_title(summary), fontsize=13, fontweight="bold")

    meta_bits = []
    if meta.get("mode"):
        meta_bits.append(f"mode={meta['mode']}")
    if meta.get("seed") is not None:
        meta_bits.append(f"seed={meta['seed']}")
    if meta.get("simulation_days") is not None:
        meta_bits.append(f"days={meta['simulation_days']}")
    if meta.get("start_date") and meta.get("end_date"):
        meta_bits.append(f"{meta['start_date']} -> {meta['end_date']}")
    if meta_bits:
        fig.text(0.5, 0.925, "  ".join(meta_bits), ha="center", fontsize=9, color="0.35")

    # 1. Sleep duration
    ax = axes[0][0]
    ax.plot(days, sleep, color="tab:blue", linewidth=1.6, label="Daily sleep")
    if baseline["sleep_hours"] is not None:
        ax.axhline(
            float(baseline["sleep_hours"]),
            color="0.45",
            linestyle="--",
            linewidth=1.1,
            label=f"Baseline {float(baseline['sleep_hours']):.1f} h",
        )
    ax.set_title("Sleep duration")
    ax.set_ylabel("Hours")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # 2. HRV
    ax = axes[0][1]
    ax.plot(days, hrv, color="tab:green", linewidth=1.6, label="Daily HRV")
    if baseline["hrv"] is not None:
        ax.axhline(
            float(baseline["hrv"]),
            color="0.45",
            linestyle="--",
            linewidth=1.1,
            label=f"Baseline {float(baseline['hrv']):.1f} ms",
        )
    ax.set_title("Heart rate variability (HRV)")
    ax.set_ylabel("ms")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # 3. Resting heart rate
    ax = axes[1][0]
    ax.plot(days, resting_hr, color="tab:red", linewidth=1.6, label="Resting HR")
    if baseline["resting_hr"] is not None:
        ax.axhline(
            float(baseline["resting_hr"]),
            color="0.45",
            linestyle="--",
            linewidth=1.1,
            label=f"Baseline {float(baseline['resting_hr']):.0f} bpm",
        )
    ax.set_title("Resting heart rate")
    ax.set_xlabel("Simulation day")
    ax.set_ylabel("bpm")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # 4. Daily compliance (0/1 bars) with reminder markers
    ax = axes[1][1]
    colors = ["tab:green" if value else "tab:red" for value in compliance]
    ax.bar(days, compliance, width=1.0, color=colors, alpha=0.85, label="Complied (1) / missed (0)")
    if reminders:
        ax.scatter(
            reminders,
            [1.08] * len(reminders),
            marker="v",
            s=22,
            color="tab:orange",
            label="Reminder sent",
            zorder=3,
        )
    rate = summary.get("compliance_rate")
    if rate is not None:
        ax.axhline(
            float(rate),
            color="tab:blue",
            linestyle="--",
            linewidth=1.1,
            label=f"Mean compliance {float(rate):.1%}",
        )
    ax.set_ylim(-0.08, 1.2)
    ax.set_yticks([0, 1])
    ax.set_title("Daily compliance and reminders")
    ax.set_xlabel("Simulation day")
    ax.set_ylabel("Compliance")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(alpha=0.3)

    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.91))
    chart_path = os.path.splitext(json_path)[0] + "_chart.png"
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return chart_path


def main(argv: list[str]) -> int:
    if len(argv) > 2:
        print(f"Usage: python {os.path.basename(argv[0])} [trajectory.json]", file=sys.stderr)
        return 2

    if len(argv) == 2:
        json_path = argv[1]
        if not os.path.isfile(json_path):
            print(f"error: file not found: {json_path}", file=sys.stderr)
            return 1
    else:
        json_path = find_latest_trajectory()
        if json_path is None:
            print(
                f"error: no trajectory_*.json found in {DEFAULT_OUTPUT_DIR}\n"
                "Run the simulator first:  python simulate.py --offline --out outputs",
                file=sys.stderr,
            )
            return 1

    try:
        payload, trajectory = load_payload(json_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: could not read {json_path}: {exc}", file=sys.stderr)
        return 1

    chart_path = plot_trajectory(json_path, payload, trajectory)
    print(f"Chart saved: {chart_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
