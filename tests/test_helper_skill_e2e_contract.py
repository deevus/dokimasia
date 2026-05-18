from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_helper_skill_prompt_does_not_disclose_helper_contract():
    from tests.e2e import test_helper_skill_live

    prompt = test_helper_skill_live.helper_stamp_prompt("abc123")

    assert "abc123" in prompt
    for forbidden in [
        "stamp_helper.py",
        "DOKIMASIA_HELPER_SKILL_STATE",
        "helper-stamp-v1",
        "sha256",
        "checksum",
        "source",
        "JSON",
    ]:
        assert forbidden not in prompt


def test_helper_stamp_action_writes_expected_state(tmp_path):
    from tests.e2e import test_helper_skill_live

    state_path = tmp_path / "state.json"
    action = ROOT / "tests" / "e2e" / "helper_skill" / "actions" / "stamp_helper.py"

    completed = subprocess.run(
        [sys.executable, str(action), "--run-id", "abc123"],
        env={**os.environ, "DOKIMASIA_HELPER_SKILL_STATE": str(state_path)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "stamped abc123\n"
    assert json.loads(state_path.read_text(encoding="utf-8")) == test_helper_skill_live.expected_helper_state("abc123")
