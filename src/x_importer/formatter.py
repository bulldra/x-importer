from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from x_importer import config

JST = ZoneInfo("Asia/Tokyo")


def _parse_dt(iso_str: str) -> datetime:
    return datetime.fromisoformat(iso_str).astimezone(JST)


def _build_ref_map(includes: dict) -> dict[str, dict]:
    ref_map: dict[str, dict] = {}
    user_map: dict[str, str] = {}
    for user in includes.get("users", []):
        user_map[user["id"]] = user.get("username", "")
    for tweet in includes.get("tweets", []):
        tweet["_author_username"] = user_map.get(tweet.get("author_id", ""), "")
        ref_map[tweet["id"]] = tweet
    return ref_map


def _sanitize_md_link_text(text: str) -> str:
    """Markdown リンクテキスト内の特殊文字を除去"""
    return text.replace("[", "").replace("]", "")


def _expand_urls(text: str, entities: dict) -> str:
    for url_entity in entities.get("urls", []):
        expanded = url_entity.get("expanded_url", url_entity["url"])
        title = url_entity.get("title")
        if title:
            safe_title = _sanitize_md_link_text(title)
            replacement = f"[{safe_title}]({expanded})"
        else:
            replacement = expanded
        text = text.replace(url_entity["url"], replacement)
    return text


