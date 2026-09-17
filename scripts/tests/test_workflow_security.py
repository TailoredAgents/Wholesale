from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class WorkflowSecurityTests(unittest.TestCase):
    def test_authenticated_smoke_cannot_run_repository_code_from_manual_refs(self) -> None:
        workflow = (ROOT / ".github/workflows/authenticated-production-smoke.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("workflow_dispatch", workflow)
        self.assertIn("environment: production-smoke", workflow)
        self.assertIn("PRODUCTION_SMOKE_CLERK_SECRET_KEY", workflow)
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("issues: write", workflow)
        self.assertIn("stonegate-authenticated-production-smoke", workflow)

    def test_production_monitor_cannot_block_a_repair_deploy(self) -> None:
        workflow = (ROOT / ".github/workflows/production-readiness.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("issues: write", workflow)
        self.assertIn("stonegate-production-readiness-monitor", workflow)
        self.assertNotIn('exit 1', workflow)


if __name__ == "__main__":
    unittest.main()
