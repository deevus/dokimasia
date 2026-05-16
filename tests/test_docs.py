from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MKDOCS = ROOT / "mkdocs.yml"
PYPROJECT = ROOT / "pyproject.toml"
WEB_DOCS = ROOT / "docs" / "web"


def test_readme_documents_suite_authoring_namespace_and_modules():
    text = README.read_text(encoding="utf-8")

    assert "dokimasia.suite" in text
    for module in [
        "dokimasia.suite.spy",
        "dokimasia.suite.layout",
        "dokimasia.suite.safety",
        "dokimasia.suite.env",
    ]:
        assert module in text


def test_readme_defines_generic_project_suite_boundary():
    text = README.read_text(encoding="utf-8")

    assert "generic suite assembly helpers" in text
    assert "Projects provide provisioning, audit normalization, and state verification" in text
    assert (
        "Project-specific resource names, executable choices, audit roots, and state assertions stay in the project suite"
        in text
    )


def test_readme_describes_pytest_first_authoring_surface():
    text = README.read_text(encoding="utf-8")

    assert "uv run pytest" in text
    assert "pytest marks" in text
    assert "plain Python setup" in text
    assert "normal pytest assertions" in text
    assert "project-owned fixtures" in text
    assert "ScenarioRunner" not in text
    assert "load_scenarios" not in text
    assert "tags" not in text
    assert "templating" not in text
    assert "state schemas" not in text


def test_mkdocs_site_uses_docs_web_directory():
    text = MKDOCS.read_text(encoding="utf-8")

    assert "docs_dir: docs/web" in text
    assert (WEB_DOCS / "index.md").is_file()
    assert (WEB_DOCS / "getting-started.md").is_file()
    assert (WEB_DOCS / "api.md").is_file()


def test_pyproject_declares_docs_extra_dependencies():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    docs_deps = data["project"]["optional-dependencies"]["docs"]
    assert any(dep.startswith("mkdocs-material") for dep in docs_deps)
    assert any(dep.startswith("mkdocstrings[python]") for dep in docs_deps)
