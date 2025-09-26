# api_client.py
# -*- coding: utf-8 -*-
"""
OpenAI 呼び出しの共通ラッパ
- utils.get_openai_api_key() でキー解決（st.secrets / .env / 環境変数）
- 取得できない場合は None を返し、呼び出し側がローカル簡易応答にフォールバック
- 日常会話 / ロールプレイ（β）用の薄いヘルパーも同梱

【型注釈について】
Pylance のスタブ要件に合わせて、呼び出し直前で
Iterable[ChatCompletionMessageParam] へ cast しています。
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Iterable, TYPE_CHECKING, cast

from utils import get_openai_api_key, get_model_name

# OpenAI SDK 1.x 系
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore

# 型チェック専用（実行時は import されない）
if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionMessageParam


def _make_client():
    """
    OpenAI クライアントを生成。APIキー未取得 or SDK 未導入なら None を返す。
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
    Chat Completions を 1 回呼ぶラッパ。
    - messages: [{"role": "...", "content": "..."} ...] の配列（緩い型）
    - model: 未指定なら utils.get_model_name() を使用
    - 失敗時 / APIキーなし は None を返す（例外は UI に出さない）
    """
    client, api_key = _make_client()
    if client is None or not api_key:
        return None

    model = model or get_model_name()

    try:
        # Pylance用に、期待型 Iterable[ChatCompletionMessageParam] へ明示キャスト
        messages_typed = cast("Iterable[ChatCompletionMessageParam]", messages)

        resp = client.chat.completions.create(  # type: ignore[reportUnknownMemberType]
            model=model,
            messages=messages_typed,
            temperature=0.7,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return None


# ========== 高レベルのヘルパー（各モード用） ==========

def daily_chat_reply(user_text: str) -> Optional[str]:
    """
    日常会話モード用の応答を返す。APIキー未設定なら None。
    """
    system_prompt = (
        "You are a friendly English/Japanese conversation partner. "
        "Respond briefly and clearly. If the user speaks Japanese, "
        "you may include a concise English paraphrase."
    )
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    return chat(messages)


def roleplay_reply(role_description: str, user_text: str) -> Optional[str]:
    """
    ロールプレイ（β）モード用の応答を返す。APIキー未設定なら None。
    role_description 例: 'You are a strict TOEIC coach.' など
    """
    system_prompt = (
        "You are roleplaying according to the given role. "
        "Stay in character. Keep responses short and actionable."
    )
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"Role: {role_description}"},
        {"role": "user", "content": user_text},
    ]
    return chat(messages)
