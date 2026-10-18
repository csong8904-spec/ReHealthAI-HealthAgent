# Changelog

**English** | [简体中文](CHANGELOG.zh-CN.md)

All notable changes to this project are documented here.

## [0.2.0] - 2026-10-18

Complete internal rewrite. The domain idea is unchanged; the implementation,
the model semantics and the packaging are not.

### Fixed — blocking

* `healthagent.engine.simulation_engine` could not be imported: it referenced a
  `get_intervention_plan()` that did not exist. The plan registry now exists and
  returns a fresh instance per call.
* `examples/*.py` failed on `from healthagent import SimulationEngine`; the
  package now exports its public API.
* `requirements.txt` listed four unused packages (numpy, pandas, click, rich)
  and omitted two imported ones (`openai`, `python-dotenv`). Replaced by
  `pyproject.toml` with exactly the runtime dependencies.
* `simulate.py` crashed with `UnicodeEncodeError` on a default Chinese Windows
  console (GBK) because of emoji in `print`.
* `healthagent/run.py` and `api/routers/*` hard-coded an author-local Windows
  path; `patient_db/db.py` hard-coded another. All machine-specific paths are
  gone; the DB path is `REHEALTH_DB_PATH` with a `~/.rehealth` default.
* The FastAPI app could not be imported from the repository root
  (`from routers import ...`) and was undocumented. It is now `api.main:app`
  with `api/__init__.py` and documented startup.
* README advertised `visualize.py`, which did not exist. It exists, has a
  rendering test (skipped when matplotlib is absent) and is run in CI.

### Fixed — model / behaviour

* **Missing feedback edge**: adherence never influenced stress, so a high-stress
  patient deteriorated regardless of adherence. Compliance now relieves the
  stress target, scaled by plan effectiveness.
* **Chronic-stress double counting**: physiology applied the absolute stress
  level, penalising a patient whose baseline was already measured under that
  stress. Now only the *excess* over baseline is penalised, and all effect sizes
  are relative to the patient's own baseline.
* **Anchoring**: sleep quality and HRV multipliers are neutral at baseline
  behaviour, so zero adherence yields approximately zero change instead of a
  spurious gain.
* **Priority downgrade bug**:
  `priority = max(priority, "medium")` compares strings, and in Python
  `max("high", "medium") == "medium"`. Priorities are now an `IntEnum`; an
  urgent day can no longer be downgraded or swallowed by the cooldown.
* **Headline metrics** used the last day minus baseline (single-day noise). They
  now use a trailing 14-day mean (`metric_window_days`).
* **Nudge fatigue**: a hard cap of 8 nudges per rolling 30 days, plus
  non-repeating message selection.
* The LLM call budget is now actually wired: a run is capped at `horizon + 5`
  requests (`max_llm_calls` to override), including retries.
* LLM-assisted runs are now verified against the real DeepSeek API
  (`deepseek-chat`): 7 calls, ~15 s, ~3.1 k tokens. The model's `narrative` and
  `key_factor` are surfaced in `DailyState` instead of being thrown away.
* **Partial adherence is no longer scored as zero.** A live run returned
  `complied: false` together with `compliance_quality: "partial"` for every day
  ("completed the meditation, skipped the walk"); v0.2.0 turned that into 0 %
  adherence and zero physiological effect. `compliance_quality` is now the
  authoritative field: full = 1.0, partial = 0.6, none = 0.0, and a day counts
  as adherent when the score is above zero.
* `LLMClient.usage_summary()` reports cumulative prompt/completion/total tokens
  so a run's cost can be measured.
* `seed=None` no longer claims reproducibility: a run is reported as
  reproducible only when it is both seeded and offline.
* `--days` outside 1–730 now produces an argparse error instead of a traceback.
* `GET /api/patients/{id}/trend` returns 404 (not `200 {"error": ...}`) for an
  unknown patient; `POST /api/patients` also returns the `id` alias.
* Removed the last unused imports and the historical absolute-path strings from
  docstrings; a test now scans the source tree for machine-specific paths.

### Changed

* The four "agents" are documented as what they are: deterministic state
  machines, one of which can optionally call an LLM.
* An explicit offline mode (`--offline`, `REHEALTH_OFFLINE`) makes demos, tests
  and CI free, fast and reproducible.
* `SimulationResult` gained `mode`, `seed`, `reproducible`, `patient`,
  `intervention`, `baseline` and `to_dict()` with a documented schema.
* Adherence is reported as `compliance_rate` (any adherence day) plus
  `full_compliance_rate` (score 1.0) and `partial_compliance_rate` (score 0.6),
  so a report can distinguish "did it" from "did part of it".
* Patient model: added `gender`, `occupation`, `wearable`, `habit_strength`,
  `social_support`; validation of all numeric ranges; `stress_level` accepts
  case-insensitive strings.
* HTTP API: request validation (`days` 1–365, bounded clinical fields), optional
  `X-API-Key` gate, non-blocking handlers, CORS allow-list.
* Optional DeerFlow wrapper (`healthagent/run.py`) no longer has local paths and
  returns an explicit "not medical advice" disclaimer.

### Added

* `tests/` — 82 pytest tests, including the dose–response invariant.
* `.github/workflows/ci.yml` — Python 3.10/3.12 + offline CLI smoke test.
* `pyproject.toml`, `CHANGELOG.md`, `.env.example` covering every variable.
* Bilingual documentation: `README.md` (English) and `README.zh-CN.md`
  (简体中文), cross-linked at the top of each file.

### Removed

* `artifacts/` (out-of-scope binary assets), `test.py` (asserted nothing),
  `commit.sh`, `commit_msg.txt`, stale `requirements.txt` and
  `api/requirements.txt`.

## [0.1.0] - 2026-03-09

Initial public demo. Not runnable as documented.
