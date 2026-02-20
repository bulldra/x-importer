from x_importer.client import FetchResult, result_from_cache_dict, result_to_cache_dict


class TestCacheRoundTrip:
    def test_roundtrip(self):
        original = FetchResult(
            tweets=[{"id": "1", "text": "hello"}],
            includes={"tweets": [{"id": "2", "text": "quoted"}]},
            request_count=1,
        )
        data = result_to_cache_dict(original)
        restored = result_from_cache_dict(data)

        assert restored.tweets == original.tweets
        assert restored.includes == original.includes
        assert restored.request_count == 0
        assert restored.from_cache is True

    def test_empty_result(self):
        original = FetchResult()
        data = result_to_cache_dict(original)
        restored = result_from_cache_dict(data)

        assert restored.tweets == []
        assert restored.includes == {}
        assert restored.from_cache is True
