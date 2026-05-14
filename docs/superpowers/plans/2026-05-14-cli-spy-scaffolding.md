# CLI Spy Scaffolding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic Dokimasia CLI spy helper that creates PATH-shadowing wrappers and records JSONL invocation events.

**Architecture:** Add a focused `dokimasia.scaffold.cli_spy` module with a `CliSpy` dataclass and `create_cli_spy` factory. Keep the helper generic; consuming projects choose executable names, real paths, source labels, and audit normalization.

**Tech Stack:** Python 3.11+ stdlib, unittest, subprocess, pathlib, dataclasses.

---

## File map

- Create: `src/dokimasia/scaffold/__init__.py` — package marker and public re-export.
- Create: `src/dokimasia/scaffold/cli_spy.py` — generic spy dataclass, validation, wrapper generation.
- Create: `tests/test_cli_spy.py` — red/green coverage for wrapper behavior.
- Modify: `README.md` — document Python usage for the scaffold helper.

## Task 1: Add tests for CLI spy behavior

**Files:**
- Create: `tests/test_cli_spy.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cli_spy.py` with tests that import `create_cli_spy`, create a real Python executable, invoke the generated wrapper, and inspect JSONL output.

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
python -m unittest tests.test_cli_spy -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'dokimasia.scaffold'`.

## Task 2: Implement CLI spy module

**Files:**
- Create: `src/dokimasia/scaffold/__init__.py`
- Create: `src/dokimasia/scaffold/cli_spy.py`

- [ ] **Step 1: Add package re-export**

Create `src/dokimasia/scaffold/__init__.py` exporting `CliSpy` and `create_cli_spy`.

- [ ] **Step 2: Add minimal implementation**

Create `src/dokimasia/scaffold/cli_spy.py` with:

- `CliSpy` dataclass;
- `path_prefix` property;
- `env_with_path(base_env=None)` helper;
- `create_cli_spy(...)` factory;
- executable-name validation;
- generated wrapper that forwards argv and writes JSONL events.

- [ ] **Step 3: Run tests to verify green**

Run:

```bash
python -m unittest tests.test_cli_spy -v
python -m unittest discover -s tests -v
```

Expected: all tests pass.

## Task 3: Document usage

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add README usage snippet**

Add a short `CLI spy scaffolding` section showing `create_cli_spy(...)` and `spy.env_with_path(...)`.

- [ ] **Step 2: Run verification**

Run:

```bash
python -m unittest discover -s tests -v
```

Expected: all tests pass.

## Self-review

- Spec coverage: tests, API, event shape, env helper, validation, and README documentation are covered.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: the plan uses `CliSpy`, `create_cli_spy`, `path_prefix`, and `env_with_path` consistently with the design.
