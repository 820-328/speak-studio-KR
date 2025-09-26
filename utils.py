# utils.py
# -*- coding: utf-8 -*-
"""
OPENAI_API_KEY/OPENAI_MODEL を安全に取得するユーティリティ

優先度（ローカル想定）:
  (1) .env / 環境変数
  (2) .streamlit/secrets.toml が実在する場合のみ st.secrets

Streamlit Cloud 対応:
  Secrets で USE_ST_SECRETS="1" を設定した場合は、
  secrets.toml の実ファイルがなくても st.secrets を利用します。
"""

from __future__ import annotations
import os
from pathlib import Path

# Streamlit が無くても落ちないよう緩く import
try:
    import streamlit as st  # type: ignore
except Exception:
    st = None  # type: ignore


def _secrets_file_exists() -> bool:
    """典型パスに secrets.toml があるかだけ事前チェック（無い時は st.secrets に触れない）"""
    candidates = [
        Path(__file__).resolve().parent / ".streamlit" / "secrets.toml",  # プロジェクト同階層
        Path.cwd() / ".streamlit" / "secrets.toml",                        # 実行カレント
        Path.home() / ".streamlit" / "secrets.toml",                       # ユーザー配下
    ]
    return any(p.is_file() for p in candidates)


def _load_dotenv_silent() -> None:
    """dotenv を静かにロード（未導入でも例外にしない）"""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(override=False)
    except Exception:
        pass


def get_openai_api_key() -> str | None:
    """
    優先度:
      (1) .env / 環境変数
      (2) USE_ST_SECRETS=1 のとき or secrets.toml が実在するときのみ st.secrets
    取得できたら os.environ にも反映。
    """
    # 1) .env / 環境変数
    _load_dotenv_silent()
    key = os.getenv("OPENAI_API_KEY")
    if key:
        os.environ["OPENAI_API_KEY"] = key
        return key

    # 2) st.secrets は条件付きで参照
    use_st = os.getenv("USE_ST_SECRETS") == "1"
    if st is not None and (use_st or _secrets_file_exists()):
        try:
            key = st.secrets.get("OPENAI_API_KEY", None)  # type: ignore[attr-defined]
        except Exception:
            key = None
        if key:
            os.environ["OPENAI_API_KEY"] = key
            return key

    return None


def get_model_name(default: str = "gpt-4o-mini") -> str:
    """
    優先度:
      (1) .env / 環境変数
      (2) USE_ST_SECRETS=1 のとき or secrets.toml が実在するときのみ st.secrets
      (3) 既定値
    """
    _load_dotenv_silent()
    name = os.getenv("OPENAI_MODEL")
    if name:
        return name

    use_st = os.getenv("USE_ST_SECRETS") == "1"
    if st is not None and (use_st or _secrets_file_exists()):
        try:
            name = st.secrets.get("OPENAI_MODEL", None)  # type: ignore[attr-defined]
        except Exception:
            name = None
        if name:
            return name

    return default
