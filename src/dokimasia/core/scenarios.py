from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml

from dokimasia.core.model import Scenario


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_document(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        loaded = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        loaded = yaml.safe_load(text)
    else:
        raise ValueError(f"unsupported scenario file extension: {path.suffix}")
    return loaded if isinstance(loaded, dict) else {}


def load_scenarios(path: Path, defaults_path: Path | None = None) -> list[Scenario]:
    defaults = load_document(defaults_path) if defaults_path else {}
    document = load_document(path)
    scenarios: list[Scenario] = []
    for item in document.get("scenarios", []):
        merged = deep_merge(defaults, item)
        scenarios.append(
            Scenario(
                name=merged["name"],
                prompt=merged["prompt"],
                tags=merged.get("tags", []),
                fixtures=merged.get("fixtures", {}),
                expect_trace=merged.get("expect_trace", {}),
                expect_audit=merged.get("expect_audit", {}),
                expect_state=merged.get("expect_state", []),
                outputs=merged.get("outputs", {}),
                execution=merged.get("execution", {}),
                depends_on=merged.get("depends_on", []),
            )
        )
    return scenarios
