#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${API_BASE_URL:-}" || -z "${WEB_BASE_URL:-}" ]]; then
  echo "API_BASE_URL and WEB_BASE_URL are required." >&2
  exit 1
fi

api_base="${API_BASE_URL%/}"
web_base="${WEB_BASE_URL%/}"

if command -v python3 >/dev/null 2>&1; then
  python_command="python3"
elif command -v python >/dev/null 2>&1; then
  python_command="python"
else
  echo "python3 or python is required to validate smoke-test JSON." >&2
  exit 1
fi

smoke_tmp_dir="$(mktemp -d)"
trap 'rm -rf -- "$smoke_tmp_dir"' EXIT
request_count=0

request_200() {
  local label="$1"
  local url="$2"
  local output_file="$3"
  local status

  if ! status="$(
    curl --silent --show-error --max-time 20 \
      --output "$output_file" \
      --write-out '%{http_code}' \
      "$url"
  )"; then
    echo "$label request could not be completed: $url" >&2
    return 1
  fi

  # curl does not follow redirects here. Requiring exactly 200 prevents a redirect,
  # auth page, or other non-success response from becoming a green smoke result.
  if [[ "$status" != "200" ]]; then
    echo "$label returned HTTP $status: $(head -c 500 "$output_file")" >&2
    return 1
  fi
}

validate_json_status() {
  local label="$1"
  local output_file="$2"
  local expected_status="$3"
  local expected_service="${4:-}"

  "$python_command" - "$label" "$output_file" "$expected_status" "$expected_service" <<'PY'
import json
import sys
from pathlib import Path

label, payload_path, expected_status, expected_service = sys.argv[1:]
raw = Path(payload_path).read_text(encoding="utf-8", errors="replace")
try:
    payload = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit(f"{label} did not return valid JSON: {exc}: {raw[:500]}") from exc

if not isinstance(payload, dict):
    raise SystemExit(f"{label} returned a non-object JSON payload: {raw[:500]}")
if payload.get("status") != expected_status:
    raise SystemExit(
        f"{label} top-level status was {payload.get('status')!r}, "
        f"expected {expected_status!r}: {raw[:500]}"
    )
if expected_service and payload.get("service") != expected_service:
    raise SystemExit(
        f"{label} top-level service was {payload.get('service')!r}, "
        f"expected {expected_service!r}: {raw[:500]}"
    )
PY
}

check_json_endpoint() {
  local label="$1"
  local url="$2"
  local expected_status="$3"
  local expected_service="${4:-}"
  local output_file

  request_count=$((request_count + 1))
  output_file="$smoke_tmp_dir/response-$request_count.json"
  request_200 "$label" "$url" "$output_file"
  validate_json_status "$label" "$output_file" "$expected_status" "$expected_service"
}

check_page() {
  local path="$1"
  local output_file

  request_count=$((request_count + 1))
  output_file="$smoke_tmp_dir/response-$request_count.html"
  request_200 "Web page $path" "$web_base$path" "$output_file"
}

check_json_endpoint "API health" "$api_base/health" "ok"
check_json_endpoint "API readiness" "$api_base/ready" "ready"
check_json_endpoint "API operational health" "$api_base/health/operations" "healthy"
check_json_endpoint "Web health" "$web_base/health" "ok" "web"

for path in / /get-a-cash-offer /privacy-policy /terms; do
  check_page "$path"
done

echo "Smoke tests passed for $web_base and $api_base."
