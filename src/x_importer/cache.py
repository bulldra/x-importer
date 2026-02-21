import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from x_importer import config

JST = ZoneInfo("Asia/Tokyo")


def _cache_dir() -> Path:
    return config.get_cache_dir()


def _cache_path(date_str: str) -> Path:
    """日付ごとのキャッシュファイルパス (e.g., '2026-02-19' -> '.../20260219.json')"""
    return _cache_dir() / f"{date_str.replace('-', '')}.json"


def _dates_in_range(start: datetime, end: datetime) -> list[str]:
    """start ~ end (exclusive) の範囲に含まれる JST 日付のリストを返す"""
    start_jst = start.astimezone(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    end_jst = end.astimezone(JST)
    dates: list[str] = []
    current = start_jst
    while current < end_jst:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def _group_tweets_by_date(tweets: list[dict]) -> dict[str, list[dict]]:
    """ツイートを JST 日付でグルーピング"""
    groups: dict[str, list[dict]] = {}
    for tweet in tweets:
        dt = datetime.fromisoformat(tweet["created_at"]).astimezone(JST)
        date_key = dt.strftime("%Y-%m-%d")
        groups.setdefault(date_key, []).append(tweet)
    return groups


def _validate_cache(data: dict) -> bool:
    """キャッシュ JSON の構造を検証"""
    if not isinstance(data, dict):
        return False
    if "tweets" not in data or not isinstance(data["tweets"], list):
        return False
    if "includes" in data and not isinstance(data["includes"], dict):
        return False
    for tweet in data["tweets"]:
        if not isinstance(tweet, dict):
            return False
        if "id" not in tweet or "text" not in tweet:
            return False
    return True


def _merge_includes(base: dict, new: dict) -> dict:
    """includes を重複なしでマージ"""
    merged = {k: list(v) for k, v in base.items()}
    for key, values in new.items():
        existing = merged.setdefault(key, [])
        id_field = "media_key" if key == "media" else "id"
        existing_ids = {item.get(id_field, item.get("id", "")) for item in existing}
        for item in values:
            item_id = item.get(id_field, item.get("id", ""))
            if item_id not in existing_ids:
                existing.append(item)
                existing_ids.add(item_id)
    return merged


def load(start: datetime, end: datetime) -> dict | None:
    """範囲内の全日付のキャッシュを結合して返す。1日でも欠けていれば None。"""
    dates = _dates_in_range(start, end)
    if not dates:
        return None

    all_tweets: list[dict] = []
    merged_includes: dict = {}

    for date_str in dates:
        path = _cache_path(date_str)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not _validate_cache(data):
            return None
        all_tweets.extend(data["tweets"])
        merged_includes = _merge_includes(merged_includes, data.get("includes", {}))

    return {"tweets": all_tweets, "includes": merged_includes}


def save(data: dict) -> list[Path]:
    """ツイートを JST 日付でグルーピングし、日付ごとにキャッシュ保存。"""
    cache_dir = _cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    tweets = data.get("tweets", [])
    includes = data.get("includes", {})
    groups = _group_tweets_by_date(tweets)
    paths: list[Path] = []

    for date_str, day_tweets in groups.items():
        day_data = {"tweets": day_tweets, "includes": includes}
        path = _cache_path(date_str)
        path.write_text(
            json.dumps(day_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        paths.append(path)

    return paths
