import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REQUIRED_ENV_VARS = [
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
]

# X API 認証情報
X_API_KEY: str = os.getenv("X_API_KEY", "")
X_API_SECRET: str = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN: str = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET: str = os.getenv("X_ACCESS_TOKEN_SECRET", "")

# Obsidian 出力設定
OBSIDIAN_VAULT_PATH: str = os.getenv("OBSIDIAN_VAULT_PATH", "")
OBSIDIAN_OUTPUT_DIR: str = os.getenv("OBSIDIAN_OUTPUT_DIR", "x-posts")

# フォーマット設定（strftime 形式）
FILENAME_FORMAT: str = os.getenv("FILENAME_FORMAT", "x-post-%Y-%m-%d")
HEADING_FORMAT: str = os.getenv("HEADING_FORMAT", "%Y-%m-%d %H:%M")


def get_output_path() -> Path:
    return Path(OBSIDIAN_VAULT_PATH) / OBSIDIAN_OUTPUT_DIR


def validate() -> None:
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        print(
            f"エラー: 以下の環境変数が未設定です: {', '.join(missing)}", file=sys.stderr
        )
        print(
            "  .env.example を参考に .env ファイルを作成してください。", file=sys.stderr
        )
        sys.exit(1)

    if not OBSIDIAN_VAULT_PATH:
        print("エラー: OBSIDIAN_VAULT_PATH が未設定です。", file=sys.stderr)
        sys.exit(1)

    vault = Path(OBSIDIAN_VAULT_PATH)
    if not vault.exists():
        print(f"エラー: Obsidian Vault が見つかりません: {vault}", file=sys.stderr)
        sys.exit(1)
