# Dokimasia

Dokimasia is a pytest-first acceptance testing harness for agent capabilities.

Use it to prove that an agent can safely use an MCP server, CLI, skill, or workflow before you roll that capability out to developers or employees.

A passing Dokimasia test gives you three kinds of evidence:

1. **Capability evidence** — the agent discovered and used the intended capability, skill, MCP server, tool, or workflow.
2. **Audited operation evidence** — the external operation happened through an approved or audited path.
3. **Independent domain oracle** — the final business or system state was verified outside the agent's trace or claims.

Dokimasia is not a model benchmark. It is CI-style acceptance testing for agent capabilities that mutate real systems.

## Why Dokimasia?

Teams are giving agents access to MCP servers, internal CLIs, reusable skills, and workflow automations. Before broad rollout, they need evidence that agents use those capabilities correctly, safely, and observably.

A trace alone is not enough. A passing CLI or API integration test is not enough. A good final answer from the model is not enough. Dokimasia combines capability evidence, audited operations, and independent state verification in ordinary pytest suites.

## What Dokimasia is not

- Not a model benchmark for comparing model quality.
- Not just an observability or trace viewer.
- Not just a CLI/API integration test.
- Not a generic eval harness trying to grade every agent behavior.

Dokimasia tests whether an agent can use a specific capability safely and produce the expected external state.

## Good fit

Use Dokimasia when you need to test whether an agent can:

- use an internal MCP server before enabling it for employees;
- use a coding-agent skill before rolling it out to developers;
- create or modify records in systems such as GitHub, Jira, Linear, Slack, AWS, or ServiceNow;
- follow approved CLIs, tools, or workflows instead of ad hoc shell or API paths.

## Domain-neutral by design

Dokimasia provides generic mechanics: agent turns, artifacts, traces, command spies, layout helpers, environment helpers, and cleanup safety checks.

Your project provides provisioning, audit normalization, state verification, and domain-specific fixtures. This keeps the core independent of GitHub, Forgejo, Jira, Slack, or any other product while letting each suite encode its own business oracle.

## Python usage

Author Dokimasia suites as ordinary pytest modules. Installing Dokimasia registers its pytest plugin, so test modules can request the `doki_factory` and `doki` fixtures directly. Use plain Python setup code, project-owned fixtures, pytest marks, and normal pytest assertions instead of loading declarative scenario files:

```python
from pathlib import Path

import pytest

from dokimasia.agents.pi import PiAdapter
from dokimasia.pytest import assert_invoked, cmd

ISSUE_CREATE = cmd.match("tea", pattern=[("issues", "issue"), "create"])


@pytest.mark.agent_e2e
def test_agent_creates_issue(doki_factory, prepared_repo):
    doki = doki_factory(
        agent=PiAdapter(skills_dir=Path("skills")),
        workspace=prepared_repo,
    )

    result = doki.run("Create the requested issue")

    assert result.ok, result.failure_summary
    assert result.has_skill_loaded("create-issue")
    assert_invoked(result, ISSUE_CREATE)
```

Project suites provide provisioning, audit normalization, independent state verification, and fixtures for their own domain objects.

For Pi skill tests, `skills_dir` points at the skills under test. Dokimasia passes that directory to Pi and uses reads of `SKILL.md` files under it as skill-loaded evidence for assertions such as `result.has_skill_loaded(...)`.

Configure named built-in agent CLI options at `doki_factory` creation time. `model` and `extra_args` work with `claude-code`:

```python
doki = doki_factory(
    agent="claude-code",
    model="claude-sonnet-4",
    extra_args=["--allowedTools", "Read"],
)
```

For Pi skill tests, configure Pi-specific CLI options on the explicit adapter:

```python
doki = doki_factory(
    agent=PiAdapter(
        skills_dir=Path("skills"),
        provider="anthropic",
        model="claude-sonnet-4",
        thinking="high",
        extra_args=["--models", "claude-*"],
    ),
)
```

The same options can be set with environment variables. `doki_factory(env={...})` overrides the pytest process environment, and explicit `doki_factory` or adapter arguments override both:

```bash
DOKIMASIA_MODEL=deepseek/deepseek-v4-flash uv run pytest
```

