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

## Suite layout helpers

Use layout helpers for domain-neutral run ids and artifact directories:

```python
from pathlib import Path

from dokimasia.suite.layout import create_run_id, prepare_run_root, prepare_scenario_dir

run_id = create_run_id()
run_root = prepare_run_root(Path(".e2e-artifacts"), run_id)
scenario_dir = prepare_scenario_dir(run_root / "artifacts", "Create issue")
```

`prepare_run_root` creates `<base>/<run-id>`. `prepare_scenario_dir` creates a safe hyphenated directory name such as `Create-issue`.


## Suite safety helpers

Use safety helpers before destructive cleanup of disposable resources. The caller supplies the suite policy so Dokimasia stays domain-neutral:

```python
from dokimasia.suite.safety import assert_scoped_disposable_name

assert_scoped_disposable_name(
    "suite-abc123",
    required_prefix="suite-",
    run_id="abc123",
)
```

The helper raises `ValueError` when the name is missing the required prefix or run id, and the error includes the refused resource name.


## Suite environment helpers

Use environment helpers when a suite needs to compose PATH values or require a host executable:

```python
from dokimasia.suite.env import env_with_path_prepend, require_executable

real_cli = require_executable("example-cli")
env = env_with_path_prepend(".e2e-artifacts/run/spy/bin", {"PATH": "/usr/bin"})
```

`env_with_path_prepend` preserves existing `PATH` content and handles empty or absent values. `require_executable` raises `FileNotFoundError` with the missing executable name when lookup fails.

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
