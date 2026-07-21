#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${API_BASE_URL:-}" || -z "${WEB_BASE_URL:-}" ]]; then
  echo "API_BASE_URL and WEB_BASE_URL are required." >&2
  exit 1
fi

api_base="${API_BASE_URL%/}"
web_base="${WEB_BASE_URL%/}"

health_payload="$(curl --fail --silent --show-error --max-time 20 "$api_base/health")"
ready_payload="$(curl --fail --silent --show-error --max-time 20 "$api_base/ready")"

if [[ "$health_payload" != *'"status":"ok"'* ]]; then
  echo "API health response was unexpected: $health_payload" >&2
  exit 1
fi

if [[ "$ready_payload" != *'"status":"ready"'* ]]; then
  echo "API readiness response was unexpected: $ready_payload" >&2
  exit 1
fi

for path in / /get-a-cash-offer /privacy-policy /terms; do
  curl --fail --silent --show-error --max-time 20 --output /dev/null "$web_base$path"
done

echo "Smoke tests passed for $web_base and $api_base."
