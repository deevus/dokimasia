# CLI Spy Scaffolding Design

Date: 2026-05-14
Status: approved design

## Goal

Add generic CLI spy scaffolding to Dokimasia so project suites can create PATH-shadowing wrappers that forward to real executables and record invocation events.

The implementation must remain domain-neutral. It must not know about tea, Forgejo, Gitea, issues, pull requests, milestones, or labels.

## Problem

The `tea-skills` E2E suite currently carries a mostly generic `tea_spy.py` helper. It creates an executable wrapper in a temporary `bin/` directory, prepends that directory to PATH, forwards argv to the real `tea` executable, and appends JSONL audit events.

Only three parts are tea-specific:

- wrapper executable name: `tea`;
- source label: `tea`;
- real executable discovery, which belongs to the consuming suite.

Dokimasia should own the reusable scaffolding. `tea-skills` should keep responsibility for choosing the executable, finding the real binary, and normalizing audit events.

## Architecture

Create a small scaffold module:

```text
src/dokimasia/scaffold/__init__.py
src/dokimasia/scaffold/cli_spy.py
tests/test_cli_spy.py
```

`dokimasia.scaffold.cli_spy` exposes:

```python
from dokimasia.scaffold.cli_spy import CliSpy, create_cli_spy
```

`create_cli_spy(...)` writes one executable Python wrapper under `<root>/bin/<executable_name>` and returns a `CliSpy` dataclass containing the generated paths and configuration.

`CliSpy.path_prefix` returns the spy `bin/` directory as a string. `CliSpy.env_with_path(base_env=None)` returns an environment dict with the spy `bin/` prepended to PATH.

## API

```python
spy = create_cli_spy(
    root=root / "spy",
    executable_name="tea",
    real_executable=Path(real_tea),
    audit_log=scenario_artifacts / "audit.jsonl",
    source="tea",
)

env = spy.env_with_path(os.environ)
```

Signature:

```python
def create_cli_spy(
    root: Path,
    executable_name: str,
    real_executable: Path,
    audit_log: Path,
    source: str,
    extra_event_fields: Mapping[str, object] | None = None,
) -> CliSpy:
    ...
```

`executable_name` must be a single file name, not a path. This prevents accidental wrapper creation outside the generated `bin/` directory.


`root`, `real_executable`, and `audit_log` are resolved to absolute paths at creation time so generated wrappers keep working when the agent invokes them from a different working directory. The generated wrapper also uses the current Python interpreter as an absolute shebang instead of `#!/usr/bin/env python3`, allowing spies for names such as `python3` without recursive PATH lookup.

## Event shape

The wrapper preserves the current compatible event shape:

```json
{
  "source": "tea",
  "argv": ["..."],
  "cwd": "...",
  "pid": 123,
  "phase": "finish",
  "exit_code": 0,
  "timestamp": "2026-05-14T00:00:00+00:00"
}
```

`extra_event_fields`, when provided, are merged into each event before writing. Core fields win over extra fields so callers cannot accidentally replace `argv`, `cwd`, `exit_code`, `phase`, `pid`, `source`, or `timestamp`.

## Data flow

1. The project suite discovers the real executable path.
2. The suite calls `create_cli_spy` with a temp root, wrapper name, real executable, audit log path, and source label.
3. The suite passes `spy.env_with_path(...)` into the agent runtime.
4. When the agent invokes the executable by name, PATH resolves to the wrapper.
5. The wrapper runs the real executable with the original argv.
6. The wrapper appends a JSONL event and exits with the real process exit code.

## Error handling

- `create_cli_spy` creates the wrapper directory and audit log parent directory.
- The generated wrapper creates the audit log parent directory again at runtime in case artifacts are cleaned or moved.
- The wrapper does not capture stdout or stderr. The real executable inherits stdio, preserving existing behavior.
- If the real executable exits non-zero, the spy still records the event and exits with the same code.
- Invalid `executable_name` values containing path separators or empty names raise `ValueError`.

## Testing

Add unit tests that exercise the generated wrapper as a real executable:

- wrapper file is executable;
- `path_prefix` points at the generated `bin/` directory;
- `env_with_path()` prepends the generated `bin/` directory;
- wrapper forwards argv and records `source`, `argv`, `cwd`, `phase`, and `exit_code`;
- wrapper records failed exits and returns the real exit code;
- invalid executable names are rejected.

- relative creation paths still work when the wrapper is invoked from another directory;
- spying an executable named `python3` does not recurse through the wrapper shebang.

## Non-goals

- Do not move `tea-skills` consumption in this change.
- Do not add stdout/stderr capture.
- Do not add a first-class `CliInvocationEvent` dataclass yet.
- Do not add any tea or Forgejo-specific normalization to Dokimasia.
