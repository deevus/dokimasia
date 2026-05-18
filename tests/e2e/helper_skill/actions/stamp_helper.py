from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

SOURCE = "helper-stamp-skill"
STAMP_VERSION = "helper-stamp-v1"
STATE_ENV_VAR = "DOKIMASIA_HELPER_SKILL_STATE"


def expected_state(run_id: str) -> dict[str, str]:
    stamp = hashlib.sha256(f"{STAMP_VERSION}:{run_id}".encode("utf-8")).hexdigest()
    return {"run_id": run_id, "source": SOURCE, "stamp": stamp}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a deterministic Dokimasia helper-skill stamp")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    state_value = os.environ.get(STATE_ENV_VAR)
    if not state_value:
        parser.error(f"{STATE_ENV_VAR} is required")

    state_path = Path(state_value)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(expected_state(args.run_id), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"stamped {args.run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
