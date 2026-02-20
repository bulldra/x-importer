from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from x_importer import cache

UTC = ZoneInfo("UTC")
JST = ZoneInfo("Asia/Tokyo")


class TestCache:
    def test_save_and_load(self, tmp_path):
        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 21, 0, 0, tzinfo=JST)
        data = {"tweets": [{"id": "1", "text": "test"}], "includes": {}}

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            cache.save(start, end, data)
            loaded = cache.load(start, end)

        assert loaded == data

    def test_load_missing_returns_none(self, tmp_path):
        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 21, 0, 0, tzinfo=JST)

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            assert cache.load(start, end) is None

    def test_load_invalid_json_returns_none(self, tmp_path):
        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 21, 0, 0, tzinfo=JST)

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            path = cache._cache_path(start, end)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not json", encoding="utf-8")
            assert cache.load(start, end) is None

    def test_load_invalid_structure_returns_none(self, tmp_path):
        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 21, 0, 0, tzinfo=JST)

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            # tweets が無い
            cache.save(start, end, {"tweets": "not_a_list", "includes": {}})
            assert cache.load(start, end) is None

    def test_load_tweet_missing_id_returns_none(self, tmp_path):
        start = datetime(2026, 2, 20, 0, 0, tzinfo=JST)
        end = datetime(2026, 2, 21, 0, 0, tzinfo=JST)

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            cache.save(start, end, {"tweets": [{"text": "no id"}], "includes": {}})
            assert cache.load(start, end) is None

    def test_cache_filename_uses_jst(self, tmp_path):
        # UTC 2/19 15:00 = JST 2/20 00:00
        start = datetime(2026, 2, 19, 15, 0, tzinfo=UTC)
        end = datetime(2026, 2, 20, 15, 0, tzinfo=UTC)

        with patch.object(cache, "_cache_dir", return_value=tmp_path / ".cache"):
            path = cache.save(start, end, {"tweets": []})

        assert path.name == "20260220_20260221.json"
