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
    return ChatOpenAI(model=model, temperature=temperature)


def _content_to_text(content: Union[str, List[Dict[str, Any]], Any]) -> str:
    """AIMessage.content が list の場合に安全に文字列へ変換"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                t = part.get("text")
                if isinstance(t, str):
                    texts.append(t)
                else:
                    try:
                        texts.append(str(t) if t is not None else "")
                    except Exception:
                        pass
        return "\n".join([t for t in texts if t]).strip()
    try:
        return str(content)
    except Exception:
        return ""


def chat_once(system_prompt: str, user_text: str, model: Optional[str] = None) -> str:
    """単発チャット。APIキー未設定時はローカル簡易応答へ"""
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
    """LLMで翻訳（即時訳用）。キー未設定時は原文"""
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
    """SpeechRecognition(Google) STT"""
    conf = get_lang_conf(lang_code)
    r = sr.Recognizer()
    try:
        text = r.recognize_google(audio_data, language=conf["stt"])  # type: ignore[attr-defined]
        return text
    except Exception:
        return ""


# ---------- TTS ----------
async def _edge_tts_bytes_async(text: str, voice: str, rate_pct: int) -> bytes:
    """Edge-TTS で音声生成（MP3）"""
    rate = f"{rate_pct:+d}%"
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)  # type: ignore[name-defined]
    out = io.BytesIO()
    async for chunk in communicate.stream():
        if isinstance(chunk, dict) and chunk.get("type") == "audio":
            data = chunk.get("data", b"")
            if isinstance(data, (bytes, bytearray)):
                out.write(data)
    return out.getvalue()


def tts_synthesize(text: str, lang_code: str, rate_pct: int = 0, prefer_edge: bool = True, edge_voice: Optional[str] = None) -> bytes:
    """
    音声合成（MP3バイトを返す）
    - Edge-TTS優先（速度調整可）
    - 失敗時は gTTS にフォールバック（固定速度）
    """
    if prefer_edge and _HAS_EDGE_TTS:
        voices = get_lang_conf(lang_code).get("edge_voices", [])
        voice = edge_voice or (voices[0] if voices else None)
        if voice:
            try:
                return asyncio.run(_edge_tts_bytes_async(text, voice, rate_pct))
            except Exception:
                pass
    conf = get_lang_conf(lang_code)
    tts = gTTS(text=text, lang=conf["tts"])
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()


# ---------- 正規化（比較用） ----------
_PUNCT_RE = re.compile(r"[^\w\s\uAC00-\uD7A3]", flags=re.UNICODE)

def normalize_for_compare(s: str) -> str:
    """シャドーイング比較用の簡易正規化"""
    s = unicodedata.normalize("NFC", s).lower().strip()
    s = _PUNCT_RE.sub("", s)
    s = re.sub(r"\s+", " ", s)
    return s
