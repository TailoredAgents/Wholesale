#!/usr/bin/env python3
"""Run the full API mypy check and reject errors beyond a committed baseline."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ERROR_PATTERN = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+): error: (?P<message>.*?)(?:  \[(?P<code>[^\]]+)\])?$"
)
NOTE_PATTERN = re.compile(r"^.+?:\d+: note: .+$")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail when full API mypy output exceeds the accepted debt baseline."
    )
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Replace the baseline with the current full mypy result.",
    )
    return parser.parse_args()


def fingerprint(line: str) -> tuple[str, str, str] | None:
    match = ERROR_PATTERN.match(line.strip())
    if match is None:
        return None
    path = match.group("path").replace("\\", "/")
    return (path, match.group("code") or "uncoded", match.group("message"))


def parse_mypy_diagnostics(
    result: subprocess.CompletedProcess[str],
) -> tuple[Counter[tuple[str, str, str]], list[str]]:
    """Parse every expected diagnostic and retain anything mypy emitted unexpectedly."""
    parsed: Counter[tuple[str, str, str]] = Counter()
    unparsed: list[str] = []
    for stream_name, output in (("stdout", result.stdout), ("stderr", result.stderr)):
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            item = fingerprint(stripped)
            if item is not None:
                parsed[item] += 1
                continue
            if NOTE_PATTERN.match(stripped):
                continue
            unparsed.append(f"{stream_name}: {stripped}")
    return parsed, unparsed


def run_mypy(
) -> tuple[
    subprocess.CompletedProcess[str],
    Counter[tuple[str, str, str]],
    list[str],
]:
    command = [
        sys.executable,
        "-m",
        "mypy",
        "app",
        "tests",
        "--no-color-output",
        "--no-error-summary",
        "--show-error-codes",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    parsed, unparsed = parse_mypy_diagnostics(result)
    return result, parsed, unparsed


def baseline_differences(
    actual: Counter[tuple[str, str, str]],
    allowed: Counter[tuple[str, str, str]],
) -> tuple[Counter[tuple[str, str, str]], Counter[tuple[str, str, str]]]:
    """Return errors beyond the baseline and stale allowance still left in it."""
    return actual - allowed, allowed - actual


def baseline_payload(errors: Counter[tuple[str, str, str]]) -> dict[str, Any]:
    entries = [
        {"path": path, "code": code, "message": message, "count": count}
        for (path, code, message), count in sorted(errors.items())
    ]
    return {
        "schema_version": 1,
        "command": "mypy app tests",
        "policy": "Existing errors are debt; any error beyond these fingerprint counts fails CI.",
        "known_errors": entries,
    }


def load_baseline(path: Path) -> Counter[tuple[str, str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Mypy baseline does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Mypy baseline is not valid JSON: {path}: {exc}") from exc

    if payload.get("schema_version") != 1 or not isinstance(payload.get("known_errors"), list):
        raise SystemExit(f"Unsupported mypy baseline schema: {path}")

    errors: Counter[tuple[str, str, str]] = Counter()
    for entry in payload["known_errors"]:
        try:
            key = (str(entry["path"]), str(entry["code"]), str(entry["message"]))
            count = int(entry["count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit(f"Malformed mypy baseline entry in {path}: {entry!r}") from exc
        if count < 1:
            raise SystemExit(f"Mypy baseline counts must be positive: {entry!r}")
        errors[key] += count
    return errors


def format_fingerprint(item: tuple[str, str, str], count: int) -> str:
    path, code, message = item
    suffix = f" (x{count})" if count > 1 else ""
    return f"  {path}: error: {message} [{code}]{suffix}"


def main() -> int:
    args = parse_arguments()
    result, actual, unparsed = run_mypy()
    if result.returncode not in (0, 1):
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        print(f"mypy could not complete (exit {result.returncode}).", file=sys.stderr)
        return result.returncode
    if result.returncode == 1 and (not actual or unparsed):
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if unparsed:
            print("Unrecognized mypy output:", file=sys.stderr)
            for line in unparsed:
                print(f"  {line}", file=sys.stderr)
        print(
            "mypy reported failure, but its complete error output could not be safely "
            "compared with the baseline.",
            file=sys.stderr,
        )
        return 2
    if result.returncode == 0 and actual:
        print(
            "mypy returned success while emitting error diagnostics; refusing to trust the result.",
            file=sys.stderr,
        )
        return 2

    if args.write_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(
            json.dumps(baseline_payload(actual), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {sum(actual.values())} known mypy errors to {args.baseline}.")
        return 0

    allowed = load_baseline(args.baseline)
    unexpected, retired = baseline_differences(actual, allowed)

    print("Full mypy regression report")
    print(f"  current errors: {sum(actual.values())}")
    print(f"  accepted baseline: {sum(allowed.values())}")
    print(f"  retired baseline entries: {sum(retired.values())}")
    print(f"  new errors: {sum(unexpected.values())}")

    failed = False
    if unexpected:
        print("New mypy errors beyond the accepted baseline:", file=sys.stderr)
        for item, count in sorted(unexpected.items()):
            print(format_fingerprint(item, count), file=sys.stderr)
        print(
            "Fix the new errors. Update the baseline only as a separately reviewed debt decision.",
            file=sys.stderr,
        )
        failed = True

    if retired:
        print(
            "The committed baseline contains retired mypy errors or excess counts:",
            file=sys.stderr,
        )
        for item, count in sorted(retired.items()):
            print(format_fingerprint(item, count), file=sys.stderr)
        print(
            "Regenerate and review the baseline in the same cleanup change so retired "
            "allowances cannot hide a later regression.",
            file=sys.stderr,
        )
        failed = True
    if failed:
        return 1

    print("No mypy regressions beyond the committed baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
