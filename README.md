# Dokimasia

Dokimasia is a generic agent end-to-end harness. It runs single-turn agent scenarios, preserves artifacts, normalizes traces, and asserts that expected trace/audit/state evidence exists.

The package is intentionally domain-neutral. It does not know about any specific product, CLI, issue tracker, or skill repository. Projects provide provisioning, audit normalization, and state verification.

CLI name: `doki`.

## Development setup

```bash
uv sync
```

Run tests:

```bash
uv run python -m unittest
```

Run package commands inside the uv-managed environment:

```bash
uv run python -c "import dokimasia; print(dokimasia.__name__)"
```

## Python usage

```python
from dokimasia.core.runner import ScenarioRunner
from dokimasia.core.scenarios import load_scenarios
from dokimasia.agents.claude_code import ClaudeCodeAdapter
```

Project suites provide provisioning, audit normalization, and state verification.


## Suite command spy

Use `create_spy` when a suite needs to put an audited wrapper earlier in `PATH` while forwarding to the real executable:

```python
from pathlib import Path
import os

from dokimasia.suite.spy import create_spy

spy = create_spy(
    root=Path(".e2e-artifacts/run/spy"),
    executable_name="example-cli",
    real_executable=Path("/usr/local/bin/example-cli"),
    audit_log=Path(".e2e-artifacts/run/audit.jsonl"),
    source="example-cli",
)

env = spy.env_with_path(os.environ)
```

The wrapper records JSONL invocation events with `source`, `argv`, `cwd`, `pid`, `phase`, `exit_code`, and `timestamp`, then exits with the real executable's status.
