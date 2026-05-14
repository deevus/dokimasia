import json
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


    def test_runner_uses_configured_audit_log_env_var(self):
        captured_env = {}

        class FakeAdapter:
            def run(self, prompt, workspace, artifact_dir, env, timeout_seconds):
                captured_env.update(env)
                stdout = artifact_dir / "stdout.txt"
                stderr = artifact_dir / "stderr.txt"
                stdout.write_text("", encoding="utf-8")
                stderr.write_text("", encoding="utf-8")
                Path(env["PROJECT_AUDIT_LOG"]).write_text(
                    json.dumps({"root": "cli.list", "argv": [], "cwd": str(workspace), "exit_code": 0, "mutates": False, "source": "cli"}) + "\n",
                    encoding="utf-8",
                )
                return AgentRunResult(0, stdout, stderr, None, [], 0.01, False)

        def normalizer(raw):
            return AuditEvent(raw["root"], raw["argv"], raw["cwd"], raw["exit_code"], raw["mutates"], raw["source"], raw)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = RunContext("abc123", "org", "repo", root / "workspace", root / "artifacts")
            ctx.workspace.mkdir()
            scenario = Scenario(name="audit env", prompt="Do it")
            result = ScenarioRunner(FakeAdapter(), normalizer, lambda expectations, ctx: [], audit_log_env_var="PROJECT_AUDIT_LOG").run(scenario, ctx, {})
            self.assertTrue(result.passed, result.message)
            self.assertIn("PROJECT_AUDIT_LOG", captured_env)
            self.assertNotIn("DOKIMASIA_AUDIT_LOG", captured_env)
            self.assertEqual([event.root for event in result.audit_events], ["cli.list"])


class DokimasiaAgentAdapterTests(unittest.TestCase):
    def test_claude_parser_extracts_plugin_qualified_skill_loaded(self):
        from dokimasia.agents.claude_code import parse_claude_stream_json

        events = parse_claude_stream_json(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Skill",
                                    "input": {"skill": "plugin:create-record"},
                                }
                            ]
                        },
                    }
                ),
            ]
        )
        self.assertIn("plugin:create-record", [event.name for event in events if event.kind == "skill.loaded"])

    def test_pi_parser_extracts_skill_loaded_from_current_skill_read(self):
        from dokimasia.agents.pi import parse_pi_json_events

        events = parse_pi_json_events(
            [
                json.dumps(
                    {
                        "type": "tool_execution_start",
                        "toolName": "read",
                        "args": {"path": "/repo/skills/create-record/SKILL.md"},
                    }
                ),
            ],
            skills_dir=Path("/repo/skills"),
        )
        self.assertEqual([event.name for event in events if event.kind == "skill.loaded"], ["create-record"])


class DokimasiaScenarioLoaderTests(unittest.TestCase):
    def test_load_yaml_scenarios_merges_defaults(self):
        from dokimasia.core.scenarios import load_scenarios

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            defaults = root / "defaults.yaml"
            scenarios = root / "scenarios.yaml"
            defaults.write_text(
                """
execution:
  timeout_seconds: 10
expect_audit:
  budgets:
    total_commands:
      max: 5
""",
                encoding="utf-8",
            )
            scenarios.write_text(
                """
scenarios:
  - name: one
    prompt: Run {{ run.id }}
    expect_trace:
      events: []
""",
                encoding="utf-8",
            )
            loaded = load_scenarios(scenarios, defaults)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].execution["timeout_seconds"], 10)
        self.assertEqual(loaded[0].expect_audit["budgets"]["total_commands"], {"max": 5})

    def test_load_json_scenarios_for_backwards_compatibility(self):
        from dokimasia.core.scenarios import load_scenarios

        with tempfile.TemporaryDirectory() as tmp:
            scenarios = Path(tmp) / "scenarios.json"
            scenarios.write_text(
                json.dumps(
                    {
                        "scenarios": [
                            {
                                "name": "json scenario",
                                "prompt": "Run it",
                                "tags": ["compat"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            loaded = load_scenarios(scenarios)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].name, "json scenario")
        self.assertEqual(loaded[0].tags, ["compat"])


if __name__ == "__main__":
    unittest.main()
