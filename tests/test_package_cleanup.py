from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "dokimasia"


def test_yaml_and_json_scenario_loader_modules_are_removed():
    assert not (SRC_ROOT / "core" / "scenarios.py").exists()


def test_declarative_scenario_runner_is_not_public_package_surface():
    assert not (SRC_ROOT / "core" / "runner.py").exists()
    model_text = (SRC_ROOT / "core" / "model.py").read_text(encoding="utf-8")
    assert "class Scenario" not in model_text
    assert "class ScenarioResult" not in model_text
    assert "class RunContext" not in model_text


def test_yaml_shaped_audit_expectation_helpers_are_removed():
    assert not (SRC_ROOT / "audit" / "assertions.py").exists()


def test_pyyaml_is_not_a_package_dependency():
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8")

    assert "PyYAML" not in pyproject
    assert "pyyaml" not in lockfile.lower()
    assert "pytest" in pyproject


def test_internal_tests_are_pytest_native():
    forbidden = ["import " + "unittest", "unittest" + ".", "unittest" + ".main"]
    for test_file in (PROJECT_ROOT / "tests").glob("test_*.py"):
        text = test_file.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{test_file} still contains {token}"
