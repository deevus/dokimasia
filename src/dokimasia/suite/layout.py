from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from slugify import slugify


def create_run_id(now: datetime | None = None) -> str:
    timestamp = now if now is not None else datetime.now(timezone.utc)
    return str(int(timestamp.timestamp()))


def prepare_run_root(base: Path | str, run_id: str | None = None) -> Path:
    selected_run_id = run_id if run_id is not None else create_run_id()
    run_root = Path(base) / selected_run_id
    run_root.mkdir(parents=True, exist_ok=True)
    return run_root


def prepare_scenario_dir(parent: Path | str, scenario_name: str) -> Path:
    slug = slugify(scenario_name, separator="-", lowercase=False, allow_unicode=False)
    scenario_dir = Path(parent) / (slug or "scenario")
    scenario_dir.mkdir(parents=True, exist_ok=True)
    return scenario_dir


__all__ = ["create_run_id", "prepare_run_root", "prepare_scenario_dir"]
