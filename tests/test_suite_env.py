from __future__ import annotations

import os
from pathlib import Path

import pytest

from dokimasia.suite.env import env_with_path_prepend, path_with_prepend, require_executable


def test_path_with_prepend_preserves_existing_path():
    assert (
        path_with_prepend(Path("/suite/bin"), existing_path=f"/usr/bin{os.pathsep}/bin")
        == f"/suite/bin{os.pathsep}/usr/bin{os.pathsep}/bin"
    )


def test_path_with_prepend_handles_empty_path():
    assert path_with_prepend(Path("/suite/bin"), existing_path="") == "/suite/bin"


def test_env_with_path_prepend_handles_absent_path():
    env = env_with_path_prepend(Path("/suite/bin"), {"OTHER": "value"})
    assert env == {"OTHER": "value", "PATH": "/suite/bin"}


def test_require_executable_returns_found_executable(tmp_path):
    executable = tmp_path / "demo"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)

    assert require_executable("demo", search_path=str(tmp_path)) == executable


def test_require_executable_raises_clear_error_when_missing():
    with pytest.raises(FileNotFoundError, match="missing-cli"):
        require_executable("missing-cli", search_path="/definitely/not/a/path")
