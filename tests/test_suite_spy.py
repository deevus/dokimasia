from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from dokimasia.suite.spy import CommandSpy, create_spy


class CommandSpyTests(unittest.TestCase):
    def _write_real_executable(self, root: Path, exit_code: int = 0) -> Path:
        real = root / "real_cli.py"
        real.write_text(
            f"""#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

Path(os.environ["REAL_CLI_RECORD"]).write_text(
    json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd()}}, sort_keys=True),
    encoding="utf-8",
)
raise SystemExit({exit_code})
""",
            encoding="utf-8",
        )
        real.chmod(0o755)
        return real

    def test_create_spy_creates_executable_wrapper_and_path_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record_path = root / "real-record.json"
            audit_log = root / "artifacts" / "audit.jsonl"
            real = self._write_real_executable(root)

            spy = create_spy(
                root=root / "spy",
                executable_name="demo",
                real_executable=real,
                audit_log=audit_log,
                source="demo-source",
            )
            self.assertIsInstance(spy, CommandSpy)

            wrapper = Path(spy.path_prefix) / "demo"
            self.assertTrue(wrapper.exists())
            self.assertTrue(os.access(wrapper, os.X_OK))

            env = spy.env_with_path({"PATH": "/usr/bin", "REAL_CLI_RECORD": str(record_path)})
            self.assertEqual(env["PATH"].split(os.pathsep)[0], spy.path_prefix)

            result = subprocess.run(
                ["demo", "alpha", "beta"],
                cwd=root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            expected_cwd = str(root.resolve())
            self.assertEqual(json.loads(record_path.read_text(encoding="utf-8")), {"argv": ["alpha", "beta"], "cwd": expected_cwd})

            events = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event["source"], "demo-source")
            self.assertEqual(event["argv"], ["alpha", "beta"])
            self.assertEqual(event["cwd"], expected_cwd)
            self.assertEqual(event["phase"], "finish")
            self.assertEqual(event["exit_code"], 0)
            self.assertIsInstance(event["pid"], int)
            self.assertIn("timestamp", event)

    def test_command_spy_records_nonzero_exit_and_preserves_core_fields_over_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record_path = root / "real-record.json"
            audit_log = root / "audit.jsonl"
            real = self._write_real_executable(root, exit_code=7)

            spy = create_spy(
                root=root / "spy",
                executable_name="demo",
                real_executable=real,
                audit_log=audit_log,
                source="demo-source",
                extra_event_fields={"suite": "unit", "exit_code": 999, "source": "wrong"},
            )

            env = spy.env_with_path(os.environ | {"REAL_CLI_RECORD": str(record_path)})
            result = subprocess.run(["demo", "fail"], cwd=root, env=env, check=False)

            self.assertEqual(result.returncode, 7)
            event = json.loads(audit_log.read_text(encoding="utf-8").strip())
            self.assertEqual(event["suite"], "unit")
            self.assertEqual(event["source"], "demo-source")
            self.assertEqual(event["exit_code"], 7)

    def test_command_spy_uses_absolute_paths_when_invoked_from_another_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            setup_dir = root / "setup"
            run_dir = root / "run"
            setup_dir.mkdir()
            run_dir.mkdir()
            record_path = root / "real-record.json"

            old_cwd = Path.cwd()
            try:
                os.chdir(setup_dir)
                real = self._write_real_executable(setup_dir)
                spy = create_spy(
                    root=Path("spy"),
                    executable_name="demo",
                    real_executable=Path("real_cli.py"),
                    audit_log=Path("audit/audit.jsonl"),
                    source="demo-source",
                )
            finally:
                os.chdir(old_cwd)

            env = spy.env_with_path(os.environ | {"REAL_CLI_RECORD": str(record_path)})
            result = subprocess.run(["demo", "from-other-cwd"], cwd=run_dir, env=env, check=False)

            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(record_path.read_text(encoding="utf-8"))["argv"], ["from-other-cwd"])
            self.assertTrue((setup_dir / "audit" / "audit.jsonl").exists())

    def test_command_spy_can_wrap_python3_without_shebang_recursion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_log = root / "audit.jsonl"
            spy = create_spy(
                root=root / "spy",
                executable_name="python3",
                real_executable=Path(sys.executable),
                audit_log=audit_log,
                source="python3",
            )

            result = subprocess.run(
                ["python3", "-c", "print('wrapped interpreter')"],
                env=spy.env_with_path(os.environ),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "wrapped interpreter")
            self.assertEqual(json.loads(audit_log.read_text(encoding="utf-8").strip())["argv"], ["-c", "print('wrapped interpreter')"])

    def test_create_spy_rejects_executable_names_that_are_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = self._write_real_executable(root)
            invalid_names = ["", ".", "..", "nested/demo", "nested\\demo", f"nested{os.pathsep}demo", "../demo"]
            for executable_name in invalid_names:
                with self.subTest(executable_name=executable_name):
                    with self.assertRaises(ValueError):
                        create_spy(
                            root=root / "spy",
                            executable_name=executable_name,
                            real_executable=real,
                            audit_log=root / "audit.jsonl",
                            source="demo-source",
                        )


    def test_old_scaffold_spy_namespace_is_removed(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("dokimasia.scaffold.cli_spy")


if __name__ == "__main__":
    unittest.main()
