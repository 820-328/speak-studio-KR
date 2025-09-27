# functions.py
# -*- coding: utf-8 -*-
"""
共通ユーティリティ群（KR版）:
- 音声ファイル用ディレクトリの確保
- アップロード音声の保存
- 任意モジュールの安全インポート
- 文字起こし（SpeechRecognition があれば使用 / 言語: ko-KR）
- 音声合成（gTTS→pyttsx3→テキスト不可の順でフォールバック / 言語: ko）

※ OpenAI 呼び出しは main.py 側の ss_api_client/api_client に委譲します。
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import uuid
from typing import Optional, Tuple, Any

# --- 安全に constants を読む（無くても動く） ---
try:
    import constants as ct  # type: ignore
except Exception:
    ct = None  # フォールバック

# 既定値（constants.py に同名定数があればそちらを優先）
APP_NAME: str = getattr(ct, "APP_NAME", "SpeakStudio KR")
AUDIO_OUTPUT_DIR: str = getattr(ct, "AUDIO_OUTPUT_DIR", "audio_outputs")
VOICE_LANG: str = getattr(ct, "VOICE_LANG", "ko")  # gTTS の lang コード（KR版は 'ko'）

# -----------------------------
# ファイル系
# -----------------------------
def ensure_audio_dir(path: Optional[str] = None) -> str:
    """音声ファイル保存ディレクトリを作成（存在しなければ作成）してパスを返す。"""
    out = path or AUDIO_OUTPUT_DIR
    os.makedirs(out, exist_ok=True)
    return out


def save_uploaded_audio(file_bytes: bytes, suffix: str = ".wav") -> str:
    """アップロード音声を保存してファイルパスを返す。"""
    out_dir = ensure_audio_dir()
    fname = f"input_{uuid.uuid4().hex}{suffix}"
    fpath = os.path.join(out_dir, fname)
    with open(fpath, "wb") as f:
        f.write(file_bytes)
    return fpath


# -----------------------------
# 動的 import ヘルパ
# -----------------------------
def _optional_import(module_name: str) -> Optional[Any]:
    """存在すればモジュールを返し、無ければ None（例外を表に出さない）。"""
    try:
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            return None
        return importlib.import_module(module_name)
    except Exception:
        return None


# -----------------------------
# 文字起こし
# -----------------------------
def transcribe_audio(audio_path: str) -> str:
    """
    SpeechRecognition があれば韓国語で簡易文字起こし（Google Web Speech API）。
    失敗時やライブラリ未導入時は空文字を返す。
    """
    sr = _optional_import("speech_recognition")
    if sr is None:
        return ""
    try:
        recognizer = sr.Recognizer()  # type: ignore[attr-defined]
        with sr.AudioFile(audio_path) as source:  # type: ignore[attr-defined]
            audio = recognizer.record(source)  # type: ignore[attr-defined]
        try:
            text = recognizer.recognize_google(audio, language="ko-KR")  # type: ignore[attr-defined]
            return text
        except Exception:
            return ""
    except Exception:
        return ""


# -----------------------------
# 音声合成（gTTS→pyttsx3→不可）
# -----------------------------
def synthesize_speech(text: str, lang: Optional[str] = None) -> Tuple[Optional[str], str]:
    """
    指定テキストを音声ファイルにし、(音声ファイルパス, 使用エンジン) を返す。
    失敗時は (None, reason) を返す。
    優先: gTTS(mp3, lang=ko) → pyttsx3(wav) → unavailable
    """
    lang = lang or VOICE_LANG
    out_dir = ensure_audio_dir()

    # 1) gTTS（mp3）
    gtts = _optional_import("gtts")
    if gtts is not None:
        try:
            mp3_path = os.path.join(out_dir, f"tts_{uuid.uuid4().hex}.mp3")
            gtts.gTTS(text=text, lang=lang).save(mp3_path)  # type: ignore[attr-defined]
            return mp3_path, "gTTS"
        except Exception:
            pass

    # 2) pyttsx3（wav）
    pyttsx3 = _optional_import("pyttsx3")
    if pyttsx3 is not None:
        try:
            engine = pyttsx3.init()  # type: ignore[attr-defined]
            wav_path = os.path.join(out_dir, f"tts_{uuid.uuid4().hex}.wav")
            engine.save_to_file(text, wav_path)  # type: ignore[attr-defined]
            engine.runAndWait()  # type: ignore[attr-defined]
            return wav_path, "pyttsx3"
        except Exception:
            pass

    # 3) フォールバック（音声生成不可）
    return None, "unavailable"
