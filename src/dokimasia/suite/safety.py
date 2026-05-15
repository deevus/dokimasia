from __future__ import annotations


def assert_scoped_disposable_name(name: str, *, required_prefix: str, run_id: str) -> None:
    if not required_prefix:
        raise ValueError("required_prefix must not be empty")
    if not run_id:
        raise ValueError("run_id must not be empty")
    if not name.startswith(required_prefix) or run_id not in name:
        raise ValueError(f"refusing to delete out-of-scope disposable resource: {name}")


__all__ = ["assert_scoped_disposable_name"]
