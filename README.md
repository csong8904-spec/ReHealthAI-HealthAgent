# ReHealth HealthAgent

**English** | [简体中文](README.zh-CN.md)

A small, **deterministic** simulator of how adherence, emotion and physiology
interact over a behavioural health intervention.

It is built to answer one question honestly: *given a patient profile, a plan and
a plausible adherence model, what trajectory do we get — and why?*

> **Research and illustration only.** This is not a medical device, not a
> diagnostic tool, and not clinical advice. No output here should be used to
> make decisions about a real person.

---

## What changed in v0.2

v0.1 was a demo that could not run: the engine imported a function that did not
exist, every example failed on import, the dependency list omitted the packages
the code imported, one module hard-coded a local path, and the "seed" had no
effect because the only source of randomness was an LLM call. The headline demo
image showed a *fully documented* intervention making every biomarker worse.

v0.2 is a rewrite of the internals with the same domain idea:

| Area | v0.1 | v0.2 |
|---|---|---|
| Feedback loop | adherence never affects stress | adherence relieves stress → physiology → nudges → adherence |
| Stress penalty | absolute stress double-counted chronic state | **excess** stress above the patient's own baseline |
| Effect sizes | absolute constants (HRV −8 ms/day) | relative to each baseline, anchored so "no adherence = no change" |
| Adherence | 1 LLM call/day, no fallback, no timeout | optional; JSON mode, retries, budget, circuit breaker, deterministic fallback |
| Reproducibility | claimed, impossible | byte-identical offline runs for a given seed + start date |
| Nudge priority | `max("high", "medium") == "medium"` | `IntEnum`, urgent days bypass the cooldown |
| Metrics | last day minus baseline | trailing 14-day mean minus baseline |
| Entry points | 4 of 5 broken | every documented command runs in CI |
| Dependencies | 4 unused, 2 missing | exactly what the code imports |
| Tests | none (`test.py` asserted nothing) | pytest suite, CI on 3.10/3.12 |

See [CHANGELOG.md](CHANGELOG.md) for the migration notes.

---

## Demo

90-day offline run on the built-in high-stress persona, reproducible with:

```bash
python simulate.py --offline --plan sleep_optimization --days 90 \
                   --seed 42 --start-date 2026-01-05 --out outputs
python visualize.py
```

![simulation demo](docs/demo.png)

That run reports adherence 54.4 %, sleep **+0.26 h**, HRV **+1.96 ms**, resting
HR **−0.43 bpm**. The numbers are deliberately modest: at ~50 % adherence the
model predicts little change, and a sleep-focused plan beats the generic hybrid
plan for this persona (hybrid: +0.01 h sleep). If you want to see the model's
best case, raise motivation/habit strength in the patient dict — the test suite
asserts that more adherence must produce better outcomes.

---

## Quick start (no API key, ~1 second)

```bash
git clone https://github.com/csong8904-spec/ReHealthAI-HealthAgent.git
cd ReHealthAI-HealthAgent
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python simulate.py --offline --days 90 --seed 42
python visualize.py              # needs the "plot" extra, see below
pytest -q
```

`--offline` selects the deterministic rule-based adherence model. No network,
no key, no cost — this is the mode used by the demos, the tests and CI.

Charts need matplotlib: `pip install -e ".[plot]"` (or `pip install matplotlib`).

---

## Two adherence backends

The simulation is four small state machines. **Only one of them can call an
LLM**, and it is optional:

| Agent | Model | Calls an LLM? |
|---|---|---|
| `EmotionAgent` | stress / motivation / fatigue dynamics | no |
| `ComplianceAgent` | daily adherence decision | **optional** |
| `PhysiologyAgent` | HRV, resting HR, sleep | no |
| `InterventionAgent` | risk detection + nudge policy | no |

```text
        yesterday's adherence
                 │
                 ▼
   emotion ──► compliance ──► physiology ──► nudge policy
      ▲                                       │
      └────────────── record ◄────────────────┘
```

### LLM mode (opt-in)

