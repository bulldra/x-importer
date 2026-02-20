from datetime import datetime
from zoneinfo import ZoneInfo

from x_importer.main import resolve_period

JST = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")


class FakeArgs:
    def __init__(self, date=None, end=None, refresh=False):
        self.date = date
        self.end = end
        self.refresh = refresh


class TestResolvePeriod:
    def test_specific_date(self):
        args = FakeArgs(date="2026-02-20")
        start, end = resolve_period(args)
        start_jst = start.astimezone(JST)
        end_jst = end.astimezone(JST)
        assert start_jst.strftime("%Y-%m-%d") == "2026-02-20"
        assert end_jst.strftime("%Y-%m-%d") == "2026-02-21"

    def test_date_range(self):
        args = FakeArgs(date="2026-02-15", end="2026-02-20")
        start, end = resolve_period(args)
        start_jst = start.astimezone(JST)
        end_jst = end.astimezone(JST)
        assert start_jst.strftime("%Y-%m-%d") == "2026-02-15"
        assert end_jst.strftime("%Y-%m-%d") == "2026-02-20"

    def test_default_is_yesterday(self):
        args = FakeArgs()
        start, end = resolve_period(args)
        start_jst = start.astimezone(JST)
        end_jst = end.astimezone(JST)
        today = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
        assert end_jst.date() == today.date()
        assert (end_jst - start_jst).days == 1

    def test_returns_utc(self):
        args = FakeArgs(date="2026-02-20")
        start, end = resolve_period(args)
        assert start.tzinfo == UTC
        assert end.tzinfo == UTC
