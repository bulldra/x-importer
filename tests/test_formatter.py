from pathlib import Path

from x_importer.formatter import (
    _build_ref_map,
    _build_self_reply_chains,
    _expand_urls,
    _format_analytics,
    _format_media,
    _format_quoted,
    _format_tweet_body,
    _is_plain_retweet,
    _sanitize_md_link_text,
    format_day,
    format_thread,
    format_tweet,
    group_tweets_by_date,
    write_markdown_files,
)

from .conftest import make_tweet


class TestSanitizeMdLinkText:
    def test_removes_brackets(self):
        assert _sanitize_md_link_text("a]( evil") == "a( evil"

    def test_removes_both_brackets(self):
        assert _sanitize_md_link_text("[link]") == "link"

    def test_safe_text_unchanged(self):
        assert _sanitize_md_link_text("Normal Title") == "Normal Title"


class TestExpandUrls:
    def test_replaces_tco_url(self):
        text = "見て https://t.co/abc"
        entities = {
            "urls": [{"url": "https://t.co/abc", "expanded_url": "https://example.com"}]
        }
        assert _expand_urls(text, entities) == "見て https://example.com"

    def test_no_entities(self):
        assert _expand_urls("そのまま", {}) == "そのまま"

    def test_title_with_brackets_sanitized(self):
        text = "見て https://t.co/abc"
        entities = {
            "urls": [
                {
                    "url": "https://t.co/abc",
                    "expanded_url": "https://example.com",
                    "title": "Evil](http://evil.com) [click",
                }
            ]
        }
        result = _expand_urls(text, entities)
        assert "](http://evil.com)" not in result
        assert "[Evil(http://evil.com) click](https://example.com)" in result

    def test_multiple_urls(self):
        text = "A https://t.co/1 B https://t.co/2"
        entities = {
            "urls": [
                {"url": "https://t.co/1", "expanded_url": "https://a.com"},
                {"url": "https://t.co/2", "expanded_url": "https://b.com"},
            ]
        }
        result = _expand_urls(text, entities)
        assert "https://a.com" in result
        assert "https://b.com" in result


class TestBuildRefMap:
    def test_maps_tweet_id_and_author(self, sample_includes):
        ref_map = _build_ref_map(sample_includes)
        assert "999" in ref_map
        assert ref_map["999"]["_author_username"] == "other_user"
        assert "888" in ref_map
        assert ref_map["888"]["_author_username"] == "someone"

    def test_empty_includes(self):
        assert _build_ref_map({}) == {}


class TestGroupTweetsByDate:
    def test_groups_by_jst_date(self):
        tweets = [
            make_tweet(id="1", created_at="2026-02-20T14:00:00+00:00"),  # JST 23:00
            make_tweet(id="2", created_at="2026-02-20T15:30:00+00:00"),  # JST 2/21 00:30
            make_tweet(id="3", created_at="2026-02-20T10:00:00+00:00"),  # JST 19:00
        ]
        groups = group_tweets_by_date(tweets)
        assert "2026-02-20" in groups
        assert "2026-02-21" in groups
        assert len(groups["2026-02-20"]) == 2
        assert len(groups["2026-02-21"]) == 1

    def test_sorted_chronological_within_date(self):
        tweets = [
            make_tweet(id="1", created_at="2026-02-20T01:00:00+00:00"),
            make_tweet(id="2", created_at="2026-02-20T05:00:00+00:00"),
        ]
        groups = group_tweets_by_date(tweets)
        date_tweets = groups["2026-02-20"]
        assert date_tweets[0]["id"] == "1"
        assert date_tweets[1]["id"] == "2"


class TestIsPlainRetweet:
    def test_plain_retweet(self, sample_retweet):
        assert _is_plain_retweet(sample_retweet) is True

    def test_quote_tweet(self, sample_quote_tweet):
        assert _is_plain_retweet(sample_quote_tweet) is False

    def test_normal_tweet(self, sample_tweet):
        assert _is_plain_retweet(sample_tweet) is False


