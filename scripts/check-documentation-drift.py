"""Fail fast when canonical Stonegate documentation drifts from durable repository facts."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


errors: list[str] = []


def require(relative_path: str, *markers: str) -> None:
    content = read(relative_path)
    for marker in markers:
        if marker not in content:
            errors.append(f"{relative_path}: missing required current marker {marker!r}")


def forbid(relative_path: str, *patterns: str) -> None:
    content = read(relative_path)
    for pattern in patterns:
        if re.search(pattern, content, flags=re.IGNORECASE):
            errors.append(f"{relative_path}: contains retired workflow pattern {pattern!r}")


# README must name the actual latest Alembic migration.
migration_dir = ROOT / "apps" / "api" / "alembic" / "versions"
migration_numbers = [
    int(match.group(1))
    for path in migration_dir.glob("*.py")
    if (match := re.match(r"(\d{4})_", path.name))
]
if not migration_numbers:
    errors.append("No numbered Alembic migrations were found.")
else:
    latest = max(migration_numbers)
    match = re.search(r"through migration (\d{4})", read("README.md"))
    if match is None or int(match.group(1)) != latest:
        documented = match.group(1) if match else "missing"
        errors.append(
            f"README.md: migration is {documented}; latest repository migration is {latest:04d}."
        )


require(
    "docs/STONEGATE_EMPLOYEE_GUIDE.md",
    "Active Buyer Prospects",
    "Buyer Network",
    "Past Buyers",
    "Investor disposition",
    "Not a lead",
    "Caroline",
)
require(
    "docs/LEAD_MANAGER_USER_MANUAL.md",
    "Leads > Today",
    "Working Conversations",
    "AI Suggestions",
    "No reminder",
)
require(
    "docs/UI_CONTROL_REFERENCE.md",
    "Active Buyer Prospects",
    "Not a lead",
    "Conversations",
)
require(
    "docs/SETUP_REFERENCE.md",
    "SELLER_CALLBACK_AGENT_PROVIDER=elevenlabs",
    "ELEVENLABS_WEBHOOK_SECRET",
    "ELEVENLABS_TOOL_SECRET",
    "Caroline AI Seller Callback Line",
    "Investor disposition",
)
forbid(
    "docs/LEAD_MANAGER_USER_MANUAL.md",
    r"Leads\s*>\s*Lead Queue",
    r"Working (The )?Inbox",
)


# Keep active callback and long-call variables represented in both the environment template and
# maintainer setup reference. Values are deliberately not checked because production secrets live
# outside the repository.
required_variables = (
    "SELLER_CALLBACK_AGENT_PROVIDER",
    "ELEVENLABS_AGENT_ENABLED",
    "ELEVENLABS_AGENT_ID",
    "ELEVENLABS_WEBHOOK_SECRET",
    "ELEVENLABS_TOOL_SECRET",
    "ELEVENLABS_LINE_NUMBER",
    "ELEVENLABS_TRANSFER_NUMBER",
    "ELEVENLABS_WEBHOOK_MAX_BYTES",
    "CALL_TRANSCRIPTION_MAX_AUDIO_BYTES",
)
for relative_path in (".env.example", "docs/SETUP_REFERENCE.md"):
    require(relative_path, *required_variables)


if errors:
    print("Documentation drift check failed:")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print(
    "Documentation drift check passed: migration, employee workflows, buyer routing, "
    "callback provider, and required environment references are current."
)
