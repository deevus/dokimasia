from __future__ import annotations

import unittest

from dokimasia.pytest import cmd


ISSUE_CREATE = cmd.match(
    "tea",
    pattern=[("issues", "issue", "i"), ("create", "c")],
)


def invocation(executable: str, argv: list[str], **extra):
    return {"executable": executable, "argv": argv, **extra}


class CommandMatcherTests(unittest.TestCase):
    def test_matchers_are_static_import_time_objects_with_keyword_only_arguments_and_labels(self):
        self.assertEqual(ISSUE_CREATE.label, "tea.issues.create")
        self.assertTrue(ISSUE_CREATE.matches(invocation("tea", ["--repo", "org/repo", "i", "--title", "T", "c"])))

        custom = cmd.match("tea", pattern=["issues", "list"], label="issue listing")
        self.assertEqual(custom.label, "issue listing")

        with self.assertRaises(TypeError):
            cmd.match("tea", ["issues", "list"])

    def test_supported_modes_distinguish_ordered_contains_span_prefix_and_exact(self):
        ordered = cmd.match("git", pattern=["status", "--short"])
        self.assertTrue(ordered.matches(invocation("git", ["-C", "repo", "status", "--ignored", "--short"])))
        self.assertFalse(ordered.matches(invocation("git", ["--short", "status"])))

        contains = cmd.match("git", pattern=["status", "--short"], mode="contains")
        self.assertTrue(contains.matches(invocation("git", ["--short", "-C", "repo", "status"])))

        span = cmd.match("jj", pattern=["git", "push"], mode="span")
        self.assertTrue(span.matches(invocation("jj", ["--repo", ".", "git", "push", "--allow-new"])))
        self.assertFalse(span.matches(invocation("jj", ["git", "--quiet", "push"])))

        prefix = cmd.match("python3", pattern=["-m", "pip"], mode="prefix")
        self.assertTrue(prefix.matches(invocation("python3", ["-m", "pip", "install", "."])))
        self.assertFalse(prefix.matches(invocation("python3", ["-I", "-m", "pip"])))

        exact = cmd.match("gh", pattern=["issue", "create"], mode="exact")
        self.assertTrue(exact.matches(invocation("gh", ["issue", "create"])))
        self.assertFalse(exact.matches(invocation("gh", ["issue", "create", "--title", "T"])))

    def test_explicit_pattern_alternatives_and_custom_where_predicates(self):
        git_status = cmd.match("git", patterns=[["status"], ["st"]])
        self.assertTrue(git_status.matches(invocation("git", ["st"])))
        self.assertTrue(git_status.matches(invocation("git", ["status", "--short"])))

        porcelain_status = cmd.match(
            "git",
            pattern=["status"],
            where=lambda command: any(token.startswith("--porcelain") for token in command.argv),
        )
        self.assertTrue(porcelain_status.matches(invocation("git", ["status", "--porcelain=v2"])))
        self.assertFalse(porcelain_status.matches(invocation("git", ["status", "--short"])))

    def test_matchers_cover_common_command_styles_without_parsing_embedded_commands(self):
        examples = [
            (cmd.match("tea", pattern=[("issues", "issue", "i"), ("create", "c")]), invocation("tea", ["--repo", "org/repo", "issue", "--title", "T", "create"])),
            (cmd.match("git", pattern=["status"]), invocation("git", ["-C", "repo", "status", "--short"])),
            (cmd.match("jj", pattern=["git", "push"], mode="span"), invocation("jj", ["--repo", ".", "git", "push", "--allow-new"])),
            (cmd.match("gh", pattern=["issue", "create"]), invocation("gh", ["issue", "--repo", "org/repo", "create"])),
            (cmd.match("xargs", pattern=["tea"]), invocation("xargs", ["-n1", "tea", "issue", "create"])),
            (cmd.match("ls"), invocation("ls", ["-la", "."])),
            (cmd.match("bootstrap-workspace", pattern=["--check"]), invocation("bootstrap-workspace", ["--check"])),
            (cmd.match("python3", pattern=["-m", "pip"], mode="prefix"), invocation("python3", ["-m", "pip", "install", "."])),
        ]
        for matcher, observed in examples:
            with self.subTest(label=matcher.label):
                self.assertTrue(matcher.matches(observed))

        self.assertFalse(cmd.match("tea", pattern=["issue", "create"]).matches(invocation("xargs", ["tea", "issue", "create"])))
        self.assertFalse(cmd.match("pip", pattern=["install"]).matches(invocation("python3", ["-m", "pip", "install", "."])))

    def test_mapping_and_object_invocations_are_supported(self):
        class ObservedCommand:
            executable = "gh"
            argv = ["issue", "list"]

        self.assertTrue(cmd.match("gh", pattern=["issue", "list"]).matches(ObservedCommand()))
        self.assertTrue(cmd.match("tea", pattern=["issues"]).matches({"source": "tea", "argv": ["issues", "list"]}))


if __name__ == "__main__":
    unittest.main()