```bash
export DEEPSEEK_API_KEY=sk-...
python simulate.py --days 30        # one API call per simulated day
```

* `temperature=0`, JSON response mode, retry with backoff, 30 s timeout.
* Hard call budget: `horizon + 5` requests per run (override with
  `SimulationEngine(max_llm_calls=...)`); the run fails over to the rule model
  after 3 consecutive failures, so one flaky request cannot destroy a 90-day
  run.
* **Latency and cost scale linearly with the horizon**: one sequential request
  per simulated day, no parallelism (day *n+1* depends on day *n*). Measured
  against `deepseek-chat`: ~2 s and ~440 tokens per day, so a 7-day run takes
  ~15 s / ~3.1 k tokens and a 90-day run ~3 min / ~40 k tokens. Use `--offline`
  for demos, tests and CI.
* LLM-backed runs are reported with `reproducible: false` — the API is not
  bit-for-bit reproducible. Offline runs are.

---

## Python API

```python
from healthagent import SimulationEngine

engine = SimulationEngine(seed=42, offline=True)
result = engine.run_simulation(
    patient={
        "age": 52,
        "bmi": 27.5,
        "sleep_avg_hours": 6.2,
        "stress_level": "high",   # low | medium | high
    },
    intervention_plan="hybrid",   # see engine.available_plans()
    simulation_days=90,
)

print(result.compliance_rate)         # any adherence day (full or partial)
print(result.full_compliance_rate)    # days scored 1.0
print(result.partial_compliance_rate) # days scored 0.6
print(result.sleep_improvement)       # hours, trailing 14 days vs baseline
print(result.hrv_change)              # ms, trailing 14 days vs baseline
print(result.summary())               # JSON-serialisable dict
print(result.to_dict()["meta"]["baseline"])
```

`compliance_rate` counts any day with adherence; the full/partial rates split it
by how much of the plan was completed (1.0 vs 0.6). `patient` may also be a
`PatientProfile`. `intervention_plan` may be a name (`sleep_optimization`,
`cardio_fitness`, `stress_management`, `nutrition_plan`, `hybrid`) or an
`InterventionPlan`.

### CLI

| Option | Default | Meaning |
|---|---|---|
| `--days N` | 90 | horizon, 1–730 |
| `--seed N` | 42 | RNG seed |
| `--plan NAME` | `hybrid` | built-in plan |
| `--offline` | off | force the rule backend (auto-off if no key) |
| `--start-date YYYY-MM-DD` | today | pin it to reproduce a run exactly |
| `--out DIR` | `outputs` | where JSON + text report go |
| `--json` | off | print the full result to stdout |

---

## HTTP API

```bash
pip install -e ".[dev]"
export REHEALTH_DB_PATH=~/.rehealth/patients.db   # optional
uvicorn api.main:app --reload                     # from the repo root
```

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | liveness (public) |
| `GET` | `/api/simulation/plans` | list plans |
| `POST` | `/api/simulation/run` | run a simulation (`days` 1–365) |
| `POST` | `/api/simulation/patient` | run + persist for a stored patient |
| `POST/GET` | `/api/patients` | create / list patients |
| `GET` | `/api/patients/{id}` | profile |
| `GET` | `/api/patients/{id}/trend` | derived 30-day trend |
| `GET` | `/api/patients/{id}/history` | stored simulation runs |
| `POST` | `/api/records` | add a daily self-report record |
| `GET` | `/api/records/{patient_id}` | last N records for a patient |

Environment: `REHEALTH_API_KEY` (when set, all `/api/*` routes require
`X-API-Key`), `REHEALTH_CORS_ORIGINS`, `REHEALTH_DB_PATH`.

The database is **unencrypted SQLite with no audit trail** — treat it as
synthetic/test data only.

---

## Model assumptions (read this before trusting a number)

* **Nothing is calibrated.** Every coefficient lives in
  [`healthagent/model_params.py`](healthagent/model_params.py) and is a plausible
  placeholder, not a fitted parameter. The rule-based adherence model happens to
  produce ~45–55 % adherence for the demo persona; that is an output of the
  coefficients, **not** a validation result.
