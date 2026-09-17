from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "validate-render-blueprint.py"
SPEC = importlib.util.spec_from_file_location("validate_render_blueprint", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
validate_render_blueprint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_render_blueprint)


class RenderBlueprintGateTests(unittest.TestCase):
    def test_supported_auto_deploy_triggers_are_accepted(self) -> None:
        for trigger in ("checksPass", "commit", "off"):
            blueprint = {
                "services": [
                    {
                        "name": "stonegate-api",
                        "type": "web",
                        "runtime": "python",
                        "autoDeployTrigger": trigger,
                    }
                ]
            }
            self.assertEqual(validate_render_blueprint.validate_blueprint(blueprint), [])

    def test_unknown_auto_deploy_trigger_fails_closed(self) -> None:
        blueprint = {
            "services": [
                {
                    "name": "stonegate-api",
                    "type": "web",
                    "runtime": "python",
                    "autoDeployTrigger": "afterChecks",
                }
            ]
        }

        self.assertEqual(
            validate_render_blueprint.validate_blueprint(blueprint),
            [
                "<root>.services[0].autoDeployTrigger: unsupported value "
                "'afterChecks'"
            ],
        )


if __name__ == "__main__":
    unittest.main()
