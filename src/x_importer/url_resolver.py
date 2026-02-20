import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger("x_importer")

_TIMEOUT = 5
_MAX_REDIRECTS = 5
_X_DOMAINS = {"x.com", "twitter.com"}


def _is_x_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        return host.replace("www.", "") in _X_DOMAINS
    except Exception:
        return False


def _is_private_host(url: str) -> bool:
    """プライベート IP / ループバックへのリクエストをブロック (SSRF 対策)"""
    try:
        hostname = urlparse(url).hostname or ""
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return True
    except (socket.gaierror, ValueError, OSError):
        return True  # 名前解決失敗は安全側に倒す
    return False


def _create_session() -> requests.Session:
    """リダイレクト回数を制限したセッションを生成"""
    session = requests.Session()
    session.max_redirects = _MAX_REDIRECTS
    adapter = HTTPAdapter(max_retries=0)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_title(url: str) -> str | None:
    if _is_x_url(url):
        return None
    if _is_private_host(url):
        logger.debug("プライベートホストをスキップ: %s", url)
        return None
    try:
        session = _create_session()
        resp = session.get(
            url, timeout=_TIMEOUT, headers={"User-Agent": "x-importer"}
        )
        resp.raise_for_status()
        match = re.search(r"<title[^>]*>([^<]+)</title>", resp.text, re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            logger.debug("タイトル取得: %s -> %s", url, title)
            return title
        logger.debug("タイトルなし: %s", url)
    except Exception as e:
        logger.debug("タイトル取得失敗: %s (%s)", url, e)
    return None


def resolve_titles_in_tweets(tweets: list[dict]) -> None:
    for tweet in tweets:
        _resolve_entities(tweet.get("entities", {}))


def _resolve_entities(entities: dict) -> None:
    for url_entity in entities.get("urls", []):
        if "title" in url_entity:
            continue
        expanded = url_entity.get("expanded_url", url_entity.get("url", ""))
        title = fetch_title(expanded)
        if title:
            url_entity["title"] = title
