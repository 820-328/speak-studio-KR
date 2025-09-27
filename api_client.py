# api_client.py
# -*- coding: utf-8 -*-
"""
OpenAI Chat Completions を 1 回呼ぶラッパ。
- utils.get_openai_api_key() / get_model_name() で安全にキーとモデル名を取得
- 失敗時（キー未設定や SDK 未導入、呼び出し例外）は None を返し、UI 側でフォールバック
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Iterable, TYPE_CHECKING, cast

from utils import get_openai_api_key, get_model_name

# OpenAI SDK 1.x 系（未導入でも落ちないように try-import）
try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore

# 型チェック時のみ詳細型を import（実行時は不要）
if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam  # type: ignore

__all__ = ["chat"]


def _make_client():
    """
    OpenAI クライアントを生成。APIキー未取得 or SDK 未導入なら (None, key) を返す。
    返り値: (client_or_none, api_key_or_none)
    """
    api_key = get_openai_api_key()
    if not api_key or OpenAI is None:
        return None, api_key
    try:
        client = OpenAI(api_key=api_key)  # type: ignore[call-arg]
        return client, api_key
    except Exception:
        return None, api_key


def chat(messages: List[Dict[str, Any]], model: Optional[str] = None) -> Optional[str]:
    """
    Chat Completions を 1 回呼ぶ薄いラッパ。
    - messages: [{"role": "system"|"user"|"assistant", "content": "..."}, ...]
    - model: 未指定なら utils.get_model_name() を使用
    - 例外は握りつぶし、None を返す
    """
    client, api_key = _make_client()
    if client is None or not api_key:
        return None

    mdl = model or get_model_name()
    try:
        # Pylance/pyright 向けに期待型へキャスト（実行時には無害）
        messages_typed = cast("Iterable[ChatCompletionMessageParam]", messages)

        resp = client.chat.completions.create(  # type: ignore[reportUnknownMemberType]
            model=mdl,
            messages=messages_typed,
            temperature=0.7,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return None