Supported variables are `DOKIMASIA_PROVIDER`, `DOKIMASIA_MODEL`, `DOKIMASIA_THINKING`, and `DOKIMASIA_EXTRA_ARGS`. `DOKIMASIA_EXTRA_ARGS` is shell-split, so quoted values are preserved.

For custom adapters, instantiate and configure the adapter directly, then pass it as `agent=`.

## Pytest invocation matchers

Use `dokimasia.pytest.cmd` to define static matchers for observed executable invocations. An invocation can be a PATH-spied host command such as `tea`, or a repo-relative action script such as `actions/issues/lock.py`. Matchers are safe to create at module import time:

```python
from dokimasia.pytest import assert_invoked, cmd

ISSUE_CREATE = cmd.match(
    "tea",
    pattern=[("issues", "issue", "i"), ("create", "c")],
)
LOCK_ACTION = cmd.match(
    "actions/issues/lock.py",
    pattern=["1", "spam"],
    mode="exact",
)

assert ISSUE_CREATE.matches({"executable": "tea", "argv": ["--repo", "org/repo", "issue", "create"]})
assert LOCK_ACTION.matches({"action": "actions/issues/lock.py", "argv": ["1", "spam"]})
```

`pattern=` accepts token groups; `patterns=` accepts explicit alternatives. Matching modes are `ordered` (default, gaps allowed), `contains` (unordered containment), `span` (contiguous span), `prefix`, and `exact`. Use `where=` for custom predicates and `label=` to override generated labels such as `tea.issues.create`.

Use `assert_invoked(result, matcher)` as the preferred general assertion against observed `result.commands` in pytest tests. By default it requires at least one successful matching invocation. Use keyword-only `times=`, `min=`, `max=`, and `exit="success" | "failure" | "any"` for count and exit-status constraints:

```python
assert_invoked(result, ISSUE_CREATE)
assert_invoked(result, LOCK_ACTION, times=1)
assert_invoked(result, LOCK_ACTION, max=0, exit="any")  # did not run
```

`assert_command_ran(result, matcher)` remains available for compatibility with suites that only assert command-shaped evidence. New suites should prefer `assert_invoked(...)` because PATH spies and file spies both produce normalized invocation evidence on `result.commands`.

Static spy specs declare wrappers for pytest suites that need audited host commands earlier in `PATH`:

```python
from dokimasia.pytest import cmd

TEA = cmd.spy("tea")
ISSUE_CREATE = TEA.match(pattern=[("issues", "issue", "i"), ("create", "c")])

def test_issue_flow(doki_factory):
    doki = doki_factory(spies=[TEA])
```

`doki_factory(spies=[...])` resolves the real executable before adding wrapper directories to `PATH`, materializes wrappers under the fixture artifact area, and only prepends the spy `bin` directory when spies are explicitly registered. `cmd.spy("name")` records audit events with `source="name"` by default; pass `source=` when the audit source should differ from the executable name.

Invocation evidence proves that an approved executable path was used. It is not a substitute for independent domain-state verification. A good end-to-end test still asserts the resulting issue, ticket, cloud resource, or other business state through an oracle outside the agent's trace and stdout.


## Agent tool-call assertions

Use generic tool-call evidence when an acceptance suite needs to prove that an
agent selected the intended agent-side tool. Dokimasia adapters expose these
calls as normalized `TraceEvent(kind="tool.call")` entries on
`result.trace_events`, and pytest helpers make the common assertions concise:

```python
from dokimasia.pytest import assert_tool_called, assert_tool_not_called, tool_calls

result = doki.run("Inspect checkout flow before editing")

assert_tool_called(result, tool="get_file_skeleton")
assert_tool_called(
    result,
    tool="get_function",
    where=lambda event: "finalizeCheckout" in event.raw.get("args", {}).get("function_names", []),
)
assert_tool_not_called(result, tool="read")
```

`tool_calls(result, tool=..., where=...)` returns the matching trace events
unchanged, so suites can inspect raw adapter arguments or write ordering checks.
The `raw` shape is adapter-specific; use it for suite-local checks rather than
portable Dokimasia contracts.
`assert_tool_called(...)` supports `times=`, `min=`, and `max=` count
constraints. `assert_tool_not_called(...)` is shorthand for requiring zero
matching calls.

Tool-call evidence proves agent tool selection. It is not a substitute for
command invocation evidence, MCP operation evidence, or independent domain-state
verification.