class TestFormatQuoted:
    def test_nested_quote(self):
        ref_map = {
            "B": {
                "id": "B",
                "text": "Bの本文",
                "_author_username": "user_b",
                "referenced_tweets": [{"type": "quoted", "id": "C"}],
            },
            "C": {
                "id": "C",
                "text": "Cの本文",
                "_author_username": "user_c",
            },
        }
        lines = _format_quoted(ref_map["B"], ref_map)
        result = "\n".join(lines)
        assert "> @user_b:" in result
        assert "> Bの本文" in result
        assert "> > @user_c:" in result
        assert "> > Cの本文" in result

    def test_depth_limit(self):
        ref_map = {
            "A": {
                "id": "A",
                "text": "depth1",
                "_author_username": "u1",
                "referenced_tweets": [{"type": "quoted", "id": "B"}],
            },
            "B": {
                "id": "B",
                "text": "depth2",
                "_author_username": "u2",
                "referenced_tweets": [{"type": "quoted", "id": "C"}],
            },
            "C": {
                "id": "C",
                "text": "depth3",
                "_author_username": "u3",
                "referenced_tweets": [{"type": "quoted", "id": "D"}],
            },
            "D": {
                "id": "D",
                "text": "depth4",
                "_author_username": "u4",
                "referenced_tweets": [{"type": "quoted", "id": "E"}],
            },
            "E": {
                "id": "E",
                "text": "depth5",
                "_author_username": "u5",
                "referenced_tweets": [{"type": "quoted", "id": "F"}],
            },
            "F": {
                "id": "F",
                "text": "depth6_should_not_appear",
                "_author_username": "u6",
            },
        }
        lines = _format_quoted(ref_map["A"], ref_map)
        result = "\n".join(lines)
        assert "> > > > > depth5" in result
        assert "depth6_should_not_appear" not in result

    def test_missing_nested_ref(self):
        ref_map = {
            "A": {
                "id": "A",
                "text": "本文",
                "_author_username": "user_a",
                "referenced_tweets": [{"type": "quoted", "id": "MISSING"}],
            },
        }
        lines = _format_quoted(ref_map["A"], ref_map)
        result = "\n".join(lines)
        assert "> @user_a:" in result
        assert "> 本文" in result


class TestBuildSelfReplyChains:
    def test_detects_chain(self):
        tweets = [
            make_tweet(id="A", created_at="2026-02-20T01:00:00+00:00"),
            make_tweet(
                id="B",
                created_at="2026-02-20T02:00:00+00:00",
                referenced_tweets=[{"type": "replied_to", "id": "A"}],
            ),
            make_tweet(
                id="C",
                created_at="2026-02-20T03:00:00+00:00",
                referenced_tweets=[{"type": "replied_to", "id": "B"}],
            ),
        ]
        heads, suppressed = _build_self_reply_chains(tweets)
        assert "A" in heads
        assert len(heads["A"]) == 3
        assert heads["A"][0]["id"] == "A"
        assert heads["A"][2]["id"] == "C"
        assert suppressed == {"B", "C"}

    def test_standalone_not_chained(self):
        tweets = [
            make_tweet(id="X", created_at="2026-02-20T01:00:00+00:00"),
            make_tweet(id="Y", created_at="2026-02-20T02:00:00+00:00"),
        ]
        heads, suppressed = _build_self_reply_chains(tweets)
        assert heads == {}
        assert suppressed == set()

    def test_reply_to_external_not_chained(self):
        tweets = [
            make_tweet(
                id="A",
                referenced_tweets=[{"type": "replied_to", "id": "EXTERNAL"}],
            ),
        ]
        heads, suppressed = _build_self_reply_chains(tweets)
        assert heads == {}
        assert suppressed == set()