* **Anchoring.** Effects are measured against each patient's own baseline:
  with zero adherence and stress at baseline, targets equal baselines. This is
  what stops the model from declaring a chronically stressed patient doomed.
* **Excess stress.** Physiology responds to `stress - stress_baseline`; the
  baseline sleep/HRV numbers were already measured under that chronic stress.
* **Closed loop.** Successful adherence lowers the stress target and improves
  sleep/HRV/resting HR, weighted by the plan's `average_effectiveness` and the
  realised `compliance_score`.
* **The "agents" are modules.** They are deterministic, independently testable
  state machines, not autonomous LLM agents. The word "agent" is kept for
  continuity with the domain language; the architecture section above is the
  accurate description.
* **Single patient, single intervention, no comorbidity, no treatment
  escalation, no dropout process.** HRV/resting HR dynamics are linear and
  mean-reverting.

---

## Reproducibility

Offline runs are byte-identical for the same `(seed, start_date, patient, plan,
params)`. The start date matters because weekday affects stress; pin it:

```bash
python simulate.py --offline --seed 42 --start-date 2026-01-05 --days 90
```

If `seed` is omitted (the API and library default), the run draws from system
entropy and reports `reproducible: false`; the CLI defaults to `--seed 42`.

The package derives one seed per agent with SHA-256 (Python's `hash()` is
salted per process, so it must not be used here). LLM runs set
`reproducible=False` in the result.

---

## Tests

```bash
pytest -q      # 82 tests, ~4 s, no network
```

The suite encodes the properties that matter, not just "it runs":

* the same seed produces an identical trajectory;
* **higher adherence produces strictly better outcomes** (dose–response);
* the high-stress demo persona does not collapse to a clamped floor;
* biomarkers stay inside plausible bounds;
* an urgent nudge is never downgraded or suppressed by the cooldown;
* the nudge cap holds over any rolling 30-day window;
* the LLM backend falls back and opens a circuit breaker on repeated failures;
* partial adherence from the LLM is scored 0.6, not 0;
* the CLI, the HTTP API and `to_dict()` keep their documented contracts;
* no machine-specific absolute path appears in the source tree.

CI (`.github/workflows/ci.yml`) runs the suite on Python 3.10 and 3.12, then
exercises the CLI, the visualiser, both examples and the API import — every
command documented above is executed on every push.

---

## Repository layout

```text
healthagent/
  model_params.py      all coefficients, documented, overridable
  llm.py               optional DeepSeek client (retry, JSON, budget)
  models/              patient, plan, trajectory data classes
  agents/              emotion, compliance, physiology, intervention, orchestrator
  engine/              public SimulationEngine
  patient_db/          SQLite persistence
  run.py               optional agent-framework tool wrapper
api/                   FastAPI app (patients, records, simulation)
tests/                 pytest suite
simulate.py            CLI
visualize.py           matplotlib charts from a result JSON
examples/              sleep and cardio walkthroughs
```

---

## Data and secrets

* Never commit patient data, datasets, business documents or credentials.
  `.gitignore` blocks `artifacts/`, `outputs/`, `*.db`, `*.pdf`, `*.pptx` and
  `.env`.
* `.env.example` lists the supported variables. Copy it to `.env` locally.
* The API has no authentication unless `REHEALTH_API_KEY` is set, and no rate
  limiting. Do not expose it publicly as-is.

---

## Contributing

Issues and pull requests are welcome. Please keep the bar the repo now sets:
a reproducible test for any behaviour change, and no new untested entry point.

```
git checkout -b fix/my-fix
pytest -q
git commit -m "fix: ..."
```

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## Disclaimer

This software produces **simulated** trajectories from hand-set assumptions. It
is not a medical device, it has not been validated against clinical outcomes,
and it must not be used for diagnosis, treatment selection, or any decision
about a real patient. Any claim about real-world effectiveness requires
prospective validation with appropriate ethics approval.
