from __future__ import annotations

import pytest

from dokimasia.suite.safety import assert_scoped_disposable_name


def test_accepts_name_with_required_prefix_and_run_id():
    assert_scoped_disposable_name("suite-run-abc123", required_prefix="suite-", run_id="abc123")


def test_rejects_name_missing_required_prefix():
    with pytest.raises(ValueError, match="production-abc123"):
        assert_scoped_disposable_name("production-abc123", required_prefix="suite-", run_id="abc123")


def test_rejects_name_missing_run_id():
    with pytest.raises(ValueError, match="suite-other"):
        assert_scoped_disposable_name("suite-other", required_prefix="suite-", run_id="abc123")


def test_rejects_empty_policy_values():
    with pytest.raises(ValueError, match="required_prefix"):
        assert_scoped_disposable_name("suite-abc123", required_prefix="", run_id="abc123")
    with pytest.raises(ValueError, match="run_id"):
        assert_scoped_disposable_name("suite-abc123", required_prefix="suite-", run_id="")
