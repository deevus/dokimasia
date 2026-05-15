from __future__ import annotations

import unittest
from pathlib import Path


README = Path(__file__).resolve().parents[1] / "README.md"


class DokimasiaDocumentationTests(unittest.TestCase):
    def test_readme_documents_suite_authoring_namespace_and_modules(self):
        text = README.read_text(encoding="utf-8")

        self.assertIn("dokimasia.suite", text)
        for module in [
            "dokimasia.suite.spy",
            "dokimasia.suite.layout",
            "dokimasia.suite.safety",
            "dokimasia.suite.env",
        ]:
            with self.subTest(module=module):
                self.assertIn(module, text)

    def test_readme_defines_generic_project_suite_boundary(self):
        text = README.read_text(encoding="utf-8")

        self.assertIn("generic suite assembly helpers", text)
        self.assertIn("Projects provide provisioning, audit normalization, and state verification", text)
        self.assertIn("Project-specific resource names, executable choices, audit roots, and state assertions stay in the project suite", text)


if __name__ == "__main__":
    unittest.main()
