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

## Pytest command matchers

Use `dokimasia.pytest.cmd` to define static matchers for observed top-level executable invocations. Matchers are safe to create at module import time:

```python
from dokimasia.pytest import cmd

ISSUE_CREATE = cmd.match(
    "tea",
    pattern=[("issues", "issue", "i"), ("create", "c")],
)

assert ISSUE_CREATE.matches({"executable": "tea", "argv": ["--repo", "org/repo", "issue", "create"]})
```

`pattern=` accepts token groups; `patterns=` accepts explicit alternatives. Matching modes are `ordered` (default, gaps allowed), `contains` (unordered containment), `span` (contiguous span), `prefix`, and `exact`. Use `where=` for custom predicates and `label=` to override generated labels such as `tea.issues.create`.

Use `assert_command_ran(result, matcher)` to assert against observed `result.commands` in pytest tests. By default it requires at least one successful matching command. Use keyword-only `times=`, `min=`, `max=`, and `exit="success" | "failure" | "any"` for count and exit-status constraints:

```python
from dokimasia.pytest import assert_command_ran, cmd

ISSUE_CREATE = cmd.match("tea", pattern=[("issues", "issue"), "create"])

assert_command_ran(result, ISSUE_CREATE)
assert_command_ran(result, ISSUE_CREATE, times=1)
assert_command_ran(result, ISSUE_CREATE, max=0, exit="any")  # did not run
```

Static spy specs declare wrappers for pytest suites that need audited host commands:

```python
from dokimasia.pytest import cmd

TEA = cmd.spy("tea")
ISSUE_CREATE = TEA.match(pattern=[("issues", "issue", "i"), ("create", "c")])

def test_issue_flow(doki_factory):
    doki = doki_factory(spies=[TEA])
```

`doki_factory(spies=[...])` resolves the real executable before adding wrapper directories to `PATH`, materializes wrappers under the fixture artifact area, and only prepends the spy `bin` directory when spies are explicitly registered. `cmd.spy("name")` records audit events with `source="name"` by default; pass `source=` when the audit source should differ from the executable name.


## Suite authoring helpers

The `dokimasia.suite` namespace contains generic suite assembly helpers. These helpers cover common mechanics that many end-to-end suites need while staying independent of any product, service, CLI, issue tracker, or project workflow.

Available helper modules:

- `dokimasia.suite.layout` creates run ids and artifact directories.
- `dokimasia.suite.spy` creates audited command wrappers that can be prepended to `PATH`.
- `dokimasia.suite.safety` checks caller-supplied cleanup policies before deleting disposable resources.
- `dokimasia.suite.env` composes `PATH` values and discovers required host executables.

Projects provide provisioning, audit normalization, and state verification. Project-specific resource names, executable choices, audit roots, and state assertions stay in the project suite. Dokimasia only provides the generic helper boundary that suite authors compose around those project-specific functions.

A typical suite composes the helpers in this order:

```python
from pathlib import Path

from dokimasia.suite.env import env_with_path_prepend, require_executable
from dokimasia.suite.layout import create_run_id, prepare_run_root, prepare_scenario_dir
from dokimasia.suite.safety import assert_scoped_disposable_name
from dokimasia.suite.spy import create_spy

run_id = create_run_id()
run_root = prepare_run_root(Path(".e2e-artifacts"), run_id)
scenario_dir = prepare_scenario_dir(run_root / "artifacts", "Create record")

resource_name = f"suite-{run_id}"
assert_scoped_disposable_name(resource_name, required_prefix="suite-", run_id=run_id)

real_cli = require_executable("example-cli")
spy = create_spy(
    root=run_root / "spy",
    executable_name="example-cli",
    real_executable=real_cli,
    audit_log=scenario_dir / "audit.jsonl",
    source="example-cli",
)
env = env_with_path_prepend(spy.path_prefix)
```

The example uses placeholder names only. Real suites should keep domain-specific provisioning, command normalization, and state assertions outside Dokimasia.

## Suite layout helpers

Use layout helpers for domain-neutral run ids and artifact directories:

```python
from pathlib import Path

from dokimasia.suite.layout import create_run_id, prepare_run_root, prepare_scenario_dir

run_id = create_run_id()
run_root = prepare_run_root(Path(".e2e-artifacts"), run_id)
scenario_dir = prepare_scenario_dir(run_root / "artifacts", "Create record")
```

`prepare_run_root` creates `<base>/<run-id>`. `prepare_scenario_dir` creates a safe hyphenated directory name such as `Create-record`.


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
