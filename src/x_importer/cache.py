import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from x_importer import config

JST = ZoneInfo("Asia/Tokyo")
CACHE_DIR_NAME = ".cache"


def _cache_dir() -> Path:
    return config.get_output_path() / CACHE_DIR_NAME


def _cache_path(start: datetime, end: datetime) -> Path:
    start_str = start.astimezone(JST).strftime("%Y%m%d")
    end_str = end.astimezone(JST).strftime("%Y%m%d")
    return _cache_dir() / f"{start_str}_{end_str}.json"


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


def load(start: datetime, end: datetime) -> dict | None:
    path = _cache_path(start, end)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not _validate_cache(data):
        return None
    return data


def save(start: datetime, end: datetime, data: dict) -> Path:
    cache_dir = _cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(start, end)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
