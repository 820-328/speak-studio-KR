# -*- coding: utf-8 -*-
"""
共通ユーティリティ群：
- LLM呼び出し（OpenAI）
- 音声合成（gTTS→pyttsx3→テキストの順でフォールバック）
- 文字起こし（SpeechRecognition があれば使用）
- 定数の安全フォールバック
"""
from __future__ import annotations

import importlib.util
import os
import uuid
import importlib
from typing import Optional, Tuple, Any

# --- 安全に constants を読む（無くても動く） ---
try:
    import constants as ct  # type: ignore
except Exception:
    ct = None  # フォールバック

# 既定値（constants.py に同名定数があればそちらを優先）
APP_NAME: str = getattr(ct, "APP_NAME", "English Conversation App")
AUDIO_OUTPUT_DIR: str = getattr(ct, "AUDIO_OUTPUT_DIR", "audio_outputs")
VOICE_LANG: str = getattr(ct, "VOICE_LANG", "en")  # gTTSのlangコード
OPENAI_MODEL: str = getattr(ct, "OPENAI_MODEL", "gpt-4o-mini")
SYSTEM_PROMPT_DAILY = getattr(
    ct,
    "SYSTEM_PROMPT_DAILY",
    "You are a friendly English conversation partner. Keep replies concise and natural."
)
SYSTEM_PROMPT_SHADOWING = getattr(
    ct,
    "SYSTEM_PROMPT_SHADOWING",
    "Provide a short, natural English sentence (10-20 words) suitable for shadowing practice."
)
SYSTEM_PROMPT_DICTATION = getattr(
    ct,
    "SYSTEM_PROMPT_DICTATION",
    "Provide a short, natural English sentence (8-15 words) for dictation. Avoid punctuation-heavy text."
)

# --- OpenAI SDK（1.x系） ---
_openai_client = None
def _get_openai_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    try:
        from openai import OpenAI  # pip install openai>=1.0
        _openai_client = OpenAI()
        return _openai_client
    except Exception:
        return None

def call_llm(user_text: str, mode: str = "daily") -> str:
    """
    OpenAIのChat Completionsで短い応答を返す。
    OpenAI SDKが使えない場合は簡易エコーバック。
    """
    system = {
        "daily": SYSTEM_PROMPT_DAILY,
        "shadowing": SYSTEM_PROMPT_SHADOWING,
        "dictation": SYSTEM_PROMPT_DICTATION,
    }.get(mode, SYSTEM_PROMPT_DAILY)

    client = _get_openai_client()
    if client is None:
        return f"(fallback reply) [{mode}] {user_text}"

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            temperature=0.7,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"(LLM error) {e}"

# --- ファイル系 ---
def ensure_audio_dir(path: Optional[str] = None) -> str:
    out = path or AUDIO_OUTPUT_DIR
    os.makedirs(out, exist_ok=True)
    return out

def save_uploaded_audio(file_bytes: bytes, suffix: str = ".wav") -> str:
    """アップロード音声を保存してパスを返す"""
    out_dir = ensure_audio_dir()
    fname = f"input_{uuid.uuid4().hex}{suffix}"
    fpath = os.path.join(out_dir, fname)
    with open(fpath, "wb") as f:
        f.write(file_bytes)
    return fpath

# --- 動的 import ヘルパ ---
def _optional_import(module_name: str) -> Optional[Any]:
    """存在すればモジュールを返し、無ければ None。Pylanceに怒られない方式。"""
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            return None
        return importlib.import_module(module_name)
    except Exception:
        return None

# --- 文字起こし（任意ライブラリがあれば利用） ---
def transcribe_audio(audio_path: str) -> str:
    """
    SpeechRecognitionがあれば英語で簡易文字起こし。
    無ければ空文字を返す（UI側で扱えるようにする）。
    """
    sr = _optional_import("speech_recognition")
    if sr is None:
        return ""
    try:
        recognizer = sr.Recognizer()
        with sr.AudioFile(audio_path) as source:
            audio = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio, language="en-US")
            return text
        except Exception:
            return ""
    except Exception:
        return ""

# --- 音声合成（gTTS→pyttsx3→テキスト） ---
def synthesize_speech(text: str, lang: Optional[str] = None) -> Tuple[Optional[str], str]:
    """
    指定テキストを音声ファイルにし、(音声ファイルパス, 実際に使用した方法) を返す。
    失敗時は (None, reason) を返す。
    """
    lang = lang or VOICE_LANG
    out_dir = ensure_audio_dir()

    # 1) gTTS（mp3）
    gtts = _optional_import("gtts")
    if gtts is not None:
        try:
            mp3_path = os.path.join(out_dir, f"tts_{uuid.uuid4().hex}.mp3")
            gtts.gTTS(text=text, lang=lang).save(mp3_path)
            return mp3_path, "gTTS"
        except Exception:
            pass

    # 2) pyttsx3（wav）
    pyttsx3 = _optional_import("pyttsx3")
    if pyttsx3 is not None:
        try:
            engine = pyttsx3.init()
            wav_path = os.path.join(out_dir, f"tts_{uuid.uuid4().hex}.wav")
            engine.save_to_file(text, wav_path)
            engine.runAndWait()
            return wav_path, "pyttsx3"
        except Exception:
            pass

    # 3) フォールバック（音声生成不可）
    return None, "unavailable"