class TestFormatThread:
    def test_shows_all_in_order(self):
        chain = [
            make_tweet(id="A", text="最初", created_at="2026-02-20T01:00:00+00:00"),
            make_tweet(id="B", text="次に", created_at="2026-02-20T02:00:00+00:00",
                       referenced_tweets=[{"type": "replied_to", "id": "A"}]),
            make_tweet(id="C", text="最後", created_at="2026-02-20T03:00:00+00:00",
                       referenced_tweets=[{"type": "replied_to", "id": "B"}]),
        ]
        result = format_thread(chain, "testuser", {})
        assert "最初" in result
        assert "次に" in result
        assert "最後" in result
        # 時系列順
        assert result.index("最初") < result.index("次に") < result.index("最後")

    def test_heading_uses_first_tweet(self):
        chain = [
            make_tweet(id="A", created_at="2026-02-20T01:00:00+00:00"),
            make_tweet(id="B", created_at="2026-02-20T02:00:00+00:00",
                       referenced_tweets=[{"type": "replied_to", "id": "A"}]),
        ]
        result = format_thread(chain, "testuser", {})
        assert "](https://x.com/testuser/status/A)" in result

    def test_no_self_reply_blockquote(self):
        chain = [
            make_tweet(id="A", text="親", created_at="2026-02-20T01:00:00+00:00"),
            make_tweet(id="B", text="子", created_at="2026-02-20T02:00:00+00:00",
                       referenced_tweets=[{"type": "replied_to", "id": "A"}]),
        ]
        # チェーン内IDを ref_map にも入れてみる
        ref_map = {"A": {"id": "A", "text": "親", "_author_username": "testuser"}}
        result = format_thread(chain, "testuser", ref_map)
        # 自己リプライは引用形式にならない
        assert "> @testuser:" not in result
        assert "親" in result
        assert "子" in result

    def test_aggregated_metrics(self):
        chain = [
            make_tweet(id="A", like=3, rt=1, impression=50,
                       created_at="2026-02-20T01:00:00+00:00"),
            make_tweet(id="B", like=7, rt=2, impression=100,
                       created_at="2026-02-20T02:00:00+00:00",
                       referenced_tweets=[{"type": "replied_to", "id": "A"}]),
        ]
        result = format_thread(chain, "testuser", {})
        assert "| 10 | 3 |" in result  # like=10, rt=3

    def test_external_reply_shown_as_blockquote(self):
        chain = [
            make_tweet(id="A", text="リプライ",
                       created_at="2026-02-20T01:00:00+00:00",
                       referenced_tweets=[{"type": "replied_to", "id": "EXT"}]),
            make_tweet(id="B", text="続き",
                       created_at="2026-02-20T02:00:00+00:00",
                       referenced_tweets=[{"type": "replied_to", "id": "A"}]),
        ]
        ref_map = {"EXT": {"id": "EXT", "text": "外部ツイート", "_author_username": "other"}}
        result = format_thread(chain, "testuser", ref_map)
        assert "> @other:" in result
        assert "> 外部ツイート" in result


class TestFormatTweet:
    def test_normal_tweet_has_metrics(self, sample_tweet):
        result = format_tweet(sample_tweet, "testuser", {})
        assert "| Like | RT | Reply | Imp |" in result
        assert "| 5 | 2 | 1 | 100 |" in result

    def test_heading_has_permalink(self, sample_tweet):
        result = format_tweet(sample_tweet, "testuser", {})
        assert "## [" in result
        assert "](https://x.com/testuser/status/123456)" in result

    def test_url_expansion(self, sample_tweet_with_url):
        result = format_tweet(sample_tweet_with_url, "testuser", {})
        assert "https://example.com/full" in result
        assert "https://t.co/abc123" not in result

    def test_plain_retweet_no_metrics(self, sample_retweet, sample_includes):
        ref_map = _build_ref_map(sample_includes)
        result = format_tweet(sample_retweet, "testuser", ref_map)
        assert "| Like |" not in result
        assert "> @other_user:" in result
        assert "> 元のツイート内容" in result

    def test_reply_shows_parent_as_blockquote(self):
        ref_map = {
            "parent_1": {
                "id": "parent_1",
                "text": "親ツイートの内容",
                "_author_username": "parent_user",
            },
        }
        reply = make_tweet(
            id="reply_1",
            text="これはリプライです",
            referenced_tweets=[{"type": "replied_to", "id": "parent_1"}],
        )
        result = format_tweet(reply, "testuser", ref_map)
        assert "> @parent_user:" in result
        assert "> 親ツイートの内容" in result
        parent_pos = result.index("> 親ツイートの内容")
        reply_pos = result.index("これはリプライです")
        assert parent_pos < reply_pos

    def test_quote_tweet_shows_quoted(self, sample_quote_tweet, sample_includes):
        ref_map = _build_ref_map(sample_includes)
        result = format_tweet(sample_quote_tweet, "testuser", ref_map)
        assert "> @someone:" in result
        assert "> 引用元の本文" in result
        assert "| Like |" in result


