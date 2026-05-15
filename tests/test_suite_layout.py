from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from dokimasia.suite.layout import create_run_id, prepare_run_root, prepare_scenario_dir


class SuiteLayoutTests(unittest.TestCase):
    def test_create_run_id_uses_unix_timestamp_seconds(self):
        now = datetime.fromtimestamp(1_778_804_624, tz=timezone.utc)

        self.assertEqual(create_run_id(now), "1778804624")

    def test_prepare_run_root_creates_base_run_id_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "artifacts"

            run_root = prepare_run_root(base, "run-123")

            self.assertEqual(run_root, base / "run-123")
            self.assertTrue(run_root.is_dir())

    def test_prepare_run_root_creates_run_id_when_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "artifacts"

            run_root = prepare_run_root(base)

            self.assertEqual(run_root.parent, base)
            self.assertRegex(run_root.name, r"^\d+$")
            self.assertTrue(run_root.is_dir())

    def test_prepare_scenario_dir_preserves_current_simple_space_hyphen_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "artifacts"

            scenario_dir = prepare_scenario_dir(parent, "Create issue")

            self.assertEqual(scenario_dir, parent / "Create-issue")
            self.assertTrue(scenario_dir.is_dir())

    def test_prepare_scenario_dir_uses_slug_for_unsafe_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "artifacts"

            scenario_dir = prepare_scenario_dir(parent, "../issue/create: happy path!")

            self.assertEqual(scenario_dir, parent / "issue-create-happy-path")
            self.assertTrue(scenario_dir.is_dir())

    def test_prepare_scenario_dir_uses_fallback_for_empty_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "artifacts"

            scenario_dir = prepare_scenario_dir(parent, "!!!")

            self.assertEqual(scenario_dir, parent / "scenario")
            self.assertTrue(scenario_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
