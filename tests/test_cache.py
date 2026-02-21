from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from x_importer import cache

UTC = ZoneInfo("UTC")
JST = ZoneInfo("Asia/Tokyo")


def _make_data(tweets, includes=None):
    return {"tweets": tweets, "includes": includes or {}}


class TestCache:
    def test_save_and_load(self, tmp_path):
        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 21, 0, 0, tzinfo=JST)
        data = _make_data([
            {"id": "1", "text": "test", "created_at": "2026-02-20T01:00:00+09:00"},
        ])

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            cache.save(data)
            loaded = cache.load(start, end)

        assert loaded is not None
        assert len(loaded["tweets"]) == 1
        assert loaded["tweets"][0]["id"] == "1"

    def test_load_missing_returns_none(self, tmp_path):
        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 21, 0, 0, tzinfo=JST)

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            assert cache.load(start, end) is None

    def test_load_invalid_json_returns_none(self, tmp_path):
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "20260220.json").write_text("not json", encoding="utf-8")

        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 21, 0, 0, tzinfo=JST)

        with patch.object(cache, "_cache_dir", return_value=cache_dir):
            assert cache.load(start, end) is None

    def test_load_invalid_structure_returns_none(self, tmp_path):
        import json

        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "20260220.json").write_text(
            json.dumps({"tweets": "not_a_list"}), encoding="utf-8"
        )

        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 21, 0, 0, tzinfo=JST)

        with patch.object(cache, "_cache_dir", return_value=cache_dir):
            assert cache.load(start, end) is None

    def test_load_tweet_missing_id_returns_none(self, tmp_path):
        import json

        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "20260220.json").write_text(
            json.dumps({"tweets": [{"text": "no id"}], "includes": {}}),
            encoding="utf-8",
        )

        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 21, 0, 0, tzinfo=JST)

        with patch.object(cache, "_cache_dir", return_value=cache_dir):
            assert cache.load(start, end) is None

    def test_saves_per_date(self, tmp_path):
        data = _make_data([
            {"id": "1", "text": "A", "created_at": "2026-02-20T10:00:00+09:00"},
            {"id": "2", "text": "B", "created_at": "2026-02-21T10:00:00+09:00"},
        ])

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            paths = cache.save(data)

        assert len(paths) == 2
        names = {p.name for p in paths}
        assert "20260220.json" in names
        assert "20260221.json" in names

    def test_load_multi_day_range(self, tmp_path):
        data = _make_data([
            {"id": "1", "text": "A", "created_at": "2026-02-20T10:00:00+09:00"},
            {"id": "2", "text": "B", "created_at": "2026-02-21T10:00:00+09:00"},
        ])

        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 22, 0, 0, tzinfo=JST)

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            cache.save(data)
            loaded = cache.load(start, end)

        assert loaded is not None
        assert len(loaded["tweets"]) == 2

    def test_partial_cache_returns_none(self, tmp_path):
        """2日間の範囲で1日分しかキャッシュがなければ None"""
        data = _make_data([
            {"id": "1", "text": "A", "created_at": "2026-02-20T10:00:00+09:00"},
        ])

        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 22, 0, 0, tzinfo=JST)  # 2日間

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            cache.save(data)
            loaded = cache.load(start, end)

        assert loaded is None

    def test_cache_filename_uses_jst(self, tmp_path):
        # UTC 2/19 15:00 = JST 2/20 00:00
        data = _make_data([
            {"id": "1", "text": "test", "created_at": "2026-02-19T15:00:00+00:00"},
        ])

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            paths = cache.save(data)

        assert len(paths) == 1
        assert paths[0].name == "20260220.json"

    def test_merges_includes_without_duplicates(self, tmp_path):
        includes = {
            "users": [{"id": "100", "username": "alice"}],
            "tweets": [{"id": "ref1", "text": "ref"}],
        }
        data1 = _make_data(
            [{"id": "1", "text": "A", "created_at": "2026-02-20T10:00:00+09:00"}],
            includes,
        )
        data2 = _make_data(
            [{"id": "2", "text": "B", "created_at": "2026-02-21T10:00:00+09:00"}],
            includes,
        )

        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 22, 0, 0, tzinfo=JST)

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            cache.save(data1)
            cache.save(data2)
            loaded = cache.load(start, end)

        assert loaded is not None
        # 同じ includes が重複しないこと
        assert len(loaded["includes"]["users"]) == 1
        assert len(loaded["includes"]["tweets"]) == 1


class TestDatesInRange:
    def test_single_day(self):
        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 21, 0, 0, tzinfo=JST)
        assert cache._dates_in_range(start, end) == ["2026-02-20"]

    def test_multi_day(self):
        start = datetime(2026, 2, 19, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 22, 0, 0, tzinfo=JST)
        assert cache._dates_in_range(start, end) == [
            "2026-02-19", "2026-02-20", "2026-02-21",
        ]

    def test_utc_to_jst_conversion(self):
        # UTC 2/19 15:00 = JST 2/20 00:00
        start = datetime(2026, 2, 19, 15, 0, tzinfo=UTC)
        end = datetime(2026, 2, 20, 15, 0, tzinfo=UTC)
        assert cache._dates_in_range(start, end) == ["2026-02-20"]
