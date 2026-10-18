"""Repository hygiene / packaging contract tests."""

from __future__ import annotations

import re
from pathlib import Path

import healthagent

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> str:
    return (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_declared_version_matches_package_version():
    match = re.search(r'^version\s*=\s*"([^"]+)"', _pyproject(), re.MULTILINE)
    assert match, "pyproject.toml must declare a static version"
    assert match.group(1) == healthagent.__version__


def test_runtime_dependencies_cover_the_imports_we_use():
    declared = _pyproject()
    for package in ("openai", "python-dotenv", "pydantic", "fastapi", "uvicorn"):
        assert package in declared, f"{package} must be declared in pyproject.toml"


def test_every_declared_plan_resolves():
    from healthagent.models import available_plans, get_intervention_plan

    for name in available_plans():
        plan = get_intervention_plan(name)
        assert plan.intervention_type is not None


def test_gitignore_excludes_generated_artifacts():
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("artifacts/", "outputs/", ".env"):
        assert pattern in text


def test_no_author_local_absolute_paths_in_sources():
    forbidden = (
        "C:\\Users",
        "C:\\\\Users",
        "D:\\deer-flow",
        "D:\\\\deer-flow",
        "Administrator\\Desktop",
    )
    offenders = []
    source_dirs = [REPO_ROOT / "healthagent", REPO_ROOT / "api", REPO_ROOT / "examples"]
    source_dirs += [REPO_ROOT / "simulate.py", REPO_ROOT / "visualize.py"]
    for path in source_dirs:
        files = path.rglob("*.py") if path.is_dir() else [path]
        for file in files:
            content = file.read_text(encoding="utf-8")
            if any(marker in content for marker in forbidden):
                offenders.append(str(file))
    assert not offenders, f"machine-specific paths found in: {offenders}"


def test_readme_does_not_advertise_missing_files():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for referenced in ("simulate.py", "visualize.py", "pyproject.toml"):
        if referenced in readme:
            assert (REPO_ROOT / referenced).exists(), f"README references missing {referenced}"
