from __future__ import annotations

import unittest

from dokimasia.suite.safety import assert_scoped_disposable_name


class SuiteSafetyTests(unittest.TestCase):
    def test_accepts_name_with_required_prefix_and_run_id(self):
        assert_scoped_disposable_name("suite-run-abc123", required_prefix="suite-", run_id="abc123")

    def test_rejects_name_missing_required_prefix(self):
        with self.assertRaisesRegex(ValueError, "production-abc123"):
            assert_scoped_disposable_name("production-abc123", required_prefix="suite-", run_id="abc123")

    def test_rejects_name_missing_run_id(self):
        with self.assertRaisesRegex(ValueError, "suite-other"):
            assert_scoped_disposable_name("suite-other", required_prefix="suite-", run_id="abc123")

    def test_rejects_empty_policy_values(self):
        with self.assertRaisesRegex(ValueError, "required_prefix"):
            assert_scoped_disposable_name("suite-abc123", required_prefix="", run_id="abc123")
        with self.assertRaisesRegex(ValueError, "run_id"):
            assert_scoped_disposable_name("suite-abc123", required_prefix="suite-", run_id="")


if __name__ == "__main__":
    unittest.main()