class TestFormatDay:
    def test_chain_merged_into_single_entry(self):
        tweets = [
            make_tweet(id="A", text="最初", created_at="2026-02-20T01:00:00+00:00"),
            make_tweet(id="B", text="次に", created_at="2026-02-20T02:00:00+00:00",
                       referenced_tweets=[{"type": "replied_to", "id": "A"}]),
            make_tweet(id="C", text="最後", created_at="2026-02-20T03:00:00+00:00",
                       referenced_tweets=[{"type": "replied_to", "id": "B"}]),
        ]
        result = format_day("2026-02-20", tweets, "testuser", {})
        # A, B, C が1回ずつしか出ない
        assert result.count("最初") == 1
        assert result.count("次に") == 1
        assert result.count("最後") == 1
        # ## 見出しは1つだけ
        assert result.count("## [") == 1

    def test_has_frontmatter(self, sample_tweet):
        result = format_day("2026-02-20", [sample_tweet], "testuser", {})
        assert "---\ndate: 2026-02-20\ntype: x-posts\n---" in result

    def test_no_h1_heading(self, sample_tweet):
        result = format_day("2026-02-20", [sample_tweet], "testuser", {})
        assert "\n# " not in result


class TestFormatAnalytics:
    def test_excludes_plain_retweets(self, sample_tweet, sample_retweet):
        tweets = [sample_tweet, sample_retweet]
        result = _format_analytics(tweets)
        assert "| 1 |" in result  # Posts = 1 (RT除外)
        assert "## Analytics" in result

    def test_sums_metrics(self):
        tweets = [
            make_tweet(like=3, rt=1, reply=2, impression=50),
            make_tweet(like=7, rt=4, reply=0, impression=150),
        ]
        result = _format_analytics(tweets)
        assert "| 2 | 10 | 5 | 2 | 200 |" in result

    def test_cost_column(self):
        tweets = [
            make_tweet(like=1, rt=0, reply=0, impression=10),
            make_tweet(like=2, rt=0, reply=0, impression=20),
        ]
        result = _format_analytics(tweets)
        assert "| Cost |" in result
        assert "$0.010" in result  # 2 tweets * $0.005


class TestFormatMedia:
    def test_embeds_image(self):
        tweet = make_tweet(attachments={"media_keys": ["mk1"]})
        media_map = {"mk1": "media/mk1.jpg"}
        lines = _format_media(tweet, media_map)
        assert "![](media/mk1.jpg)" in lines

    def test_no_attachments(self):
        tweet = make_tweet()
        lines = _format_media(tweet, {"mk1": "media/mk1.jpg"})
        assert lines == []

    def test_missing_key_in_map(self):
        tweet = make_tweet(attachments={"media_keys": ["mk_missing"]})
        lines = _format_media(tweet, {})
        assert lines == []

    def test_multiple_media(self):
        tweet = make_tweet(attachments={"media_keys": ["mk1", "mk2"]})
        media_map = {"mk1": "media/mk1.jpg", "mk2": "media/mk2.mp4"}
        lines = _format_media(tweet, media_map)
        assert "![](media/mk1.jpg)" in lines
        assert "![](media/mk2.mp4)" in lines


class TestFormatTweetWithMedia:
    def test_media_embedded_in_output(self):
        tweet = make_tweet(
            text="写真付き投稿",
            attachments={"media_keys": ["mk1"]},
        )
        media_map = {"mk1": "media/mk1.jpg"}
        result = format_tweet(tweet, "testuser", {}, media_map=media_map)
        assert "![](media/mk1.jpg)" in result
        assert "写真付き投稿" in result

    def test_no_media_map_still_works(self):
        tweet = make_tweet(text="普通の投稿")
        result = format_tweet(tweet, "testuser", {})
        assert "普通の投稿" in result


class TestQuotedWithMedia:
    def test_media_in_quoted_tweet(self):
        ref_map = {
            "Q1": {
                "id": "Q1",
                "text": "引用元",
                "_author_username": "other",
                "attachments": {"media_keys": ["mk_q"]},
            },
        }
        media_map = {"mk_q": "media/mk_q.jpg"}
        lines = _format_quoted(ref_map["Q1"], ref_map, media_map=media_map)
        result = "\n".join(lines)
        assert "> ![](media/mk_q.jpg)" in result

    def test_no_media_in_quoted(self):
        ref_map = {
            "Q1": {
                "id": "Q1",
                "text": "引用元",
                "_author_username": "other",
            },
        }
        lines = _format_quoted(ref_map["Q1"], ref_map)
        result = "\n".join(lines)
        assert "![](" not in result


