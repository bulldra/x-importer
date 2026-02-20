# x-importer

X (Twitter) の自分の投稿を取得して Obsidian に Markdown 保存するバッチツール。
OAuth 1.0a 認証で X API v2 から投稿を取得し、日付別の Markdown ファイルとして出力する。
cron 等での自動実行に適した構成。

## 技術スタック

| 項目 | 技術 |
|------|------|
| 言語 | Python 3.11+ |
| パッケージ管理 | uv |
| X API クライアント | tweepy 4.14.0+ |
| 認証方式 | OAuth 1.0a |
| API エンドポイント | `GET /2/users/:id/tweets` (User Timeline) |
| 環境変数管理 | python-dotenv 1.0.0+ |
| テスト | pytest 9.0.2+ |
| 型チェック | mypy 1.19.1+ |

## 使い方

```bash
uv run python -m x_importer              # 前日1日分
uv run python -m x_importer 2026-02-19   # 指定日の1日分
uv run python -m x_importer 2026-02-15 --end 2026-02-20  # 期間指定
uv run python -m x_importer --refresh    # キャッシュを無視して再取得
```

### CLI 引数

| 引数 | 必須 | 説明 |
|------|------|------|
| `date` | 省略可 | 取得開始日 (YYYY-MM-DD, JST)。省略時は前日 |
| `--end` | 省略可 | 取得終了日 (YYYY-MM-DD, JST)。省略時は date + 1日 |
| `--refresh` | 省略可 | キャッシュを無視して API から再取得 |

日付は JST (Asia/Tokyo) で解釈され、API リクエスト時に UTC に変換される。

## モジュール構成

```
src/x_importer/
├── __main__.py      # エントリポイント (python -m x_importer)
├── main.py          # CLI 引数解析・メインワークフロー
├── config.py        # 環境変数の読み込み・バリデーション
├── client.py        # X API クライアント (tweepy ラッパー)
├── formatter.py     # Markdown フォーマッタ
├── cache.py         # JSON キャッシュ
└── url_resolver.py  # URL タイトル取得 (SSRF 対策付き)
```

### main.py - メインワークフロー

1. CLI 引数を解析し、取得期間を JST → UTC に変換
2. `config.validate()` で環境変数と出力先を検証
3. キャッシュを確認（`--refresh` 時はスキップ）
4. キャッシュミス時に X API からツイートを取得
5. URL タイトルを解決（未取得分のみ）
6. キャッシュを保存
7. Markdown ファイルを出力
8. API 使用量と推定コスト ($0.005/tweet) を表示

### config.py - 設定管理

`.env` から以下の環境変数を読み込む。

| 変数名 | 必須 | デフォルト | 説明 |
|--------|------|-----------|------|
| `X_API_KEY` | Yes | - | API Key (Consumer Key) |
| `X_API_SECRET` | Yes | - | API Key Secret (Consumer Secret) |
| `X_ACCESS_TOKEN` | Yes | - | Access Token |
| `X_ACCESS_TOKEN_SECRET` | Yes | - | Access Token Secret |
| `OBSIDIAN_VAULT_PATH` | Yes | - | Obsidian Vault のパス |
| `OBSIDIAN_OUTPUT_DIR` | No | `x-posts` | Vault 内の出力ディレクトリ |
| `FILENAME_FORMAT` | No | `x-post-%Y-%m-%d` | ファイル名のフォーマット |
| `HEADING_FORMAT` | No | `%Y-%m-%d %H:%M` | 見出しの日時フォーマット |

`validate()` で必須変数の存在と `OBSIDIAN_VAULT_PATH` のディレクトリ存在を検証する。

### client.py - X API クライアント

- `create_client()`: OAuth 1.0a で tweepy.Client を初期化
- `get_me()`: 認証ユーザー情報 (`UserInfo`) を取得
- `fetch_user_tweets()`: ページネーション対応のツイート取得 (`FetchResult`)
  - `tweet_fields`: created_at, public_metrics, entities, referenced_tweets, author_id
  - `expansions`: referenced_tweets.id, referenced_tweets.id.author_id
  - 1リクエストあたり最大 100 件、next_token で全件取得
- `result_to_cache_dict()` / `result_from_cache_dict()`: キャッシュ用シリアライズ

### formatter.py - Markdown フォーマッタ

- `group_tweets_by_date()`: ツイートを JST 日付でグルーピング
- `format_tweet()`: 個別ツイートの Markdown 変換
- `format_thread()`: 自己リプライチェーンを一連のスレッドとして出力
- `format_day()`: 日次 Markdown（front matter + analytics + 全ツイート）
- `write_markdown_files()`: 日付別ファイルへの書き出し

内部処理:
- `_build_self_reply_chains()`: 自己リプライチェーンを検出し、スレッドとしてまとめる
- `_format_quoted()`: 引用RT・リプライ先を再帰展開（最大3段）
- `_expand_urls()`: t.co URL を展開 URL に置換し、タイトル付きリンクに変換
- `_is_plain_retweet()`: 純粋な RT を判定（本文なし・メトリクスなしで表示）
- `_format_metrics()`: Like / RT / Reply / Impression をテーブル出力
- `_format_analytics()`: 日次サマリ（RT 除く自身の投稿を集計）

### cache.py - JSON キャッシュ

