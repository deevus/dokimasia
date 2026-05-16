# Getting started

Install the project with its documentation dependencies from a checkout:

```bash
uv sync --extra docs
```

Build the documentation site:

```bash
uv run mkdocs build
```

Serve it locally:

```bash
uv run mkdocs serve
```

## Authoring an acceptance test

Dokimasia suites are ordinary pytest modules. Use plain Python setup code, project-owned fixtures, pytest marks, and normal pytest assertions.

```python
import pytest

from dokimasia.pytest import assert_command_ran, cmd

ISSUE_CREATE = cmd.match("tea", pattern=[("issues", "issue"), "create"])


@pytest.mark.agent_e2e
def test_agent_creates_issue(doki_factory, prepared_repo):
    doki = doki_factory(agent="pi", workspace=prepared_repo)

    result = doki.run("Create the requested issue")

    assert result.ok, result.failure_summary
    assert result.has_skill_loaded("create-issue")
    assert_command_ran(result, ISSUE_CREATE)
```

Project suites provide provisioning, audit normalization, independent state verification, and fixtures for their own domain objects.