class TestQuotedArticle:
    def test_article_in_quoted_tweet(self):
        ref_map = {
            "A1": {
                "id": "A1",
                "text": "https://t.co/xxx",
                "_author_username": "writer",
                "article": {
                    "title": "引用記事タイトル",
                    "plain_text": "引用記事の本文",
                    "cover_media": "mk_cover",
                },
            },
        }
        media_map = {"mk_cover": "media/mk_cover.jpg"}
        lines = _format_quoted(ref_map["A1"], ref_map, media_map=media_map)
        result = "\n".join(lines)
        assert "> @writer:" in result
        assert "> **引用記事タイトル**" in result
        assert "> ![](media/mk_cover.jpg)" in result
        assert "> 引用記事の本文" in result

    def test_note_tweet_in_quoted(self):
        ref_map = {
            "N1": {
                "id": "N1",
                "text": "短縮テキスト",
                "_author_username": "author",
                "note_tweet": {
                    "text": "これは長文の全文テキストです。" * 5,
                },
            },
        }
        lines = _format_quoted(ref_map["N1"], ref_map)
        result = "\n".join(lines)
        assert "短縮テキスト" not in result
        assert "> これは長文の全文テキストです。" in result


class TestArticleFormat:
    def test_article_shows_title_and_text(self):
        tweet = make_tweet(text="https://t.co/xxx")
        tweet["article"] = {
            "title": "記事タイトル",
            "plain_text": "記事の本文テキスト",
            "cover_media": "mk_cover",
        }
        media_map = {"mk_cover": "media/mk_cover.jpg"}
        lines = _format_tweet_body(tweet, {}, media_map=media_map)
        result = "\n".join(lines)
        assert "**記事タイトル**" in result
        assert "記事の本文テキスト" in result
        assert "![](media/mk_cover.jpg)" in result

    def test_article_without_cover(self):
        tweet = make_tweet(text="https://t.co/xxx")
        tweet["article"] = {
            "title": "タイトルのみ",
            "plain_text": "本文",
        }
        lines = _format_tweet_body(tweet, {})
        result = "\n".join(lines)
        assert "**タイトルのみ**" in result
        assert "本文" in result
        assert "![](" not in result

    def test_article_no_quoted_rt(self):
        """article はそのまま出力し、引用RT展開しない"""
        tweet = make_tweet(
            text="https://t.co/xxx",
            referenced_tweets=[{"type": "quoted", "id": "Q1"}],
        )
        tweet["article"] = {
            "title": "記事",
            "plain_text": "本文",
        }
        ref_map = {"Q1": {"id": "Q1", "text": "引用元", "_author_username": "u"}}
        lines = _format_tweet_body(tweet, ref_map)
        result = "\n".join(lines)
        assert "引用元" not in result


class TestNoteTweet:
    def test_uses_full_text(self):
        tweet = make_tweet(text="短縮テキスト…")
        tweet["note_tweet"] = {
            "text": "これは280文字を超える長文投稿の全文です。" * 10,
        }
        lines = _format_tweet_body(tweet, {})
        result = "\n".join(lines)
        assert "短縮テキスト" not in result
        assert "これは280文字を超える長文投稿の全文です。" in result

    def test_note_tweet_entities(self):
        tweet = make_tweet(text="短縮 https://t.co/abc")
        tweet["note_tweet"] = {
            "text": "全文 https://t.co/abc を参照",
            "entities": {
                "urls": [
                    {"url": "https://t.co/abc", "expanded_url": "https://example.com"}
                ]
            },
        }
        lines = _format_tweet_body(tweet, {})
        result = "\n".join(lines)
        assert "https://example.com" in result
        assert "https://t.co/abc" not in result

    def test_no_note_tweet_uses_normal_text(self):
        tweet = make_tweet(text="通常テキスト")
        lines = _format_tweet_body(tweet, {})
        result = "\n".join(lines)
        assert "通常テキスト" in result


class TestWriteMarkdownFiles:
    def test_creates_files_with_correct_name(self, tmp_path, sample_tweet):
        tweets = [sample_tweet]
        files = write_markdown_files(tweets, {}, tmp_path, "testuser")
        assert len(files) == 1
        assert files[0].name == "x-post-2026-02-20.md"
        assert files[0].exists()

    def test_splits_by_date(self, tmp_path):
        tweets = [
            make_tweet(id="1", created_at="2026-02-20T10:00:00+00:00"),
            make_tweet(id="2", created_at="2026-02-21T10:00:00+00:00"),
        ]
        files = write_markdown_files(tweets, {}, tmp_path, "testuser")
        assert len(files) == 2
        names = {f.name for f in files}
        assert "x-post-2026-02-20.md" in names
        assert "x-post-2026-02-21.md" in names
