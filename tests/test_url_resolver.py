from unittest.mock import MagicMock, patch

from x_importer.url_resolver import (
    _is_private_host,
    _is_x_url,
    fetch_title,
    resolve_titles_in_tweets,
)


class TestIsXUrl:
    def test_x_dot_com(self):
        assert _is_x_url("https://x.com/user/status/123") is True

    def test_twitter_dot_com(self):
        assert _is_x_url("https://twitter.com/user/status/123") is True

    def test_other_domain(self):
        assert _is_x_url("https://github.com/repo") is False

    def test_www_prefix(self):
        assert _is_x_url("https://www.x.com/user") is True


class TestIsPrivateHost:
    @patch("x_importer.url_resolver.socket.getaddrinfo")
    def test_blocks_loopback(self, mock_dns):
        mock_dns.return_value = [(None, None, None, None, ("127.0.0.1", 0))]
        assert _is_private_host("http://localhost/secret") is True

    @patch("x_importer.url_resolver.socket.getaddrinfo")
    def test_blocks_private_ip(self, mock_dns):
        mock_dns.return_value = [(None, None, None, None, ("192.168.1.1", 0))]
        assert _is_private_host("http://internal.local") is True

    @patch("x_importer.url_resolver.socket.getaddrinfo")
    def test_blocks_link_local(self, mock_dns):
        mock_dns.return_value = [(None, None, None, None, ("169.254.169.254", 0))]
        assert _is_private_host("http://169.254.169.254/metadata") is True

    @patch("x_importer.url_resolver.socket.getaddrinfo")
    def test_allows_public_ip(self, mock_dns):
        mock_dns.return_value = [(None, None, None, None, ("93.184.216.34", 0))]
        assert _is_private_host("https://example.com") is False

    @patch("x_importer.url_resolver.socket.getaddrinfo", side_effect=OSError)
    def test_blocks_on_dns_failure(self, mock_dns):
        assert _is_private_host("http://nonexistent.invalid") is True


class TestFetchTitle:
    def test_skips_x_urls(self):
        assert fetch_title("https://x.com/user/status/123") is None

    @patch("x_importer.url_resolver._is_private_host", return_value=False)
    @patch("x_importer.url_resolver._create_session")
    def test_extracts_title(self, mock_session, mock_private):
        mock_resp = MagicMock()
        mock_resp.text = "<html><head><title>My Page Title</title></head></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_resp

        assert fetch_title("https://example.com") == "My Page Title"

    @patch("x_importer.url_resolver._is_private_host", return_value=False)
    @patch("x_importer.url_resolver._create_session")
    def test_returns_none_on_error(self, mock_session, mock_private):
        mock_session.return_value.get.side_effect = Exception("timeout")
        assert fetch_title("https://example.com") is None

    @patch("x_importer.url_resolver._is_private_host", return_value=False)
    @patch("x_importer.url_resolver._create_session")
    def test_returns_none_when_no_title(self, mock_session, mock_private):
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>no title</body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_resp

        assert fetch_title("https://example.com") is None

    @patch("x_importer.url_resolver._is_private_host", return_value=True)
    def test_skips_private_host(self, mock_private):
        assert fetch_title("http://192.168.1.1/admin") is None


class TestResolveTitlesInTweets:
    @patch("x_importer.url_resolver.fetch_title", return_value="Fetched Title")
    def test_adds_title_to_entities(self, mock_fetch):
        tweets = [
            {
                "id": "1",
                "text": "link",
                "entities": {
                    "urls": [
                        {"url": "https://t.co/abc", "expanded_url": "https://example.com"}
                    ]
                },
            }
        ]
        resolve_titles_in_tweets(tweets)
        assert tweets[0]["entities"]["urls"][0]["title"] == "Fetched Title"

    @patch("x_importer.url_resolver.fetch_title")
    def test_skips_already_resolved(self, mock_fetch):
        tweets = [
            {
                "id": "1",
                "text": "link",
                "entities": {
                    "urls": [
                        {
                            "url": "https://t.co/abc",
                            "expanded_url": "https://example.com",
                            "title": "Cached Title",
                        }
                    ]
                },
            }
        ]
        resolve_titles_in_tweets(tweets)
        mock_fetch.assert_not_called()

    def test_no_entities(self):
        tweets = [{"id": "1", "text": "no link"}]
        resolve_titles_in_tweets(tweets)  # should not raise
