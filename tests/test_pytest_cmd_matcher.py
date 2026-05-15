from __future__ import annotations

import pytest

from dokimasia.pytest import cmd


ISSUE_CREATE = cmd.match(
    "tea",
    pattern=[("issues", "issue", "i"), ("create", "c")],
)


def invocation(executable: str, argv: list[str], **extra):
    return {"executable": executable, "argv": argv, **extra}


def test_matchers_are_static_import_time_objects_with_keyword_only_arguments_and_labels():
    assert ISSUE_CREATE.label == "tea.issues.create"
    assert ISSUE_CREATE.matches(invocation("tea", ["--repo", "org/repo", "i", "--title", "T", "c"]))

    custom = cmd.match("tea", pattern=["issues", "list"], label="issue listing")
    assert custom.label == "issue listing"

    with pytest.raises(TypeError):
        cmd.match("tea", ["issues", "list"])


def test_supported_modes_distinguish_ordered_contains_span_prefix_and_exact():
    ordered = cmd.match("git", pattern=["status", "--short"])
    assert ordered.matches(invocation("git", ["-C", "repo", "status", "--ignored", "--short"]))
    assert not ordered.matches(invocation("git", ["--short", "status"]))

    contains = cmd.match("git", pattern=["status", "--short"], mode="contains")
    assert contains.matches(invocation("git", ["--short", "-C", "repo", "status"]))

    span = cmd.match("jj", pattern=["git", "push"], mode="span")
    assert span.matches(invocation("jj", ["--repo", ".", "git", "push", "--allow-new"]))
    assert not span.matches(invocation("jj", ["git", "--quiet", "push"]))

    prefix = cmd.match("python3", pattern=["-m", "pip"], mode="prefix")
    assert prefix.matches(invocation("python3", ["-m", "pip", "install", "."]))
    assert not prefix.matches(invocation("python3", ["-I", "-m", "pip"]))

    exact = cmd.match("gh", pattern=["issue", "create"], mode="exact")
    assert exact.matches(invocation("gh", ["issue", "create"]))
    assert not exact.matches(invocation("gh", ["issue", "create", "--title", "T"]))


def test_explicit_pattern_alternatives_and_custom_where_predicates():
    git_status = cmd.match("git", patterns=[["status"], ["st"]])
    assert git_status.matches(invocation("git", ["st"]))
    assert git_status.matches(invocation("git", ["status", "--short"]))

    porcelain_status = cmd.match(
        "git",
        pattern=["status"],
        where=lambda command: any(token.startswith("--porcelain") for token in command.argv),
    )
    assert porcelain_status.matches(invocation("git", ["status", "--porcelain=v2"]))
    assert not porcelain_status.matches(invocation("git", ["status", "--short"]))


def test_matchers_cover_common_command_styles_without_parsing_embedded_commands():
    examples = [
        (
            cmd.match("tea", pattern=[("issues", "issue", "i"), ("create", "c")]),
            invocation("tea", ["--repo", "org/repo", "issue", "--title", "T", "create"]),
        ),
        (
            cmd.match("git", pattern=["status"]),
            invocation("git", ["-C", "repo", "status", "--short"]),
        ),
        (
            cmd.match("jj", pattern=["git", "push"], mode="span"),
            invocation("jj", ["--repo", ".", "git", "push", "--allow-new"]),
        ),
        (
            cmd.match("gh", pattern=["issue", "create"]),
            invocation("gh", ["issue", "--repo", "org/repo", "create"]),
        ),
        (
            cmd.match("xargs", pattern=["tea"]),
            invocation("xargs", ["-n1", "tea", "issue", "create"]),
        ),
        (cmd.match("ls"), invocation("ls", ["-la", "."])),
        (
            cmd.match("bootstrap-workspace", pattern=["--check"]),
            invocation("bootstrap-workspace", ["--check"]),
        ),
        (
            cmd.match("python3", pattern=["-m", "pip"], mode="prefix"),
            invocation("python3", ["-m", "pip", "install", "."]),
        ),
    ]
    for matcher, observed in examples:
        assert matcher.matches(observed), matcher.label

    assert not cmd.match("tea", pattern=["issue", "create"]).matches(invocation("xargs", ["tea", "issue", "create"]))
    assert not cmd.match("pip", pattern=["install"]).matches(invocation("python3", ["-m", "pip", "install", "."]))


def test_mapping_and_object_invocations_are_supported():
    class ObservedCommand:
        executable = "gh"
        argv = ["issue", "list"]

    assert cmd.match("gh", pattern=["issue", "list"]).matches(ObservedCommand())
    assert cmd.match("tea", pattern=["issues"]).matches({"source": "tea", "argv": ["issues", "list"]})


def test_spy_specs_default_source_and_create_source_aligned_matchers():
    tea_spy = cmd.spy("tea")

    assert tea_spy.executable == "tea"
    assert tea_spy.source == "tea"
    assert tea_spy.match(pattern=["issues", "create"]).matches({"source": "tea", "argv": ["issues", "create"]})

    custom_source = cmd.spy("gh", source="github-cli")
    matcher = custom_source.match(pattern=["issue", "list"])

    assert custom_source.executable == "gh"
    assert custom_source.source == "github-cli"
    assert matcher.matches({"source": "github-cli", "argv": ["issue", "list"]})
    assert not matcher.matches(invocation("gh", ["issue", "list"]))
