from datetime import UTC, datetime, timedelta

from app.services.company_time import company_date, company_day_bounds


def test_company_date_uses_eastern_business_day() -> None:
    assert company_date(datetime(2026, 9, 18, 2, 30, tzinfo=UTC)).isoformat() == "2026-09-17"
    assert company_date(datetime(2026, 9, 18, 4, 30, tzinfo=UTC)).isoformat() == "2026-09-18"


def test_company_day_bounds_respect_daylight_saving_time() -> None:
    summer_start, summer_end = company_day_bounds(datetime(2026, 7, 10, 16, tzinfo=UTC))
    winter_start, winter_end = company_day_bounds(datetime(2026, 1, 10, 16, tzinfo=UTC))

    assert summer_start == datetime(2026, 7, 10, 4, tzinfo=UTC)
    assert summer_end == datetime(2026, 7, 11, 4, tzinfo=UTC)
    assert winter_start == datetime(2026, 1, 10, 5, tzinfo=UTC)
    assert winter_end == datetime(2026, 1, 11, 5, tzinfo=UTC)


def test_company_day_bounds_cover_short_and_long_dst_days() -> None:
    spring_start, spring_end = company_day_bounds(datetime(2026, 3, 8, 16, tzinfo=UTC))
    fall_start, fall_end = company_day_bounds(datetime(2026, 11, 1, 16, tzinfo=UTC))

    assert spring_end - spring_start == timedelta(hours=23)
    assert fall_end - fall_start == timedelta(hours=25)
