"""Regression tests for legacy timestamp formats in distributor admin stats."""
from datetime import datetime, timedelta, timezone

from routes.distributor_admin import _created_at_day, _within_days


def test_created_at_day_accepts_native_mongo_datetime_and_iso_string():
    now = datetime.now(timezone.utc)
    assert _created_at_day(now) == now.date().isoformat()
    assert _created_at_day(now.isoformat()) == now.date().isoformat()
    assert _created_at_day("invalid") == ""
    assert _created_at_day(None) == ""


def test_within_days_accepts_aware_and_naive_datetimes_and_iso_strings():
    now = datetime.now(timezone.utc)
    assert _within_days(now, 7)
    assert _within_days(now.replace(tzinfo=None), 7)
    assert _within_days(now.isoformat(), 7)
    assert not _within_days(now - timedelta(days=8), 7)
    assert not _within_days(now + timedelta(minutes=1), 7)
    assert not _within_days("not-a-timestamp", 7)
