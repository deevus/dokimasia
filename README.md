# Dokimasia

Dokimasia is a generic agent end-to-end harness. It runs single-turn agent scenarios, preserves artifacts, normalizes traces, and asserts that expected trace/audit/state evidence exists.

The package is intentionally domain-neutral. It does not know about any specific product, CLI, issue tracker, or skill repository. Projects provide provisioning, audit normalization, and state verification.

CLI name: `doki`.

## Development install

```bash
python -m pip install -e /Users/sh/Projects/dokimasia
```

## Python usage

```python
from dokimasia.core.runner import ScenarioRunner
from dokimasia.core.scenarios import load_scenarios
from dokimasia.agents.claude_code import ClaudeCodeAdapter
```

Project suites provide provisioning, audit normalization, and state verification.
