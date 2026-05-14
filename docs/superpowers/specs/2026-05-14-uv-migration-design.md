# uv Migration Design

## Goal

Move Dokimasia's development workflow from direct `pip` commands to a uv-native workflow while keeping the existing Python packaging model simple and compatible.

## Current State

- The project already uses `pyproject.toml`.
- The build backend is setuptools.
- Runtime dependencies are declared in `[project].dependencies`.
- README currently documents editable install via `python -m pip install -e /Users/sh/Projects/dokimasia`.
- No lockfile is committed.

## Decision

Use uv for development environment management and dependency locking, but keep setuptools as the build backend.

This means:

- Keep `[build-system]` unchanged.
- Commit `uv.lock` for reproducible local development and test runs.
- Document setup with `uv sync`.
- Document execution with `uv run ...`.
- Do not migrate to hatchling, flit, poetry, or another backend as part of this change.

## User Workflow

Primary setup command:

```bash
uv sync
```

Primary test command:

```bash
uv run python -m unittest
```

Optional editable/package command if needed:

```bash
uv pip install -e .
```

## Scope

In scope:

- Generate and commit `uv.lock`.
- Update README development instructions.
- Verify tests through uv.

Out of scope:

- Replacing setuptools.
- Adding unrelated dev tools.
- Fixing the missing `dokimasia.cli` entrypoint.
- Changing package metadata beyond what uv requires.

## Testing

Run:

```bash
uv run python -m unittest
```

The migration is complete when the test suite passes under uv and README instructions reflect the new workflow.
