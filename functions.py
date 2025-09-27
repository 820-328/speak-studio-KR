# -*- coding: utf-8 -*-
"""
SpeakStudio functions:
- LLM呼び出し（LangChain OpenAI）
- 翻訳ユーティリティ（即時訳ON時に使用）
- STT（SpeechRecognition）
- TTS（Edge-TTS優先、無ければgTTS）、速度調整
- テキスト正規化（比較用）
"""

from __future__ import annotations
import io
import os
import re
import unicodedata
import asyncio
from typing import Optional, List, Dict, Any, Union

import constants as ct

# LLM（LangChain OpenAI）
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# STT / TTS
import speech_recognition as sr
from gtts import gTTS

# Edge-TTS は任意（あれば高品質＆速度調整）
try:
    import edge_tts  # type: ignore
    _HAS_EDGE_TTS = True
except Exception:
    _HAS_EDGE_TTS = False


def _make_llm(model: Optional[str] = None, temperature: float = 0.3):
    model = model or ct.OPENAI_MODEL
    # APIキー未設定時は失敗するので、呼び出し側でフォールバック
    return ChatOpenAI(model=model, temperature=temperature)


def _content_to_text(content: Union[str, List[Dict[str, Any]], Any]) -> str:
    """
    LangChainの AIMessage.content は str か list[dict(type=..., ...)] の場合がある。
    Pylanceの型警告を避けつつ安全に文字列へ。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                # OpenAIのツール出力等を想定。type=="text" を優先的に拾う。
                t = part.get("text")
                if isinstance(t, str):
                    texts.append(t)
                else:
                    # 念のため他タイプも文字列化
                    try:
                        texts.append(str(t) if t is not None else "")
                    except Exception:
                        pass
        return "\n".join([t for t in texts if t]).strip()
    # 不明タイプは素直に文字列化
    try:
        return str(content)
    except Exception:
        return ""


def chat_once(system_prompt: str, user_text: str, model: Optional[str] = None) -> str:
    """
    単発チャット生成。APIキー未設定時はローカル簡易応答にフォールバック。
    """
    if not os.getenv("OPENAI_API_KEY"):
        return f"(ローカル簡易応答) {user_text}"

    try:
        llm = _make_llm(model=model, temperature=0.3)
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "{u}"),
        ])
        chain = prompt | llm
        out = chain.invoke({"u": user_text})
        text = _content_to_text(getattr(out, "content", out))
        return text.strip()
    except Exception as e:
        return f"(LLMエラー) {e}"


def translate_text(text: str, target_lang_label: str = "Japanese", model: Optional[str] = None) -> str:
    """
    LLMで翻訳（即時訳用）。APIキー未設定時は原文を返す。
    """
    if not os.getenv("OPENAI_API_KEY"):
        return text

    try:
        llm = _make_llm(model=model or ct.OPENAI_MODEL_MINI, temperature=0.0)
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a precise translator. Return only the translated text without explanations."),
            ("user", "Translate to {tlang}: {src}"),
        ])
        chain = prompt | llm
        out = chain.invoke({"tlang": target_lang_label, "src": text})
        t = _content_to_text(getattr(out, "content", out))
        return t.strip()
    except Exception as e:
        return f"(翻訳エラー) {e}"


def get_lang_conf(lang_code: str) -> Dict[str, Any]:
    return ct.LANGS.get(lang_code, ct.LANGS[ct.DEFAULT_LANG])


def stt_recognize_from_audio(audio_data, lang_code: str) -> str:
    """
    SpeechRecognition(Google) でSTT。lang_codeに応じて言語切替。
    """
    conf = get_lang_conf(lang_code)
    r = sr.Recognizer()
    try:
        # Pylanceのstubに recognize_google が載っていないため、型警告を抑制
        text = r.recognize_google(audio_data, language=conf["stt"])  # type: ignore[attr-defined]
        return text
    except Exception:
        return ""


# ---------- TTS ----------
async def _edge_tts_bytes_async(text: str, voice: str, rate_pct: int) -> bytes:
    """
    Edge-TTS で音声生成（MP3）。rate_pctは -50～+50 を想定。
    """
    rate = f"{rate_pct:+d}%"
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)  # type: ignore[name-defined]
    out = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            out.write(chunk["data"])
    return out.getvalue()


def tts_synthesize(text: str, lang_code: str, rate_pct: int = 0, prefer_edge: bool = True, edge_voice: Optional[str] = None) -> bytes:
    """
    音声合成してバイトを返す（MP3推奨）。prefer_edge=True かつ Edge-TTSが利用可能ならそれを使用（速度調整可）。
    それ以外は gTTS でフォールバック（速度調整は不可）。
    """
    # Edge-TTS優先
    if prefer_edge and _HAS_EDGE_TTS:
        voices = get_lang_conf(lang_code).get("edge_voices", [])
        voice = edge_voice or (voices[0] if voices else None)
        if voice:
            try:
                return asyncio.run(_edge_tts_bytes_async(text, voice, rate_pct))
            except Exception:
                pass  # 失敗時はgTTSへフォールバック

    # gTTSフォールバック（速度調整不可）
    conf = get_lang_conf(lang_code)
    tts = gTTS(text=text, lang=conf["tts"])
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()


# ---------- 正規化（比較用） ----------
_PUNCT_RE = re.compile(r"[^\w\s\uAC00-\uD7A3]", flags=re.UNICODE)

def normalize_for_compare(s: str) -> str:
    """
    シャドーイング判定用のテキスト正規化（英語＆韓国語想定）。
    - 大文字小文字/全角半角
    - 句読点除去（ハングル範囲は保持）
    - 連続空白の単一化
    """
    s = unicodedata.normalize("NFC", s).lower().strip()
    s = _PUNCT_RE.sub("", s)
    s = re.sub(r"\s+", " ", s)
    return s
