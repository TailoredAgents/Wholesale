from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

COMPANY_TIME_ZONE_NAME = "America/New_York"
COMPANY_TIME_ZONE = ZoneInfo(COMPANY_TIME_ZONE_NAME)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def company_date(value: datetime) -> date:
    return as_utc(value).astimezone(COMPANY_TIME_ZONE).date()


def company_day_bounds(value: datetime) -> tuple[datetime, datetime]:
    local_date = company_date(value)
    local_start = datetime.combine(local_date, time.min, tzinfo=COMPANY_TIME_ZONE)
    local_end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=COMPANY_TIME_ZONE)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)
