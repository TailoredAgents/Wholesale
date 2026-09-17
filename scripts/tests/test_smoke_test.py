from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import unittest
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = Path("scripts/smoke-test.sh")
Response = tuple[int, str, str]


class RouteHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        routes: dict[str, Response] = self.server.routes  # type: ignore[attr-defined]
        status, content_type, body = routes.get(
            self.path,
            (404, "text/plain", "not found"),
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if 300 <= status < 400:
            self.send_header("Location", "/")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def serve(routes: dict[str, Response]) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), RouteHandler)
    server.routes = routes  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def bash_executable() -> str | None:
    candidate = shutil.which("bash")
    if candidate and not (os.name == "nt" and Path(candidate).name.lower() == "bash.exe"):
        return candidate
    if os.name == "nt":
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.exists():
            return str(git_bash)
    return candidate


class ProductionSmokeScriptTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.bash = bash_executable()
        if not self.bash:
            self.skipTest("bash is unavailable")
        self.api_routes: dict[str, Response] = {
            "/health": (200, "application/json", json.dumps({"status": "ok"}, indent=2)),
            "/ready": (200, "application/json", json.dumps({"status": "ready"}, indent=2)),
            "/health/operations": (
                200,
                "application/json",
                json.dumps({"status": "healthy", "worker": {"status": "healthy"}}, indent=2),
            ),
        }
        self.web_routes: dict[str, Response] = {
            "/health": (
                200,
                "application/json",
                json.dumps({"status": "ok", "service": "web"}, indent=2),
            ),
            "/": (200, "text/html", "<html>home</html>"),
            "/get-a-cash-offer": (200, "text/html", "<html>offer</html>"),
            "/privacy-policy": (200, "text/html", "<html>privacy</html>"),
            "/terms": (200, "text/html", "<html>terms</html>"),
        }

    def run_smoke(self) -> subprocess.CompletedProcess[str]:
        with ExitStack() as stack:
            api_url = stack.enter_context(serve(self.api_routes))
            web_url = stack.enter_context(serve(self.web_routes))
            env = {
                **os.environ,
                "API_BASE_URL": api_url,
                "WEB_BASE_URL": web_url,
            }
            return subprocess.run(
                [self.bash, str(SMOKE_SCRIPT)],
                cwd=REPOSITORY_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )

    def test_accepts_structurally_valid_pretty_printed_json(self) -> None:
        result = self.run_smoke()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Smoke tests passed", result.stdout)

    def test_rejects_redirect_instead_of_treating_it_as_success(self) -> None:
        self.web_routes["/privacy-policy"] = (302, "text/html", "redirect")

        result = self.run_smoke()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("returned HTTP 302", result.stderr)

    def test_rejects_nested_healthy_status_when_top_level_is_unhealthy(self) -> None:
        self.api_routes["/health/operations"] = (
            200,
            "application/json",
            json.dumps({"status": "unhealthy", "worker": {"status": "healthy"}}),
        )

        result = self.run_smoke()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("top-level status was 'unhealthy'", result.stderr)

    def test_rejects_non_json_web_health_response(self) -> None:
        self.web_routes["/health"] = (200, "text/html", "<html>not health json</html>")

        result = self.run_smoke()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not return valid JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
