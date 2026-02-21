import sys
from dataclasses import dataclass, field
from datetime import datetime

import tweepy

from x_importer import config


@dataclass
class UserInfo:
    id: str
    username: str


@dataclass
class FetchResult:
    tweets: list[dict] = field(default_factory=list)
    includes: dict = field(default_factory=dict)
    request_count: int = 0
    from_cache: bool = False


def create_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=config.X_API_KEY,
        consumer_secret=config.X_API_SECRET,
        access_token=config.X_ACCESS_TOKEN,
        access_token_secret=config.X_ACCESS_TOKEN_SECRET,
    )


def get_me(client: tweepy.Client) -> UserInfo:
    try:
        resp = client.get_me(user_auth=True)
        if resp.data:
            return UserInfo(id=str(resp.data.id), username=resp.data.username)
    except tweepy.errors.TweepyException as e:
        print(f"エラー: 認証に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)
    print("エラー: ユーザー情報を取得できませんでした。", file=sys.stderr)
    sys.exit(1)


def _tweet_to_dict(tweet: tweepy.Tweet) -> dict:
    """tweepy.Tweet の全データを dict 化（キャッシュ用に全フィールド保持）"""
    d = dict(tweet.data)
    d["id"] = str(d.get("id", ""))
    if "author_id" in d:
        d["author_id"] = str(d["author_id"])
    if "referenced_tweets" in d:
        d["referenced_tweets"] = [
            {**rt, "id": str(rt["id"])} for rt in d["referenced_tweets"]
        ]
    if "attachments" in d and "media_keys" in d.get("attachments", {}):
        d["attachments"]["media_keys"] = [
            str(k) for k in d["attachments"]["media_keys"]
        ]
    if "created_at" in d and hasattr(d["created_at"], "isoformat"):
        d["created_at"] = d["created_at"].isoformat()
    return d


def _user_to_dict(user: tweepy.User) -> dict:
    """tweepy.User の全データを dict 化"""
    d = dict(user.data)
    d["id"] = str(d.get("id", ""))
    return d


def _media_to_dict(media: tweepy.Media) -> dict:
    """tweepy.Media の全データを dict 化"""
    return dict(media.data)


def fetch_user_tweets(
    client: tweepy.Client,
    user_id: str,
    start_time: datetime,
    end_time: datetime,
) -> FetchResult:
    result = FetchResult()
    pagination_token: str | None = None

    while True:
        response = client.get_users_tweets(
            id=user_id,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            max_results=100,
            tweet_fields=[
                "created_at",
                "public_metrics",
                "entities",
                "referenced_tweets",
                "author_id",
                "attachments",
                "note_tweet",
                "article",
            ],
            expansions=[
                "referenced_tweets.id",
                "referenced_tweets.id.author_id",
                "attachments.media_keys",
                "article.cover_media",
                "article.media_entities",
            ],
            media_fields=["url", "type", "variants", "preview_image_url"],
            pagination_token=pagination_token,
            user_auth=True,
        )
        result.request_count += 1

        if response.data:
            result.tweets.extend(_tweet_to_dict(t) for t in response.data)

        if response.includes:
            for key, values in response.includes.items():
                id_field = "media_key" if key == "media" else "id"
                existing_ids = {
                    item[id_field] for item in result.includes.get(key, [])
                }
                for item in values:
                    if isinstance(item, tweepy.Tweet):
                        d = _tweet_to_dict(item)
                    elif isinstance(item, tweepy.User):
                        d = _user_to_dict(item)
                    elif isinstance(item, tweepy.Media):
                        d = _media_to_dict(item)
                    else:
                        d = {"id": str(item.id)}
                    item_id = d.get(id_field, d.get("id", ""))
                    if item_id not in existing_ids:
                        result.includes.setdefault(key, []).append(d)

        meta = response.meta or {}
        pagination_token = meta.get("next_token")
        if not pagination_token:
            break

    return result


def fetch_missing_media(
    client: tweepy.Client,
    result: FetchResult,
) -> int:
    """includes.tweets のメディアキーで includes.media にないものを補完取得する。

    Returns:
        追加取得した API リクエスト数
    """
    existing_media_keys = {
        m["media_key"] for m in result.includes.get("media", [])
    }

    # メディアキーを持つがメタデータがない referenced tweets を特定
    missing_tweet_ids: list[str] = []
    for ref_tweet in result.includes.get("tweets", []):
        for key in ref_tweet.get("attachments", {}).get("media_keys", []):
            if key not in existing_media_keys:
                missing_tweet_ids.append(ref_tweet["id"])
                break
        # article の cover_media も確認
        cover = ref_tweet.get("article", {}).get("cover_media")
        if cover and cover not in existing_media_keys and ref_tweet["id"] not in missing_tweet_ids:
            missing_tweet_ids.append(ref_tweet["id"])

    if not missing_tweet_ids:
        return 0

    # 100件ずつバッチ取得
    request_count = 0
    for i in range(0, len(missing_tweet_ids), 100):
        batch = missing_tweet_ids[i : i + 100]
        resp = client.get_tweets(
            ids=batch,
            tweet_fields=["attachments", "article"],
            expansions=["attachments.media_keys", "article.cover_media"],
            media_fields=["url", "type", "variants", "preview_image_url"],
            user_auth=True,
        )
        request_count += 1

        if resp.includes:
            for item in resp.includes.get("media", []):
                if isinstance(item, tweepy.Media):
                    d = _media_to_dict(item)
                else:
                    continue
                if d["media_key"] not in existing_media_keys:
                    result.includes.setdefault("media", []).append(d)
                    existing_media_keys.add(d["media_key"])

    result.request_count += request_count
    return request_count


def result_to_cache_dict(result: FetchResult) -> dict:
    return {"tweets": result.tweets, "includes": result.includes}


def result_from_cache_dict(data: dict) -> FetchResult:
    return FetchResult(
        tweets=data.get("tweets", []),
        includes=data.get("includes", {}),
        request_count=0,
        from_cache=True,
    )
