# -*- coding: utf-8 -*-
"""
SpeakStudio functions:
- LLM / 翻訳
- STT（SpeechRecognition）
- TTS（Edge-TTS優先、無ければgTTS）
- MP3→WAV 変換（ffmpeg：imageio-ffmpeg か システム ffmpeg を自動検出）
- テキスト正規化
"""

from __future__ import annotations
import io
import os
import re
import unicodedata
import asyncio
import subprocess
import importlib
import importlib.util
import shutil
from typing import Optional, List, Dict, Any, Union, Tuple

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
    conf = get_lang_conf(lang_code)
    r = sr.Recognizer()
    try:
        text = r.recognize_google(audio_data, language=conf["stt"])  # type: ignore[attr-defined]
        return text
    except Exception:
        return ""


# ---------- ffmpeg 検出 ----------
def _detect_ffmpeg_exe() -> Optional[str]:
    """
    優先順:
    1) 環境変数 FFMPEG_PATH
    2) imageio-ffmpeg があればその静的 ffmpeg
    3) システム PATH 上の ffmpeg / ffmpeg.exe
    """
    # 1) env
    env_p = os.environ.get("FFMPEG_PATH")
    if isinstance(env_p, str) and env_p and os.path.isfile(env_p):
        return env_p

    # 2) imageio-ffmpeg（動的 import）
    try:
        spec = importlib.util.find_spec("imageio_ffmpeg")
        if spec is not None:
            mod = importlib.import_module("imageio_ffmpeg")
            get_exe = getattr(mod, "get_ffmpeg_exe", None)
            if callable(get_exe):
                p_obj: Any = get_exe()
                # p_obj が str か PathLike のときだけ扱う
                if isinstance(p_obj, str):
                    if os.path.isfile(p_obj):
                        return p_obj
                else:
                    try:
                        # PathLike を文字列化（非対応なら例外）
                        path_like = os.fspath(p_obj)  # type: ignore[arg-type]
                        if isinstance(path_like, str) and os.path.isfile(path_like):
                            return path_like
                    except Exception:
                        pass
    except Exception:
        pass

    # 3) system ffmpeg
    p = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    return p if isinstance(p, str) else None


_FFMPEG_PATH: Optional[str] = _detect_ffmpeg_exe()


# ---------- TTS ----------
async def _edge_tts_bytes_async(text: str, voice: str, rate_pct: int) -> bytes:
    """Edge-TTS で音声生成（MP3相当）。"""
    rate = f"{rate_pct:+d}%"
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)  # type: ignore[name-defined]
    out = io.BytesIO()
    async for chunk in communicate.stream():
        if isinstance(chunk, dict) and chunk.get("type") == "audio":
            data = chunk.get("data", b"")
            if isinstance(data, (bytes, bytearray)):
                out.write(data)
    return out.getvalue()


def _gtts_bytes(text: str, lang_code: str) -> bytes:
    conf = get_lang_conf(lang_code)
    tts = gTTS(text=text, lang=conf["tts"])
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()


def _mp3_to_wav_bytes(mp3_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> Optional[bytes]:
    """
    MP3 -> WAV(PCM16) に変換。ffmpeg が使えない場合は None を返す。
    iOS Safari などの互換性向上用。
    """
    if not _FFMPEG_PATH:
        return None
    try:
        cmd = [
            _FFMPEG_PATH,
            "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0",
            "-acodec", "pcm_s16le", "-ac", str(channels), "-ar", str(sample_rate),
            "-f", "wav", "pipe:1",
        ]
        proc = subprocess.run(cmd, input=mp3_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        return proc.stdout if proc.returncode == 0 and len(proc.stdout) > 44 else None
    except Exception:
        return None


def tts_synthesize(
    text: str,
    lang_code: str,
    rate_pct: int = 0,
    prefer_edge: bool = True,
    edge_voice: Optional[str] = None,
    force_wav: bool = False,
    force_gtts: bool = False,
) -> Tuple[bytes, str]:
    """
    音声合成（bytes, mime）を返す
    - Edge-TTS優先（audio/mpeg）
    - 失敗/短尺(1KB未満)時は gTTS に自動フォールバック（audio/mpeg）
    - force_gtts=True なら常に gTTS
    - force_wav=True なら最終的に WAV へ変換（可能なら）
    """
    audio_mp3: Optional[bytes] = None

    if not force_gtts and prefer_edge and _HAS_EDGE_TTS:
        voices = get_lang_conf(lang_code).get("edge_voices", [])
        voice = edge_voice or (voices[0] if voices else None)
        if voice:
            try:
                b = asyncio.run(_edge_tts_bytes_async(text, voice, rate_pct))
                if b and len(b) >= 1024:
                    audio_mp3 = b
            except Exception:
                audio_mp3 = None

    if audio_mp3 is None:
        audio_mp3 = _gtts_bytes(text, lang_code)

    if force_wav:
        wav = _mp3_to_wav_bytes(audio_mp3)
        if wav:
            return wav, "audio/wav"

    return audio_mp3, "audio/mpeg"


# ---------- 正規化（比較用） ----------
_PUNCT_RE = re.compile(r"[^\w\s\uAC00-\uD7A3]", flags=re.UNICODE)

def normalize_for_compare(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower().strip()
    s = _PUNCT_RE.sub("", s)
    s = re.sub(r"\s+", " ", s)
    return s
