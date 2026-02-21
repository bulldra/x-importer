from unittest.mock import MagicMock, patch

from x_importer.media import (
    _alt_photo_url,
    _best_video_url,
    _extension_from_url,
    _media_url,
    download_media_for_tweets,
)

from .conftest import make_tweet


class TestBestVideoUrl:
    def test_selects_highest_bitrate(self):
        variants = [
            {"content_type": "video/mp4", "bit_rate": 832000, "url": "https://v.co/low.mp4"},
            {"content_type": "video/mp4", "bit_rate": 2176000, "url": "https://v.co/high.mp4"},
            {"content_type": "application/x-mpegURL", "url": "https://v.co/stream.m3u8"},
        ]
        assert _best_video_url(variants) == "https://v.co/high.mp4"

    def test_no_mp4(self):
        variants = [
            {"content_type": "application/x-mpegURL", "url": "https://v.co/stream.m3u8"},
        ]
        assert _best_video_url(variants) is None

    def test_empty_variants(self):
        assert _best_video_url([]) is None


class TestMediaUrl:
    def test_photo(self):
        media = {"type": "photo", "url": "https://pbs.twimg.com/media/abc.jpg"}
        assert _media_url(media) == "https://pbs.twimg.com/media/abc.jpg"

    def test_video(self):
        media = {
            "type": "video",
            "variants": [
                {"content_type": "video/mp4", "bit_rate": 2176000, "url": "https://v.co/vid.mp4"},
            ],
        }
        assert _media_url(media) == "https://v.co/vid.mp4"

    def test_animated_gif(self):
        media = {
            "type": "animated_gif",
            "variants": [
                {"content_type": "video/mp4", "bit_rate": 0, "url": "https://v.co/gif.mp4"},
            ],
        }
        assert _media_url(media) == "https://v.co/gif.mp4"

    def test_unknown_type(self):
        media = {"type": "unknown"}
        assert _media_url(media) is None


class TestExtensionFromUrl:
    def test_jpg(self):
        assert _extension_from_url("https://pbs.twimg.com/media/abc.jpg") == "jpg"

    def test_png(self):
        assert _extension_from_url("https://pbs.twimg.com/media/abc.png") == "png"

    def test_mp4(self):
        assert _extension_from_url("https://video.twimg.com/ext/abc.mp4?tag=12") == "mp4"

    def test_no_extension(self):
        assert _extension_from_url("https://example.com/noext") == "jpg"


class TestDownloadMediaForTweets:
    def test_no_media_in_includes(self, tmp_path):
        tweets = [make_tweet()]
        result = download_media_for_tweets(tweets, {}, tmp_path)
        assert result == {}

    def test_no_media_keys_in_tweets(self, tmp_path):
        tweets = [make_tweet()]
        includes = {"media": [{"media_key": "mk1", "type": "photo", "url": "https://example.com/a.jpg"}]}
        result = download_media_for_tweets(tweets, includes, tmp_path)
        assert result == {}

    @patch("x_importer.media.requests.get")
    def test_downloads_photo(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"fake image data"]
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        tweets = [make_tweet(attachments={"media_keys": ["mk1"]})]
        includes = {
            "media": [{"media_key": "mk1", "type": "photo", "url": "https://pbs.twimg.com/media/abc.jpg"}]
        }
        result = download_media_for_tweets(tweets, includes, tmp_path)
        assert "mk1" in result
        assert result["mk1"] == "media/mk1.jpg"
        assert (tmp_path / "media" / "mk1.jpg").exists()

    def test_skips_existing_file(self, tmp_path):
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "mk1.jpg").write_bytes(b"existing")

        tweets = [make_tweet(attachments={"media_keys": ["mk1"]})]
        includes = {
            "media": [{"media_key": "mk1", "type": "photo", "url": "https://pbs.twimg.com/media/abc.jpg"}]
        }
        result = download_media_for_tweets(tweets, includes, tmp_path)
        assert result["mk1"] == "media/mk1.jpg"

    @patch("x_importer.media.requests.get")
    def test_downloads_video(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"fake video data"]
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        tweets = [make_tweet(attachments={"media_keys": ["mk2"]})]
        includes = {
            "media": [{
                "media_key": "mk2",
                "type": "video",
                "variants": [
                    {"content_type": "video/mp4", "bit_rate": 2176000, "url": "https://video.twimg.com/ext/vid.mp4"},
                ],
            }]
        }
        result = download_media_for_tweets(tweets, includes, tmp_path)
        assert "mk2" in result
        assert result["mk2"] == "media/mk2.mp4"

    @patch("x_importer.media.requests.get")
    def test_handles_download_failure(self, mock_get, tmp_path):
        mock_get.side_effect = Exception("Network error")

        tweets = [make_tweet(attachments={"media_keys": ["mk1"]})]
        includes = {
            "media": [{"media_key": "mk1", "type": "photo", "url": "https://pbs.twimg.com/media/abc.jpg"}]
        }
        result = download_media_for_tweets(tweets, includes, tmp_path)
        assert result == {}

    @patch("x_importer.media.requests.get")
    def test_collects_referenced_tweet_media(self, mock_get, tmp_path):
        """includes.tweets 内のメディアキーも収集する"""
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"ref image"]
        mock_resp.raise_for_status.return_value = None
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        tweets = [make_tweet(
            referenced_tweets=[{"type": "quoted", "id": "ref1"}],
        )]
        includes = {
            "media": [{"media_key": "mk_ref", "type": "photo", "url": "https://pbs.twimg.com/media/ref.jpg"}],
            "tweets": [{"id": "ref1", "text": "quoted", "attachments": {"media_keys": ["mk_ref"]}}],
        }
        result = download_media_for_tweets(tweets, includes, tmp_path)
        assert "mk_ref" in result
        assert result["mk_ref"] == "media/mk_ref.jpg"

    @patch("x_importer.media.requests.get")
    def test_collects_article_cover_media(self, mock_get, tmp_path):
        """article の cover_media を収集する"""
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"cover image"]
        mock_resp.raise_for_status.return_value = None
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        tweets = [make_tweet(article={"title": "Test", "cover_media": "mk_cover"})]
        includes = {
            "media": [{"media_key": "mk_cover", "type": "photo", "url": "https://pbs.twimg.com/media/cover.jpg"}],
        }
        result = download_media_for_tweets(tweets, includes, tmp_path)
        assert "mk_cover" in result


class TestAltPhotoUrl:
    def test_converts_pbs_url(self):
        url = "https://pbs.twimg.com/media/abc.jpg"
        assert _alt_photo_url(url) == "https://pbs.twimg.com/media/abc?format=jpg&name=large"

    def test_converts_png(self):
        url = "https://pbs.twimg.com/media/XYZ123.png"
        assert _alt_photo_url(url) == "https://pbs.twimg.com/media/XYZ123?format=png&name=large"

    def test_non_pbs_returns_none(self):
        url = "https://video.twimg.com/ext/vid.mp4"
        assert _alt_photo_url(url) is None

    def test_no_extension_returns_none(self):
        url = "https://pbs.twimg.com/media/noext"
        assert _alt_photo_url(url) is None

    def test_nested_path(self):
        url = "https://pbs.twimg.com/tweet_video_thumb/abc.jpg"
        assert _alt_photo_url(url) == "https://pbs.twimg.com/tweet_video_thumb/abc?format=jpg&name=large"
