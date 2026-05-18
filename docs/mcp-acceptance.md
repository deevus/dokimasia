# MCP acceptance testing

Dokimasia treats MCP use as acceptance-test evidence, not as a model score. A
passing MCP suite should show that the agent used the intended MCP capability,
that the operation is auditable, and that the expected business state changed.

## Evidence model

A strong Dokimasia MCP test combines three kinds of evidence:

1. **Capability evidence** (capability evidence) — the agent selected the intended
   MCP server and operation instead of answering from memory or editing files
   directly.
2. **Audited operation evidence** (audited operation evidence) — the MCP request
   and response are present in ordered runtime logs, a proxy audit log, or
   another trusted operation log.
3. **Independent domain oracle** (independent domain oracle) — the final state is
   verified outside the agent's answer and outside the normalized MCP trace.

Dokimasia normalizes adapter-specific MCP logs into `result.mcp_calls`. Each
normalized MCP evidence item is a `McpCall` with fields such as `server`, `tool`,
`mode`, `arguments`, `result`, `error`, `sequence`, `call_id`, and `raw`.
Assertion helpers query that normalized list, so most tests do not need to know
which agent produced the trace:

```python
from dokimasia.pytest import assert_mcp_called


def has_expected_amount(call):
    return call.arguments == {
        "account": "acceptance",
        "amount_cents": 1234,
        "memo": "opt-in ledger MCP E2E",
    }


assert_mcp_called(
    result,
    server="doki-ledger",
    tool="record_transaction",
    success=True,
    times=1,
    where=has_expected_amount,
)
```

`assert_mcp_called(...)` filters by server, tool, mode, success/failure status,
count constraints, and an optional predicate. `assert_mcp_not_called(...)` is
available for negative checks.

The default `mode` filter is `"call"`. Non-mutating MCP adapter operations such
as discovery, search, list, or describe can also be represented as normalized MCP
evidence with their own modes. Use `mode=None` when a test intentionally wants to
inspect every MCP operation regardless of mode.

## Claude Code MCP evidence

Claude Code exposes MCP tools as first-class tool-use names shaped like
`mcp__server__tool`. For example, a call to the `record_transaction` tool on the
`doki-ledger` server appears as:

```json
{
  "type": "tool_use",
  "id": "toolu_...",
  "name": "mcp__doki-ledger__record_transaction",
  "input": {"account": "acceptance", "amount_cents": 1234}
}
```

Claude Code later emits a `tool_result` paired by `tool_use_id`. Dokimasia's
Claude Code adapter uses that pairing to preserve `call_id`, decode arguments,
classify failures, and emit one normalized MCP call with `mode="call"`.

## Pi MCP evidence

Pi does not include MCP support out of the box. MCP support comes from Pi
extensions, so the Pi adapter keeps MCP normalization pluggable. The default
supported extension is `nicobailon/pi-mcp-adapter`.

`pi-mcp-adapter` has two useful shapes:

- **proxy mode** — the agent calls one proxy tool, usually named `mcp`, with
  fields such as `server`, `tool`, `args`, `connect`, `describe`, or `search`.
  The extension records details about the real MCP operation in the result.
- **direct-tool mode** — the extension exposes MCP tools directly to Pi. Tool
  names may include a server prefix, a short name, or no prefix depending on the
  extension configuration, so Dokimasia prefers explicit metadata from the
  extension result over guessing from the displayed tool name.

The Pi normalizer supports both proxy mode and direct-tool mode for
`nicobailon/pi-mcp-adapter`. It also preserves discovery/list/describe evidence,
keeps raw request/response payloads, decodes JSON-string arguments, classifies
adapter errors, and deduplicates repeated nested Pi result evidence with the same
call id.

Suites with a different Pi MCP extension can pass custom MCP normalizers to
`PiAdapter`:

```python
from dokimasia.agents.pi import PiAdapter

adapter = PiAdapter(
    skills_dir=skills_dir,
    mcp_normalizers=[custom_normalizer],
)
```

## When an MCP proxy is optional

An MCP proxy is useful when the agent runtime does not expose trustworthy ordered
request/response evidence, when a suite needs extra policy enforcement, or when a
server-side audit trail must be retained independently of agent artifacts.

A proxy is optional, not foundational, when the ordered agent logs already show
complete and trustworthy MCP request/response evidence. In that case Dokimasia can
normalize the runtime logs directly and the suite can assert against
`result.mcp_calls`.

Do not treat normalized MCP evidence as the business oracle. It proves what the
agent attempted through MCP. The final state should still be checked through a
separate domain-specific read path.

## Stateful example: doki-ledger

`doki-ledger` is the in-repo stateful MCP example server. It exposes a mutating
`record_transaction(account, amount_cents, memo?)` tool and persists entries to a
pytest-controlled JSON file. That makes it suitable for tracer-bullet acceptance
coverage without external services or cleanup.

A live-agent ledger MCP test uses two checks:

1. normalized MCP evidence proves the agent called
   `doki-ledger.record_transaction` with the expected decoded business
   arguments; and
2. an independent domain oracle reads `ledger.json` with
   `dokimasia.examples.doki_ledger.read_entries()` to prove exactly one expected
   transaction was persisted.

The same pattern applies to ledger-style or todo-style stateful example servers:
keep the MCP server local and deterministic, then verify final state through a
pytest-owned file or API that does not depend on the agent's final answer.

See also:

- `examples/doki-ledger/README.md`
- `tests/e2e/test_doki_ledger_mcp_live.py`
- `tests/e2e/README.md`

## Opt-in live-agent E2E tests

Live-agent MCP tests should be opt-in. Normal CI should remain deterministic and
should not require Claude Code credentials, a local Pi MCP extension, or any user
MCP configuration.

The in-repo live MCP E2E suite is skipped unless `DOKIMASIA_LIVE_MCP_E2E` is set
to a truthy value:

```bash
DOKIMASIA_LIVE_MCP_E2E=1 uv run pytest -m "agent_e2e and mcp_e2e" tests/e2e -rs
```

Choose live adapters with `DOKIMASIA_LIVE_MCP_AGENTS`:

```bash
DOKIMASIA_LIVE_MCP_E2E=1 DOKIMASIA_LIVE_MCP_AGENTS=claude uv run pytest tests/e2e -rs
DOKIMASIA_LIVE_MCP_E2E=1 DOKIMASIA_LIVE_MCP_AGENTS=pi uv run pytest tests/e2e -rs
DOKIMASIA_LIVE_MCP_E2E=1 DOKIMASIA_LIVE_MCP_AGENTS=all uv run pytest tests/e2e -rs
```

Artifacts are stored under `.e2e-artifacts/<run-id>/` by default. Override the
artifact base directory with `DOKIMASIA_LIVE_MCP_E2E_ARTIFACT_DIR`:

```bash
DOKIMASIA_LIVE_MCP_E2E=1 \
DOKIMASIA_LIVE_MCP_E2E_ARTIFACT_DIR=/tmp/dokimasia-ledger-mcp \
uv run pytest tests/e2e -rs
```

Each run root contains the disposable workspace, Dokimasia artifacts, generated
`mcp.json`, and the ledger oracle state file. Use
`DOKIMASIA_LIVE_MCP_TIMEOUT_SECONDS` to adjust the per-agent timeout.