- 保存先: `OBSIDIAN_VAULT_PATH/OBSIDIAN_OUTPUT_DIR/.cache/`
- ファイル名: `YYYYMMDD_YYYYMMDD.json`（取得期間の開始日_終了日）
- キャッシュ構造の検証: tweets 配列の存在、各ツイートの id/text フィールドを確認
- `--refresh` フラグでキャッシュを無視して API から再取得可能

### url_resolver.py - URL タイトル解決

- ツイート内の t.co URL に対して展開先ページの `<title>` タグを取得
- X/Twitter 自身の URL はスキップ
- SSRF 対策: プライベート IP・ループバック・リンクローカルアドレスをブロック
- タイムアウト: 5秒、リダイレクト上限: 5回
- 取得済みタイトルはスキップ（キャッシュと連携して重複取得を回避）

## 出力形式

`OBSIDIAN_VAULT_PATH/OBSIDIAN_OUTPUT_DIR/<FILENAME_FORMAT>.md` に日付別で出力。

```markdown
---
date: 2026-02-21
type: x-posts
---

## Analytics

| Posts | Like | RT | Reply | Imp |
|------:|-----:|---:|------:|----:|
| 5 | 23 | 4 | 2 | 1500 |

---

## [2026-02-21 14:30](https://x.com/username/status/xxxxx)

投稿本文テキスト

[ページタイトル](https://example.com/article)

| Like | RT | Reply | Imp |
|-----:|---:|------:|----:|
| 5 | 2 | 1 | 120 |

---

## [2026-02-21 15:00](https://x.com/username/status/yyyyy)

スレッドの1つ目

スレッドの2つ目

| Like | RT | Reply | Imp |
|-----:|---:|------:|----:|
| 10 | 3 | 0 | 500 |
```

### 出力の特徴

- **YAML front matter**: `date` と `type: x-posts` を付与
- **Analytics セクション**: RT を除いた自身の投稿の日次集計
- **見出しリンク**: 各ツイートの見出しが X の投稿 URL へのリンク
- **URL 展開**: t.co 短縮 URL を展開し、ページタイトル付きの Markdown リンクに変換
- **引用 RT**: blockquote で再帰展開（最大3段）
- **リプライ先**: blockquote で表示（著者名付き）
- **自己リプライチェーン**: スレッドとして1つのセクションにまとめて出力
- **純粋な RT**: 引用のみ表示（メトリクスなし）
- **個別メトリクス**: 各ツイート・スレッドに Like / RT / Reply / Impression テーブル

## セットアップ

### 1. X API の準備

#### API プラン

| プラン | 月額 | Tweet 読み取り | 備考 |
|--------|------|---------------|------|
| Free | $0 | 100件/月 | 読み取りは実質不可 |
| **Basic** | **$200** | **15,000件/月** | **本ツール推奨** |
| Pro | $5,000 | 1,000,000件/月 | 大規模利用向け |

Free プランでは読み取りが月100件に制限されており実用不可。**Basic 以上が必須**。

#### Developer アカウント作成

1. https://developer.x.com/ に X アカウントでログイン
2. 「Sign up」からサインアップ
3. 利用目的を英語で記入（例: "I plan to use the X API to retrieve my own tweets and archive them for personal use."）
4. 審査・承認（通常 5〜10 分）

#### プロジェクト・App の作成

1. Dashboard → Projects & Apps → 「+ Create Project」
2. プロジェクト名（例: `x-importer`）・用途・説明を入力
3. プロジェクト内で「+ Create App」→ App 名を入力
4. **Products セクションから Basic プランにアップグレード**

#### OAuth 1.0a の設定

1. App → Settings → User authentication settings → 「Set up」
2. 以下を設定:
   - **App permissions**: 「Read」を選択
   - **Type of App**: 「Web App, Automated App or Bot」を選択
   - **Callback URI**: `https://example.com/callback`（ダミーで可）
   - **Website URL**: 自分の X プロフィール URL 等
3. 「Save」

**注意**: App permissions を後から変更した場合、Access Token の再生成が必要。

#### Keys and Tokens の取得

App → Keys and tokens タブで以下を取得:

| .env の変数名 | Developer Portal での表示名 | 取得ボタン |
|--------------|---------------------------|-----------|
| `X_API_KEY` | API Key (Consumer Key) | Consumer Keys → Regenerate |
| `X_API_SECRET` | API Key Secret (Consumer Secret) | Consumer Keys → Regenerate |
| `X_ACCESS_TOKEN` | Access Token | Authentication Tokens → Generate |
| `X_ACCESS_TOKEN_SECRET` | Access Token Secret | Authentication Tokens → Generate |

全て**一度だけしか表示されない**ため、即座に保存すること。

### 2. 環境設定

```bash
cp .env.example .env
```

`.env` を編集:

```env
X_API_KEY=取得した API Key
X_API_SECRET=取得した API Key Secret
X_ACCESS_TOKEN=取得した Access Token
X_ACCESS_TOKEN_SECRET=取得した Access Token Secret
OBSIDIAN_VAULT_PATH=/path/to/your/obsidian/vault
OBSIDIAN_OUTPUT_DIR=x-posts
```

### 3. 依存関係インストール

```bash
uv sync
```

## 開発

```bash
# テスト実行
uv run pytest

# 型チェック
uv run mypy src/

# リント
uv run ruff check src/ tests/
```

## 参考 URL

- X Developer Portal: https://developer.x.com/
- Developer Dashboard: https://developer.x.com/en/portal/dashboard
- OAuth 1.0a ドキュメント: https://developer.x.com/en/docs/authentication/oauth-1-0a
- プラン・料金: https://developer.x.com/en/products