def group_tweets_by_date(tweets: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for tweet in tweets:
        dt_jst = _parse_dt(tweet["created_at"])
        date_key = dt_jst.strftime("%Y-%m-%d")
        groups[date_key].append(tweet)
    for date_key in groups:
        groups[date_key].sort(key=lambda t: t["created_at"])
    return dict(groups)


_MAX_QUOTE_DEPTH = 5


def _format_quoted(
    ref_tweet: dict,
    ref_map: dict[str, dict],
    depth: int = 1,
    media_map: dict[str, str] | None = None,
) -> list[str]:
    prefix = "> " * depth
    empty_prefix = prefix.rstrip()
    mm = media_map or {}
    author = ref_tweet.get("_author_username", "")
    lines: list[str] = []
    if author:
        lines.append(f"{prefix}@{author}:")
        lines.append(empty_prefix)

    # article: タイトル + 本文
    article = ref_tweet.get("article")
    if article:
        title = article.get("title", "")
        if title:
            lines.append(f"{prefix}**{_sanitize_md_link_text(title)}**")
            lines.append(empty_prefix)
        cover_key = article.get("cover_media")
        if cover_key:
            path = mm.get(cover_key)
            if path:
                lines.append(f"{prefix}![]({path})")
                lines.append(empty_prefix)
        plain_text = article.get("plain_text", "")
        if plain_text:
            lines.append(prefix + plain_text.replace("\n", f"\n{prefix}"))
        return lines

    # note_tweet: 長文投稿は全文を使用
    note = ref_tweet.get("note_tweet")
    if note:
        entities = note.get("entities", ref_tweet.get("entities", {}))
        text = _expand_urls(note.get("text", ref_tweet["text"]), entities)
    else:
        text = _expand_urls(ref_tweet["text"], ref_tweet.get("entities", {}))
    lines.append(prefix + text.replace("\n", f"\n{prefix}"))

    # メディア埋め込み
    for key in ref_tweet.get("attachments", {}).get("media_keys", []):
        path = mm.get(key)
        if path:
            lines.append(empty_prefix)
            lines.append(f"{prefix}![]({path})")

    # 多段引用: 引用先がさらに引用を持つ場合に再帰展開
    if depth < _MAX_QUOTE_DEPTH:
        for ref in ref_tweet.get("referenced_tweets", []):
            if ref["type"] in ("quoted", "retweeted", "replied_to") and ref["id"] in ref_map:
                lines.append(empty_prefix)
                lines.extend(
                    _format_quoted(ref_map[ref["id"]], ref_map, depth + 1, mm)
                )

    return lines


def _is_plain_retweet(tweet: dict) -> bool:
    refs = tweet.get("referenced_tweets", [])
    return any(r["type"] == "retweeted" for r in refs)


def _build_self_reply_chains(
    tweets: list[dict],
) -> tuple[dict[str, list[dict]], set[str]]:
    """自己リプライチェーンを検出する。

    Returns:
        chain_heads: {先頭ツイートID: チェーン(時系列順)}
        suppressed: チェーン内で先頭以外のツイートID（個別表示しない）
    """
    tweet_map = {t["id"]: t for t in tweets}

    # child_id -> parent_id（両方が同日のツイートリスト内にある場合）
    child_to_parent: dict[str, str] = {}
    for t in tweets:
        for ref in t.get("referenced_tweets", []):
            if ref["type"] == "replied_to" and ref["id"] in tweet_map:
                child_to_parent[t["id"]] = ref["id"]

    # 末尾ツイート: 他のツイートからリプライされていないもの
    parent_ids = set(child_to_parent.values())
    tail_ids = set(tweet_map.keys()) - parent_ids

    chain_heads: dict[str, list[dict]] = {}
    suppressed: set[str] = set()

    for tail_id in tail_ids:
        chain_ids: list[str] = []
        current: str | None = tail_id
        while current:
            chain_ids.append(current)
            current = child_to_parent.get(current)
        chain_ids.reverse()  # 時系列順

        if len(chain_ids) > 1:
            chain = [tweet_map[tid] for tid in chain_ids]
            chain_heads[chain_ids[0]] = chain
            for tid in chain_ids[1:]:
                suppressed.add(tid)

    return chain_heads, suppressed


def _format_metrics(tweets: list[dict]) -> list[str]:
    """ツイート群のメトリクスをテーブルとして出力"""
    total_like = sum(t.get("public_metrics", {}).get("like_count", 0) for t in tweets)
    total_rt = sum(t.get("public_metrics", {}).get("retweet_count", 0) for t in tweets)
    total_reply = sum(t.get("public_metrics", {}).get("reply_count", 0) for t in tweets)
    total_imp = sum(
        t.get("public_metrics", {}).get("impression_count", 0) for t in tweets
    )
    return [
        "| Like | RT | Reply | Imp |",
        "|-----:|---:|------:|----:|",
        f"| {total_like} | {total_rt} | {total_reply} | {total_imp} |",
    ]


def _format_media(tweet: dict, media_map: dict[str, str]) -> list[str]:
    """ツイートに紐づくメディアの埋め込みを出力"""
    lines: list[str] = []
    for key in tweet.get("attachments", {}).get("media_keys", []):
        path = media_map.get(key)
        if path:
            lines.append(f"![]({path})")
            lines.append("")
    return lines


def _format_tweet_body(
    tweet: dict,
    ref_map: dict[str, dict],
    media_map: dict[str, str] | None = None,
    skip_replied_ids: set[str] | None = None,
) -> list[str]:
    """ツイート本文・引用RT・メディアを出力（ヘッダ・メトリクス除く）"""
    lines: list[str] = []
    skip = skip_replied_ids or set()
    mm = media_map or {}

    # リプライ先（チェーン内のものはスキップ）
    for ref in tweet.get("referenced_tweets", []):
        if ref["type"] == "replied_to" and ref["id"] in ref_map and ref["id"] not in skip:
            lines.extend(_format_quoted(ref_map[ref["id"]], ref_map, media_map=mm))
            lines.append("")

    # article: タイトル + 本文 + カバー画像
    article = tweet.get("article")
    if article:
        title = article.get("title", "")
        if title:
            lines.append(f"**{_sanitize_md_link_text(title)}**")
            lines.append("")
        cover_key = article.get("cover_media")
        if cover_key:
            path = mm.get(cover_key)
            if path:
                lines.append(f"![]({path})")
                lines.append("")
        plain_text = article.get("plain_text", "")
        if plain_text:
            lines.append(plain_text)
            lines.append("")
        return lines

    # note_tweet: 長文投稿は全文を使用
    note = tweet.get("note_tweet")
    if note:
        entities = note.get("entities", tweet.get("entities", {}))
        text = _expand_urls(note.get("text", tweet["text"]), entities)
    else:
        entities = tweet.get("entities", {})
        text = _expand_urls(tweet["text"], entities)
    lines.append(text)
    lines.append("")

    # メディア埋め込み
    lines.extend(_format_media(tweet, mm))

    # 引用RT
    for ref in tweet.get("referenced_tweets", []):
        if ref["type"] == "quoted" and ref["id"] in ref_map:
            lines.extend(_format_quoted(ref_map[ref["id"]], ref_map, media_map=mm))
            lines.append("")

    return lines


def format_tweet(
    tweet: dict,
    username: str,
    ref_map: dict[str, dict],
    media_map: dict[str, str] | None = None,
) -> str:
    dt_jst = _parse_dt(tweet["created_at"])
    heading = dt_jst.strftime(config.HEADING_FORMAT)
    is_rt = _is_plain_retweet(tweet)

    tweet_url = f"https://x.com/{username}/status/{tweet['id']}"

    lines: list[str] = []
    lines.append(f"## [{heading}]({tweet_url})")
    lines.append("")

    if is_rt:
        for ref in tweet.get("referenced_tweets", []):
            if ref["type"] == "retweeted" and ref["id"] in ref_map:
                lines.extend(
                    _format_quoted(ref_map[ref["id"]], ref_map, media_map=media_map)
                )
                lines.append("")
    else:
        lines.extend(_format_tweet_body(tweet, ref_map, media_map=media_map))
        lines.extend(_format_metrics([tweet]))

    return "\n".join(lines)


def format_thread(
    chain: list[dict],
    username: str,
    ref_map: dict[str, dict],
    media_map: dict[str, str] | None = None,
) -> str:
    """自己リプライチェーンを一連の流れとして出力"""
    first = chain[0]
    dt_jst = _parse_dt(first["created_at"])
    heading = dt_jst.strftime(config.HEADING_FORMAT)
    tweet_url = f"https://x.com/{username}/status/{first['id']}"

    chain_ids = {t["id"] for t in chain}

    lines: list[str] = []
    lines.append(f"## [{heading}]({tweet_url})")
    lines.append("")

    for tweet in chain:
        lines.extend(
            _format_tweet_body(
                tweet, ref_map, media_map=media_map, skip_replied_ids=chain_ids,
            )
        )

    lines.extend(_format_metrics(chain))

    return "\n".join(lines)


_COST_PER_READ = 0.005  # Pay-Per-Use: $0.005/tweet


def _format_analytics(tweets: list[dict]) -> str:
    own_tweets = [t for t in tweets if not _is_plain_retweet(t)]
    total_like = 0
    total_rt = 0
    total_reply = 0
    total_imp = 0
    for tweet in own_tweets:
        m = tweet.get("public_metrics", {})
        total_like += m.get("like_count", 0)
        total_rt += m.get("retweet_count", 0)
        total_reply += m.get("reply_count", 0)
        total_imp += m.get("impression_count", 0)

    cost = len(tweets) * _COST_PER_READ

    lines: list[str] = []
    lines.append("## Analytics")
    lines.append("")
    lines.append("| Posts | Like | RT | Reply | Imp | Cost |")
    lines.append("|------:|-----:|---:|------:|----:|-----:|")
    lines.append(
        f"| {len(own_tweets)} | {total_like} | {total_rt} | {total_reply} | {total_imp} | ${cost:.3f} |"
    )
    return "\n".join(lines)


def format_day(
    date_str: str,
    tweets: list[dict],
    username: str,
    ref_map: dict[str, dict],
    media_map: dict[str, str] | None = None,
) -> str:
    chain_heads, suppressed = _build_self_reply_chains(tweets)

    lines: list[str] = []

    lines.append("---")
    lines.append(f"date: {date_str}")
    lines.append("type: x-posts")
    lines.append("---")
    lines.append("")
    lines.append(_format_analytics(tweets))
    lines.append("")

    for tweet in tweets:
        if tweet["id"] in suppressed:
            continue
        lines.append("---")
        lines.append("")
        if tweet["id"] in chain_heads:
            lines.append(
                format_thread(chain_heads[tweet["id"]], username, ref_map, media_map)
            )
        else:
            lines.append(format_tweet(tweet, username, ref_map, media_map))
        lines.append("")

    return "\n".join(lines)


def _filename_for_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime(config.FILENAME_FORMAT)


def write_markdown_files(
    tweets: list[dict],
    includes: dict,
    output_dir: Path,
    username: str,
    media_map: dict[str, str] | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    ref_map = _build_ref_map(includes)
    groups = group_tweets_by_date(tweets)
    written_files: list[Path] = []

    for date_str in sorted(groups.keys()):
        content = format_day(date_str, groups[date_str], username, ref_map, media_map)
        filename = _filename_for_date(date_str)
        file_path = output_dir / f"{filename}.md"
        file_path.write_text(content, encoding="utf-8")
        written_files.append(file_path)

    return written_files
