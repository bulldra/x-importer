import argparse
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from x_importer import cache, config
from x_importer.client import (
    FetchResult,
    create_client,
    fetch_missing_media,
    fetch_user_tweets,
    get_me,
    result_from_cache_dict,
    result_to_cache_dict,
)
from x_importer.formatter import write_markdown_files
from x_importer.media import download_media_for_tweets
from x_importer.url_resolver import resolve_titles_in_tweets

JST = ZoneInfo("Asia/Tokyo")
UTC = ZoneInfo("UTC")

COST_PER_READ = 0.005  # Pay-Per-Use: $0.005/tweet

logger = logging.getLogger("x_importer")


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logger.setLevel(logging.DEBUG)

    # コンソール出力
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logger.addHandler(console)

    # ファイル出力（常に DEBUG レベル）
    log_dir = config.get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now(JST):%Y-%m-%d}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logger.addHandler(file_handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="X (Twitter) の投稿を取得して Obsidian に保存"
    )
    parser.add_argument(
        "date", nargs="?", type=str, help="取得日 (YYYY-MM-DD, JST)。省略時は前日"
    )
    parser.add_argument(
        "--end", type=str, help="終了日 (YYYY-MM-DD, JST)。date と組み合わせて期間指定"
    )
    parser.add_argument(
        "--refresh", action="store_true", help="キャッシュを無視してAPIから再取得"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="詳細ログを表示"
    )
    return parser.parse_args()


def resolve_period(args: argparse.Namespace) -> tuple[datetime, datetime]:
    today = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    if args.date:
        start = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=JST)
    else:
        start = yesterday

    if args.end:
        end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=JST)
    else:
        end = start + timedelta(days=1)

    return start.astimezone(UTC), end.astimezone(UTC)


def main() -> None:
    args = parse_args()
    config.validate()
    _setup_logging(verbose=args.verbose)

    start, end = resolve_period(args)
    start_jst = start.astimezone(JST)
    end_jst = end.astimezone(JST)
    logger.info(
        "期間: %s JST -> %s JST", f"{start_jst:%Y-%m-%d %H:%M}", f"{end_jst:%Y-%m-%d %H:%M}"
    )

    # キャッシュ確認
    result: FetchResult | None = None
    if not args.refresh:
        cached = cache.load(start, end)
        if cached:
            result = result_from_cache_dict(cached)
            logger.info("キャッシュヒット")
    else:
        logger.debug("--refresh: キャッシュをスキップ")

    # API 取得
    if result is None:
        client = create_client()
        me = get_me(client)
        logger.info("ユーザー: @%s (ID: %s)", me.username, me.id)
        logger.info("API取得中...")
        result = fetch_user_tweets(client, me.id, start, end)
        logger.debug("APIリクエスト数: %d", result.request_count)
        if result.tweets:
            cache.save(result_to_cache_dict(result))
            logger.debug("キャッシュ保存完了")
    else:
        client = create_client()
        me = get_me(client)

    if not result.tweets:
        logger.info("該当期間の投稿はありませんでした")
        return

    # URL タイトル解決
    logger.info("URLタイトル解決中...")
    resolve_titles_in_tweets(result.tweets)

    # referenced tweets のメディア補完取得
    extra = fetch_missing_media(client, result)
    if extra:
        logger.debug("メディア補完: %d リクエスト追加", extra)

    cache.save(result_to_cache_dict(result))

    # メディアダウンロード
    output_dir = config.get_output_path()
    logger.info("メディアダウンロード中...")
    media_map = download_media_for_tweets(result.tweets, result.includes, output_dir)

    # Markdown 出力
    written_files = write_markdown_files(
        result.tweets, result.includes, output_dir, me.username, media_map
    )

    # 結果ログ
    tweet_count = len(result.tweets)
    if not result.from_cache:
        cost = tweet_count * COST_PER_READ
        logger.info(
            "API推定コスト: $%.3f (%d reads x $%.3f/read)",
            cost, tweet_count, COST_PER_READ,
        )
    logger.info("取得件数: %d tweets", tweet_count)
    for f in written_files:
        logger.info("出力先: %s", f)
    logger.info("完了")
