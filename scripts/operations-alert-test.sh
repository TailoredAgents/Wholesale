#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${OPERATIONS_ALERT_WEBHOOK_URL:-}" ]]; then
  echo "OPERATIONS_ALERT_WEBHOOK_URL is required." >&2
  exit 1
fi

occurred_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

curl \
  --fail \
  --silent \
  --show-error \
  --max-time 20 \
  --header "Content-Type: application/json" \
  --data "{
    \"event\": \"stonegate.controlled_test_alert\",
    \"service\": \"stonegate-operations\",
    \"operation\": \"alert_delivery_test\",
    \"error_type\": \"ControlledTest\",
    \"attempt_count\": 1,
    \"first_occurred_at\": \"$occurred_at\",
    \"last_occurred_at\": \"$occurred_at\"
  }" \
  "$OPERATIONS_ALERT_WEBHOOK_URL" \
  >/dev/null

echo "Controlled Stonegate operations alert delivered."

