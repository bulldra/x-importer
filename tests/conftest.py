"""テスト用の共通フィクスチャ・スタブデータ"""

import pytest


def make_tweet(
    id: str = "123456",
    text: str = "テストツイート",
    created_at: str = "2026-02-20T00:30:00+00:00",
    like: int = 5,
    rt: int = 2,
    reply: int = 1,
    impression: int = 100,
    referenced_tweets: list | None = None,
    entities: dict | None = None,
    author_id: str | None = None,
) -> dict:
    d: dict = {
        "id": id,
        "text": text,
        "created_at": created_at,
        "public_metrics": {
            "like_count": like,
            "retweet_count": rt,
            "reply_count": reply,
            "impression_count": impression,
        },
    }
    if referenced_tweets:
        d["referenced_tweets"] = referenced_tweets
    if entities:
        d["entities"] = entities
    if author_id:
        d["author_id"] = author_id
    return d


@pytest.fixture()
def sample_tweet():
    return make_tweet()


@pytest.fixture()
def sample_tweet_with_url():
    return make_tweet(
        id="111",
        text="リンク https://t.co/abc123 を参照",
        entities={
            "urls": [
                {"url": "https://t.co/abc123", "expanded_url": "https://example.com/full"}
            ]
        },
    )


@pytest.fixture()
def sample_retweet():
    return make_tweet(
        id="222",
        text="RT @other_user: 元のツイート内容",
        like=0,
        rt=500,
        reply=0,
        impression=0,
        referenced_tweets=[{"type": "retweeted", "id": "999"}],
    )


@pytest.fixture()
def sample_quote_tweet():
    return make_tweet(
        id="333",
        text="引用コメント https://t.co/xyz",
        like=3,
        rt=1,
        reply=0,
        impression=50,
        referenced_tweets=[{"type": "quoted", "id": "888"}],
        entities={
            "urls": [
                {
                    "url": "https://t.co/xyz",
                    "expanded_url": "https://twitter.com/someone/status/888",
                }
            ]
        },
    )


@pytest.fixture()
def sample_includes():
    return {
        "tweets": [
            {
                "id": "999",
                "text": "元のツイート内容",
                "author_id": "50000",
            },
            {
                "id": "888",
                "text": "引用元の本文",
                "author_id": "60000",
            },
        ],
        "users": [
            {"id": "50000", "username": "other_user"},
            {"id": "60000", "username": "someone"},
        ],
    }
