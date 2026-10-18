#!/usr/bin/env python3
"""ReHealth HealthAgent - command line entry point.

Examples::

    python simulate.py                      # rule-based, 90 days, no API key needed
    python simulate.py --days 30 --seed 7
    python simulate.py --plan cardio_fitness --days 120 --offline
    python simulate.py                      # with DEEPSEEK_API_KEY -> LLM adherence

Output is ASCII-only on purpose: v0.1 crashed on a Chinese Windows console
(default GBK code page) because of emoji in ``print``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from healthagent import SimulationEngine, __version__, available_plans  # noqa: E402
from healthagent.llm import LLMClient  # noqa: E402
from healthagent.models.trajectory import DISCLAIMER  # noqa: E402


def _configure_stdio() -> None:
    """Never die on a non-UTF-8 console (e.g. GBK on Chinese Windows)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - platform dependent
            pass


def _days(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from None
    if not 1 <= parsed <= 730:
        raise argparse.ArgumentTypeError(f"days must be within [1, 730], got {parsed}")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simulate.py",
        description="Simulate a health intervention over time (research use only).",
    )
    parser.add_argument(
        "--days", type=_days, default=90, help="horizon in days, 1-730 (default: 90)"
    )
    parser.add_argument("--seed", type=int, default=42, help="random seed (default: 42)")
    parser.add_argument(
        "--plan",
        default="hybrid",
        choices=available_plans(),
        help="intervention plan (default: hybrid)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="force the deterministic rule-based adherence model (no network)",
    )
    parser.add_argument("--out", default="outputs", help="output directory (default: outputs)")
    parser.add_argument(
        "--start-date",
        default=None,
        help="first simulated day as YYYY-MM-DD (default: today); "
        "pin it to reproduce a run exactly",
    )
    parser.add_argument(
        "--json", action="store_true", help="also print the full JSON result to stdout"
    )
    parser.add_argument("--quiet", action="store_true", help="only print the summary")
    parser.add_argument("--version", action="version", version=f"healthagent {__version__}")
    return parser


def print_trajectory(result, every: int = 10) -> None:
    print(" Day | Adherence | Emotion     | Stress | Sleep h | HRV ms | HR bpm | Nudge")
    print("-" * 78)
    for state in result.trajectory:
        if state.day != 1 and state.day % every != 0:
            continue
        nudge = "*" if state.intervention_triggered else ""
        print(
            f"{state.day:4d} | "
            f"{'yes' if state.compliance else 'no ':>9} | "
            f"{state.emotion_state:<11} | "
            f"{state.stress_level:6.2f} | "
            f"{state.sleep_hours:7.1f} | "
            f"{state.hrv:6.1f} | "
            f"{state.resting_hr:6d} | {nudge}"
        )


def print_summary(result) -> None:
    summary = result.summary()
    print()
    print("=" * 66)
    print(f" Simulation complete - {result.simulation_days} days, mode={result.mode}")
    print("=" * 66)
    print(f" Adherence rate          : {summary['compliance_rate']:.1%}")
    print(f"   full / partial        : {summary['full_compliance_rate']:.1%} / "
          f"{summary['partial_compliance_rate']:.1%}")
    print(f" Average sleep           : {summary['average_sleep_hours']:.1f} h")
    print(f" Sleep change (vs base)  : {summary['sleep_improvement']:+.2f} h")
    print(f" HRV change (vs base)    : {summary['hrv_change']:+.2f} ms")
    print(f" Resting HR change       : {summary['resting_hr_change']:+.2f} bpm")
    print(f" Nudges sent             : {summary['intervention_count']}")
    print(f" Reproducible run        : {summary['reproducible']}")
    print(f" Metrics window          : last {result.metrics_window_days} days")
    print("=" * 66)
    print(f" NOTE: {DISCLAIMER}")
    print()


def save_result(result, out_dir: str) -> tuple[Path, Path]:
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = directory / f"trajectory_{stamp}.json"
    json_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    report = result.summary()
    report_path = directory / f"report_{stamp}.txt"
    lines = [
        "=" * 66,
        f" ReHealth HealthAgent v{__version__} - simulation report",
        "=" * 66,
        f" Mode                : {result.mode}",
        f" Seed                : {result.seed}",
        f" Horizon             : {result.simulation_days} days",
        f" Start date          : {result.start_date}",
        f" Adherence rate      : {report['compliance_rate']:.1%}",
        f" Average sleep       : {report['average_sleep_hours']:.2f} h",
        f" Sleep change        : {report['sleep_improvement']:+.2f} h",
        f" HRV change          : {report['hrv_change']:+.2f} ms",
        f" Resting HR change   : {report['resting_hr_change']:+.2f} bpm",
        f" Nudges sent         : {report['intervention_count']}",
        f" Reproducible        : {report['reproducible']}",
        "-" * 66,
        f" {DISCLAIMER}",
        "=" * 66,
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, report_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)

    offline = bool(args.offline) or os.getenv("REHEALTH_OFFLINE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    llm: Optional[LLMClient] = None
    if not offline:
        llm = LLMClient.from_env()
        if not llm.available:
            offline = True
            if not args.quiet:
                print("[info] DEEPSEEK_API_KEY not set - using the deterministic rule model.")
        elif not args.quiet:
            print(f"[info] {llm.describe()} - one API call per simulated day.")

    print(f"Plan: {args.plan} | horizon: {args.days} days | seed: {args.seed}")
    if not args.quiet:
        print(f"Mode: {'offline (deterministic)' if offline else 'llm-assisted'}")
        print()

    start_date = None
    if args.start_date:
        try:
            start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
        except ValueError:
            print(f"[error] --start-date must be YYYY-MM-DD, got {args.start_date!r}")
            return 2

    engine = SimulationEngine(seed=args.seed, offline=offline, llm=llm)
    result = engine.run_simulation(
        intervention_plan=args.plan, simulation_days=args.days, start_date=start_date
    )

    if not args.quiet:
        print_trajectory(result)
    print_summary(result)

    json_path, report_path = save_result(result, args.out)
    print(f"Saved JSON   : {json_path}")
    print(f"Saved report : {report_path}")

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