## MCP acceptance testing

Use normalized MCP evidence when an acceptance suite needs to prove that an agent
called the intended MCP server and tool. Dokimasia exposes adapter-independent
MCP calls on `result.mcp_calls` and assertion helpers such as
`assert_mcp_called(...)` and `assert_mcp_not_called(...)`.

See `docs/mcp-acceptance.md` for the full MCP acceptance testing workflow,
including Claude Code `mcp__server__tool` traces, Pi MCP extension support,
`nicobailon/pi-mcp-adapter` proxy and direct-tool modes, the optional role of MCP
proxies, `doki-ledger` oracle tests, and opt-in live-agent E2E configuration.

## File spies for action scripts

Use file spies when the executable under test is a repo-relative action script rather than a host command discovered through `PATH`. The suite replaces the action file in the disposable test workspace with a wrapper. The wrapper forwards to the real project-owned script, records a JSONL event through `DOKIMASIA_COMMAND_LOG`, and preserves the real script's exit code. Production action scripts do not import Dokimasia; only the test workspace wrapper depends on Dokimasia's generated instrumentation.

Python action example:

```python
from dokimasia.pytest import assert_invoked, cmd
from dokimasia.suite import create_file_spy

LOCK_ACTION = cmd.match("actions/issues/lock.py", pattern=["1", "spam"], mode="exact")


def test_agent_locks_issue(doki_factory, workspace_repo, real_repo):
    create_file_spy(
        wrapper_path=workspace_repo / "actions/issues/lock.py",
        real_executable=real_repo / "actions/issues/lock.py",
        invocation_name="actions/issues/lock.py",
        source="issue-action",
    )

    result = doki_factory(workspace=workspace_repo).run("Lock issue 1 as spam")

    assert result.ok, result.failure_summary
    assert_invoked(result, LOCK_ACTION)
```

Node action example:

```python
from dokimasia.pytest import assert_invoked, cmd
from dokimasia.suite import create_node_file_spy

LOCK_ACTION = cmd.match("actions/issues/lock.js", pattern=["1", "spam"], mode="exact")


def test_agent_locks_issue_with_node_action(doki_factory, workspace_repo, real_repo):
    create_node_file_spy(
        wrapper_path=workspace_repo / "actions/issues/lock.js",
        real_script=real_repo / "actions/issues/lock.js",
        invocation_name="actions/issues/lock.js",
        source="issue-action",
        node_runner="node",
    )

    result = doki_factory(workspace=workspace_repo).run("Lock issue 1 as spam")

    assert result.ok, result.failure_summary
    assert_invoked(result, LOCK_ACTION)
```

Shell action example:

```python
from dokimasia.pytest import assert_invoked, cmd
from dokimasia.suite import create_shell_file_spy

LOCK_ACTION = cmd.match("actions/issues/lock.sh", pattern=["1", "spam"], mode="exact")


def test_agent_locks_issue_with_shell_action(doki_factory, workspace_repo, real_repo):
    create_shell_file_spy(
        wrapper_path=workspace_repo / "actions/issues/lock.sh",
        real_script=real_repo / "actions/issues/lock.sh",
        invocation_name="actions/issues/lock.sh",
        source="issue-action",
        shell_runner="sh",
    )

    result = doki_factory(workspace=workspace_repo).run("Lock issue 1 as spam")

    assert result.ok, result.failure_summary
    assert_invoked(result, LOCK_ACTION)
```

The recorded event includes normalized fields such as `action`, `argv`, `cwd`, `pid`, `phase`, `source`, `exit_code`, and `timestamp`. `Doki.run(...)` loads those events into the returned result, so assertions use `assert_invoked(result, LOCK_ACTION)` directly rather than reading audit files in the test.

## Examples

`doki-ledger` is a local stateful MCP server example for acceptance suites that need a deterministic MCP mutation target. It exposes a `record_transaction` tool, persists ledger entries to a pytest-controlled JSON file, and provides Python oracle helpers such as `balance_cents()` and `read_entries()` so tests can verify final state without trusting an agent trace. See `examples/doki-ledger/README.md`.


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

## Development setup

```bash
uv sync
```

Run tests:

```bash
uv run pytest
```

Run package commands inside the uv-managed environment:

```bash
uv run python -c "import dokimasia; print(dokimasia.__name__)"
```
