from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from dokimasia.suite.env import env_with_path_prepend, path_with_prepend, require_executable


class SuiteEnvTests(unittest.TestCase):
    def test_path_with_prepend_preserves_existing_path(self):
        self.assertEqual(
            path_with_prepend(Path("/suite/bin"), existing_path=f"/usr/bin{os.pathsep}/bin"),
            f"/suite/bin{os.pathsep}/usr/bin{os.pathsep}/bin",
        )

    def test_path_with_prepend_handles_empty_path(self):
        self.assertEqual(path_with_prepend(Path("/suite/bin"), existing_path=""), "/suite/bin")

    def test_env_with_path_prepend_handles_absent_path(self):
        env = env_with_path_prepend(Path("/suite/bin"), {"OTHER": "value"})
        self.assertEqual(env, {"OTHER": "value", "PATH": "/suite/bin"})

    def test_require_executable_returns_found_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "demo"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)

            self.assertEqual(require_executable("demo", search_path=tmp), executable)

    def test_require_executable_raises_clear_error_when_missing(self):
        with self.assertRaisesRegex(FileNotFoundError, "missing-cli"):
            require_executable("missing-cli", search_path="/definitely/not/a/path")


if __name__ == "__main__":
    unittest.main()
