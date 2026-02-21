import logging
from pathlib import Path
from urllib.parse import urlparse

import requests

logger = logging.getLogger("x_importer")

MEDIA_DIR_NAME = "media"
_TIMEOUT = 30


def _best_video_url(variants: list[dict]) -> str | None:
    """最高ビットレートの mp4 URL を返す"""
    mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
    if not mp4s:
        return None
    best = max(mp4s, key=lambda v: v.get("bit_rate", 0))
    return best.get("url")


def _media_url(media: dict) -> str | None:
    """メディアのダウンロード URL を決定"""
    media_type = media.get("type", "")
    if media_type == "photo":
        return media.get("url")
    if media_type in ("video", "animated_gif"):
        variants = media.get("variants", [])
        return _best_video_url(variants)
    return None


def _extension_from_url(url: str) -> str:
    """URL からファイル拡張子を推定"""
    path = urlparse(url).path
    if "." in path:
        ext = path.rsplit(".", 1)[-1].split("?")[0]
        if ext in ("jpg", "jpeg", "png", "gif", "mp4", "webp"):
            return ext
    return "jpg"


def _alt_photo_url(url: str) -> str | None:
    """pbs.twimg.com の旧形式 URL を新形式に変換"""
    parsed = urlparse(url)
    if parsed.hostname != "pbs.twimg.com":
        return None
    path = parsed.path
    filename = path.rsplit("/", 1)[-1] if "/" in path else path
    if "." not in filename:
        return None
    base, ext = filename.rsplit(".", 1)
    base_path = path.rsplit("/", 1)[0] if "/" in path else ""
    return f"https://pbs.twimg.com{base_path}/{base}?format={ext}&name=large"


def _media_dir(output_dir: Path) -> Path:
    return output_dir / MEDIA_DIR_NAME


def download_media_for_tweets(
    tweets: list[dict],
    includes: dict,
    output_dir: Path,
) -> dict[str, str]:
    """ツイートのメディアをダウンロードし、media_key → 相対パスの辞書を返す。

    Returns:
        dict: {media_key: "media/filename.ext"} (Markdown 埋め込み用の相対パス)
    """
    media_map: dict[str, dict] = {}
    for m in includes.get("media", []):
        media_map[m["media_key"]] = m

    if not media_map:
        return {}

    # ツイートに紐づくメディアキーを収集（自分のツイート + referenced tweets）
    needed_keys: set[str] = set()
    for tweet in tweets:
        for key in tweet.get("attachments", {}).get("media_keys", []):
            if key in media_map:
                needed_keys.add(key)
    for ref_tweet in includes.get("tweets", []):
        for key in ref_tweet.get("attachments", {}).get("media_keys", []):
            if key in media_map:
                needed_keys.add(key)
    # article のカバー画像
    for tweet in tweets:
        cover = tweet.get("article", {}).get("cover_media")
        if cover and cover in media_map:
            needed_keys.add(cover)

    if not needed_keys:
        return {}

    media_dir = _media_dir(output_dir)
    media_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, str] = {}

    for media_key in needed_keys:
        media = media_map[media_key]
        url = _media_url(media)
        if not url:
            logger.debug("ダウンロード URL なし: %s", media_key)
            continue

        ext = _extension_from_url(url)
        filename = f"{media_key}.{ext}"
        file_path = media_dir / filename
        relative_path = f"{MEDIA_DIR_NAME}/{filename}"

        if file_path.exists():
            logger.debug("メディア既存: %s", relative_path)
            result[media_key] = relative_path
            continue

        try:
            resp = requests.get(url, timeout=_TIMEOUT, stream=True)
            # 404 の場合 pbs.twimg.com は ?format=ext&name=large 形式を試行
            if resp.status_code == 404:
                alt_url = _alt_photo_url(url)
                if alt_url:
                    resp = requests.get(alt_url, timeout=_TIMEOUT, stream=True)
            resp.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info("メディア取得: %s (%s)", relative_path, media.get("type", ""))
            result[media_key] = relative_path
        except Exception as e:
            logger.warning("メディア取得失敗: %s (%s)", url, e)

    return result
