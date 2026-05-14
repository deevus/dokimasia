import tempfile
import unittest
from pathlib import Path

from dokimasia.audit.assertions import AuditAssertionError, assert_audit
from dokimasia.core.model import AgentRunResult, AuditEvent, RunContext, Scenario, TraceEvent
from dokimasia.core.runner import ScenarioRunner
from dokimasia.core.template import render_template


class DokimasiaCoreTests(unittest.TestCase):
    def test_render_template_replaces_dotted_values(self):
        self.assertEqual(
            render_template("{{ item.title }} / {{ run.id }}", {"item": {"title": "Hello"}, "run": {"id": "abc"}}),
            "Hello / abc",
        )

    def test_audit_expectations_ignore_failed_required_events(self):
        events = [AuditEvent("cli.create", [], "/repo", 1, True, "cli")]
        with self.assertRaisesRegex(AuditAssertionError, "cli.create"):
            assert_audit(events, {"events": [{"root": "cli.create", "min": 1}]})

    def test_runner_accepts_plugin_qualified_skill_names(self):
        class FakeAdapter:
            def run(self, prompt, workspace, artifact_dir, env, timeout_seconds):
                stdout = artifact_dir / "stdout.txt"
                stderr = artifact_dir / "stderr.txt"
                stdout.write_text("", encoding="utf-8")
                stderr.write_text("", encoding="utf-8")
                return AgentRunResult(
                    0,
                    stdout,
                    stderr,
                    None,
                    [TraceEvent(kind="skill.loaded", name="plugin:create-record")],
                    0.01,
                    False,
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = RunContext("run", "org", "repo", root / "workspace", root / "artifacts")
            ctx.workspace.mkdir()
            scenario = Scenario(
                name="qualified skill",
                prompt="Do it",
                expect_trace={"events": [{"kind": "skill.loaded", "name": "create-record"}]},
            )
            result = ScenarioRunner(FakeAdapter(), lambda raw: raw, lambda expectations, ctx: []).run(scenario, ctx, {})
            self.assertTrue(result.passed, result.message)

    def test_runner_renders_nested_state_expectations(self):
        class FakeAdapter:
            def run(self, prompt, workspace, artifact_dir, env, timeout_seconds):
                stdout = artifact_dir / "stdout.txt"
                stderr = artifact_dir / "stderr.txt"
                stdout.write_text("", encoding="utf-8")
                stderr.write_text("", encoding="utf-8")
                return AgentRunResult(0, stdout, stderr, None, [], 0.01, False)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = RunContext("abc123", "org", "repo", root / "workspace", root / "artifacts")
            ctx.workspace.mkdir()
            seen_expectations = []

            def verifier(expectations, context):
                seen_expectations.extend(expectations)
                return []

            scenario = Scenario(
                name="render state",
                prompt="Do it",
                expect_state=[{"match": {"title": "Run {{ run.id }}", "labels": ["{{ org }}"]}}],
            )
            result = ScenarioRunner(FakeAdapter(), lambda raw: raw, verifier).run(scenario, ctx, {})
            self.assertTrue(result.passed, result.message)
            self.assertEqual(seen_expectations, [{"match": {"title": "Run abc123", "labels": ["org"]}}])


if __name__ == "__main__":
    unittest.main()
