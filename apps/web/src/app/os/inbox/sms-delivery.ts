export const SMS_DELIVERY_REFRESH_INTERVAL_MS = 2_000;
export const SMS_DELIVERY_REFRESH_MAX_ATTEMPTS = 15;
export const SMS_DELIVERY_AUTO_REFRESH_RECENCY_MS = 5 * 60_000;

const pendingTwilioSmsStatuses = new Set([
  "accepted",
  "scheduled",
  "queued",
  "sending",
  "sent",
]);

type SmsDeliveryTimelineItem = {
  id: string;
  direction: string | null;
  channel: string;
  status: string;
  provider: string | null;
  occurred_at: string;
};

export function isPendingOutboundTwilioSms(
  item: SmsDeliveryTimelineItem,
  nowMs = Date.now(),
) {
  const occurredAtMs = Date.parse(item.occurred_at);
  return (
    item.direction === "outbound" &&
    item.channel === "sms" &&
    item.provider === "twilio" &&
    Number.isFinite(occurredAtMs) &&
    Math.abs(nowMs - occurredAtMs) <= SMS_DELIVERY_AUTO_REFRESH_RECENCY_MS &&
    pendingTwilioSmsStatuses.has(item.status.toLowerCase())
  );
}

export function pendingOutboundTwilioSmsKey(
  timeline: SmsDeliveryTimelineItem[],
  nowMs = Date.now(),
) {
  return timeline
    .filter((item) => isPendingOutboundTwilioSms(item, nowMs))
    .map((item) => item.id)
    .sort()
    .join("|");
}
