# -*- coding: utf-8 -*-
"""
English Practice App (Streamlit)
- Modes: Daily Chat / Shadowing / Roleplay (beta)
- Windows 11 + Python 3.10-3.12

Required packages (PowerShell):
    pip install streamlit streamlit-mic-recorder SpeechRecognition gTTS openai

Run:
    streamlit run main.py

Notes:
- Daily Chat / Roleplay need OPENAI_API_KEY (env or st.secrets). If missing, a simple local fallback reply is used.
- Shadowing works offline except gTTS (needs internet). Recording uses browser; STT uses SpeechRecognition.
"""
from __future__ import annotations

import io
import os
import base64
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher, ndiff
from typing import Any, Dict, List, Tuple

import streamlit as st
import streamlit.components.v1 as components

# LLM 呼び出しは api_client に委譲（キー取得は utils 内部で自動解決）
from api_client import chat as llm_chat

APP_VERSION = "2025-09-26_17"

# ===== Optional: mic recorder =====
try:
    from streamlit_mic_recorder import mic_recorder  # type: ignore
    MIC_OK = True
except Exception:
    MIC_OK = False

# ===== STT =====
try:
    import speech_recognition as sr  # type: ignore
    SR_OK = True
except Exception:
    sr = None  # type: ignore
    SR_OK = False

# ===== TTS =====
try:
    from gtts import gTTS
    GTTS_OK = True
except Exception:
    GTTS_OK = False


# ==============================
# Utilities
# ==============================
def local_fallback_reply(messages: List[Dict[str, Any]]) -> str:
    """APIキー無しや失敗時の簡易ローカル応答"""
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = m.get("content", "")
            break
    return (
        f"(ローカル簡易応答) I understood your message and will keep it short.\n"
        f"You said: {last_user}\n"
        f"JP: あなたの入力は『{last_user}』でした。"
    )


def tts_bytes(text: str, lang: str = "en") -> bytes | None:
    """Return MP3 bytes using gTTS, or None if failed."""
    if not GTTS_OK:
        return None
    try:
        tts = gTTS(text=text, lang=lang)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def tts_cached(text: str, lang: str = "en") -> bytes | None:
    """TTSをキャッシュ（同一セッション & 同一テキスト）"""
    return tts_bytes(text, lang)


def play_audio_js(mp3_bytes: bytes, nonce: str) -> None:
    """
    コントロール無し・即再生。クリック毎に nonce を変えて確実に再生。
    components.html は key を受け取らないため、HTML文字列自体を毎回変える。
    """
    if not mp3_bytes:
        return
    b64 = base64.b64encode(mp3_bytes).decode("ascii")
    # height>0 にしないと描画されない環境があるため 10px
    components.html(
        f"""
        <!-- nonce:{nonce} -->
        <audio id="ghost-audio-{nonce}" src="data:audio/mp3;base64,{b64}" style="display:none"></audio>
        <script>
          const a = document.getElementById('ghost-audio-{nonce}');
          if (a) {{
            a.currentTime = 0;
            a.play().catch(() => {{ /* autoplay 制限時は無視 */ }});
          }}
        </script>
        """,
        height=10,
        scrolling=False,
    )


def extract_english_for_tts(full_text: str, max_len: int = 600) -> str:
    """返答文から 'JP:' 以降を除外して英語部分のみをTTS対象に。"""
    lines = []
    for line in full_text.splitlines():
        if line.strip().startswith("JP:"):
            break
        lines.append(line)
    eng = "\n".join(lines).strip() or full_text.strip()
    return eng[:max_len]


def stt_from_wav_bytes(wav_bytes: bytes, language: str = "en-US") -> Tuple[bool, str]:
    """SpeechRecognition to transcribe WAV bytes. Returns (ok, text_or_error)."""
    if not SR_OK:
        return False, "SpeechRecognition が未インストールです。 pip install SpeechRecognition"
    recognizer = sr.Recognizer()  # type: ignore
    try:
        with sr.AudioFile(io.BytesIO(wav_bytes)) as source:  # type: ignore
            audio = recognizer.record(source)  # type: ignore
        text = recognizer.recognize_google(audio, language=language)  # type: ignore[attr-defined]
        return True, text
    except Exception as e:
        return False, f"音声の解析に失敗しました: {e}"


def similarity_score(ref: str, hyp: str) -> float:
    return SequenceMatcher(None, ref.lower().strip(), hyp.lower().strip()).ratio()


def diff_html(ref: str, hyp: str) -> str:
    out: List[str] = []
    for token in ndiff(ref.split(), hyp.split()):
        if token.startswith("- "):
            out.append("<span class='del'>" + token[2:] + "</span>")
        elif token.startswith("+ "):
            out.append("<span class='add'>" + token[2:] + "</span>")
        elif token.startswith("? "):
            pass
        else:
            out.append(token[2:])
    return " ".join(out)


# ==============================
# Access Counter (SQLite)
# ==============================
DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR, "counter.db")

def _init_counter_db() -> None:
    """カウンタ用DBの初期化（存在しなければ作成）"""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)  # autocommit
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS counters (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO counters(name, value) VALUES(?, ?);",
            ("page_views", 0),
        )
    finally:
        conn.close()

def increment_and_get_page_views() -> int:
    """同一ブラウザの1セッション中は1度だけ加算し、累計を返す"""
    if "view_counted" not in st.session_state:
        st.session_state.view_counted = False

    _init_counter_db()
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)  # autocommit
    try:
        if not st.session_state.view_counted:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute("UPDATE counters SET value = value + 1 WHERE name = ?;", ("page_views",))
            conn.commit()
            st.session_state.view_counted = True

        cur = conn.execute("SELECT value FROM counters WHERE name = ?;", ("page_views",))
        row = cur.fetchone()
        total = row[0] if row else 0
        return total
    finally:
        conn.close()

def show_footer_counter(placement: str = "footer") -> None:
    """
    placement:
      - "footer": 通常のページ下部に表示
      - "below_input": チャット入力欄のさらに下（画面最下部）に固定表示
    """
    total = increment_and_get_page_views()

    if placement == "below_input":
        st.markdown(
            f"""
            <style>
              [data-testid="stChatInput"] {{ margin-bottom: 28px; }}
              .footer-counter-fixed {{
                position: fixed;
                left: 0; right: 0;
                bottom: 6px;
                text-align: center;
                color: #9aa0a6;
                font-size: 12px;
                opacity: 0.9;
                pointer-events: none;
                z-index: 999;
              }}
            </style>
            <div class="footer-counter-fixed">累計アクセス：{total:,} 回</div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <style>
            .footer-counter {{
                color: #9aa0a6;
                font-size: 12px;
                text-align: center;
                margin-top: 32px;
                opacity: 0.9;
            }}
            </style>
            <div class="footer-counter">累計アクセス：{total:,} 回</div>
            """,
            unsafe_allow_html=True,
        )


# ==============================
# Data for Shadowing
# ==============================
@dataclass
class ShadowSentence:
    id: str
    text_en: str
    text_ja: str
    hint: str


SENTENCES: List[ShadowSentence] = [
    ShadowSentence(
        id="A1-001",
        text_en="Could you tell me how to get to the nearest station?",
        text_ja="最寄り駅への行き方を教えていただけますか？",
        hint="丁寧さを保ちつつ、語尾をはっきり。station の音に注意。",
    ),
    ShadowSentence(
        id="A1-002",
        text_en="I started learning English to improve my work communication.",
        text_ja="仕事でのコミュニケーションを上達させるために英語の勉強を始めました。",
        hint="started と communication の発音をゆっくり確認。",
    ),
    ShadowSentence(
        id="A2-003",
        text_en="Let me check my schedule and get back to you this afternoon.",
        text_ja="予定を確認して、今日の午後に折り返し連絡します。",
        hint="get back to you の連結と弱形、afternoon の第2音節を強めて。",
    ),
    ShadowSentence(
        id="B1-004",
        text_en="If we streamline the process, we can reduce errors and save time.",
        text_ja="プロセスを合理化すれば、ミスを減らして時間を節約できます。",
        hint="streamline の長音を過度に強調しない。",
    ),
    ShadowSentence(
        id="B2-005",
        text_en="With clearer goals and regular feedback, our team can maintain high motivation and keep improving.",
        text_ja="目標を明確にし定期的なフィードバックを行えば、チームは高いモチベーションを維持し続けられます。",
        hint="clearer と regular のリズムに注意。",
    ),
]


# ==============================
# Page setup & styles
# ==============================
st.set_page_config(page_title="英会話アプリ", layout="wide")

CSS_BLOCK = "\n".join(
    [
        "<style>",
        ".note {background:#f6f9ff;border:1px solid #c9dcff;border-radius:10px;padding:10px 12px;margin:8px 0;}",
        ".warn {background:#fff8f6;border:1px solid #ffd3c6;border-radius:10px;padding:10px 12px;margin:8px 0;}",
        ".good {background:#f6fff6;border:1px solid #c6ffd3;border-radius:10px;padding:10px 12px;margin:8px 0;}",
        ".add {background:#e7ffe7;border:1px solid #b8f5b8;border-radius:6px;padding:1px 4px;margin:0 1px;}",
        ".del {background:#ffecec;border:1px solid #ffc5c5;border-radius:6px;padding:1px 4px;margin:0 1px;text-decoration:line-through;}",
        ".idpill {display:inline-block;background:#222;color:#fff;border-radius:8px;padding:2px 8px;font-size:12px;margin-right:6px;}",
        "</style>",
    ]
)

st.markdown(CSS_BLOCK, unsafe_allow_html=True)

st.title("英会話アプリ")
st.caption("Version: " + APP_VERSION)
mode = st.radio("モードを選択", ("日常英会話", "シャドーイング", "ロールプレイ（β）"), index=0)


# Helper for option formatting
def format_sentence_option(sid: str, id_to_sent: Dict[str, ShadowSentence]) -> str:
    s = id_to_sent[sid].text_en
    preview = s[:60] + ("..." if len(s) > 60 else "")
    return f"{sid} : {preview}"


# ==============================
# 1) Daily Chat
# ==============================
if mode == "日常英会話":
    st.subheader("日常英会話")
    st.caption("※ OpenAI キーがない場合は簡易ローカル応答（音声なし）")

    if "daily_messages" not in st.session_state:
        st.session_state.daily_messages = [
            {
                "role": "system",
                "content": (
                    "You are a friendly English conversation partner. "
                    "Keep each reply under 120 words. Use simple, natural English. "
                    "At the end, add one short follow-up question. "
                    "After your English reply, add a concise Japanese line starting with 'JP:'."
                ),
            }
        ]

    # render history (skip system)
    for m in st.session_state.daily_messages:
        if m["role"] == "system":
            continue
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    user_text = st.chat_input("英語で話しかけてみよう…（日本語でもOK）", key="dc_input")
    if user_text:
        st.session_state.daily_messages.append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.markdown(user_text)
        with st.chat_message("assistant"):
            with st.spinner("考え中…"):
                reply = llm_chat(st.session_state.daily_messages)
                if reply is None:
                    reply = local_fallback_reply(st.session_state.daily_messages)
            st.markdown(reply)

            # === 返答の英語部分をTTSで読み上げ（可視プレイヤー） ===
            eng = extract_english_for_tts(reply)
            mp3 = tts_cached(eng, lang="en")
            if mp3:
                st.audio(mp3, format="audio/mp3")
            else:
                st.caption("（音声生成に失敗：ネットワークまたは gTTS の状態をご確認ください）")

        st.session_state.daily_messages.append({"role": "assistant", "content": reply})

    # 入力欄の“さらに下”に固定カウンター
    show_footer_counter(placement="below_input")


# ==============================
# 2) Shadowing
# ==============================
elif mode == "シャドーイング":
    st.subheader("シャドーイング")
    NOTE_HTML = (
        "<div class='note'>英語のモデル音声を聞いてすぐ重ねて話す練習です。録音後に文字起こしし、類似度と差分を表示します。</div>"
    )
    st.markdown(NOTE_HTML, unsafe_allow_html=True)

    levels = {
        "やさしい(A1–A2)": ["A1-001", "A1-002", "A2-003"],
        "ふつう(B1)": ["B1-004"],
        "むずかしい(B2)": ["B2-005"],
    }
    col1, col2 = st.columns([1, 2])
    with col1:
        level = st.selectbox("レベル", list(levels.keys()), index=0)
        id_to_sent = {s.id: s for s in SENTENCES}
        choices = levels[level]
        sel_id = st.selectbox(
            "文例",
            choices,
            format_func=lambda sid: format_sentence_option(sid, id_to_sent),
        )
    with col2:
        target = id_to_sent[sel_id]
        st.markdown(
            "<span class='idpill'>" + target.id + "</span> **" + target.text_en + "**",
            unsafe_allow_html=True,
        )
        with st.expander("和訳とヒント", expanded=False):
            st.write(target.text_ja)
            st.caption(target.hint)

    # === お手本音声を事前生成（選択した文に対して一度だけ） ===
    demo_mp3 = tts_cached(target.text_en, lang="en")

    # === お手本の発音：押すたびに毎回・即再生（コントロール非表示） ===
    st.markdown("#### お手本の発音")
    if st.button("▶ お手本を再生", key=f"demo_tts_btn_{sel_id}"):
        if demo_mp3:
            hit_count = st.session_state.get("_demo_hits", 0) + 1
            st.session_state["_demo_hits"] = hit_count
            play_audio_js(demo_mp3, nonce=f"{sel_id}-{hit_count}")
        else:
            st.markdown(
                "<div class='warn'>お手本音声の生成に失敗しました。ネットワークや gTTS の状態をご確認ください。</div>",
                unsafe_allow_html=True,
            )

    st.divider()

    st.markdown("#### あなたの発話を録音 / アップロード")
    wav_bytes: bytes | None = None
    tabs = st.tabs(["マイクで録音", "WAV をアップロード"])

    with tabs[0]:
        if not MIC_OK:
            MIC_WARN = (
                "<div class='warn'>`streamlit-mic-recorder` が未インストールのため、マイク録音は使用できません。下の『WAV をアップロード』を利用してください。<br>インストール: <code>pip install streamlit-mic-recorder</code></div>"
            )
            st.markdown(MIC_WARN, unsafe_allow_html=True)
        else:
            st.write("ボタンを押して録音 → もう一度押して停止。")
            audio = mic_recorder(
                start_prompt="🎙 録音開始",
                stop_prompt="🛑 停止",
                key="shadow_rec",
                use_container_width=True,
                format="wav",
            )
            if audio and isinstance(audio, dict) and audio.get("bytes"):
                wav_bytes = audio["bytes"]
                st.audio(wav_bytes, format="audio/wav")

    with tabs[1]:
        up = st.file_uploader("WAV (16k〜48kHz, PCM) を選択", type=["wav"], key="wav_upload")
        if up:
            wav_bytes = up.read()
            st.audio(wav_bytes, format="audio/wav")

    st.divider()

    if wav_bytes is not None:
        with st.spinner("音声を解析しています…"):
            ok, text_or_err = stt_from_wav_bytes(wav_bytes, language="en-US")
        if ok:
            recognized = text_or_err
            st.markdown("#### 認識結果 (あなたの発話)")
            st.write(recognized)

            score = similarity_score(target.text_en, recognized)
            st.markdown("#### 類似度スコア: **" + f"{score*100:.1f}%" + "**")

            st.markdown("#### 差分 (緑=追加/置換, 赤=不足)")
            html = diff_html(target.text_en, recognized)
            st.markdown("<div class='note'>" + html + "</div>", unsafe_allow_html=True)

            fb: List[str] = []
            if score < 0.5:
                fb.append("まずはゆっくり・正確に。短い区切りで練習しましょう。")
            elif score < 0.75:
                fb.append("主要語の発音と抑揚を意識。機能語は弱く短く。")
            else:
                fb.append("良い感じ！ 連結やリズムをさらに自然に。")
            if any(w in target.text_en.lower() for w in ["the", "to", "and", "of", "can", "you"]):
                fb.append("the/to/and/of などは弱く短く、内容語は強く長く。")
            st.markdown("#### フィードバック")
            for line in fb:
                st.markdown("- " + line)
        else:
            st.error(text_or_err)
    else:
        st.info("録音または WAV をアップロードすると評価します。")


# ==============================
# 3) Roleplay (beta)
# ==============================
else:
    st.subheader("ロールプレイ（β）")
    st.caption("※ OpenAI キーがない場合は簡易ローカル応答（音声なし）")

    scenarios = {
        "ホテルのチェックイン": "You are a hotel front desk staff. Be polite and concise. Ask for the guest's name and reservation details.",
        "ミーティングの進行": "You are a meeting facilitator at a tech company. Keep the discussion on track and ask clarifying questions.",
        "カスタマーサポート": "You are a customer support agent. Empathize and guide to solutions step by step.",
    }

    col_l, col_r = st.columns([1, 2])
    with col_l:
        scenario = st.selectbox("シナリオを選択", list(scenarios.keys()), index=0)
        tone = st.select_slider("丁寧さ/カジュアル度", options=["フォーマル", "標準", "カジュアル"], value="標準")
    with col_r:
        RP_NOTE = (
            "<div class='note'>相手役（AI）と会話します。英語→最後に短い質問を付け、JP: で日本語要約も付きます。</div>"
        )
        st.markdown(RP_NOTE, unsafe_allow_html=True)

    key_name = "roleplay_messages::" + scenario + "::" + tone
    if key_name not in st.session_state:
        style = {
            "フォーマル": "Use polite expressions and a formal tone.",
            "標準": "Use a neutral, business-casual tone.",
            "カジュアル": "Use friendly, casual expressions.",
        }[tone]
        sys_prompt = (
            scenarios[scenario]
            + " "
            + style
            + " Keep replies under 120 words. Ask one short follow-up question. "
            + "After the English reply, add a concise Japanese line starting with 'JP:'."
        )
        st.session_state[key_name] = [{"role": "system", "content": sys_prompt}]

    # 履歴表示
    for m in st.session_state[key_name]:
        if m["role"] == "system":
            continue
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # 入力
    user_input = st.chat_input("あなたのセリフ（日本語でもOK）", key=f"rp_input_{key_name}")
    if user_input:
        st.session_state[key_name].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("相手役が考えています…"):
                reply = llm_chat(st.session_state[key_name])
                if reply is None:
                    reply = local_fallback_reply(st.session_state[key_name])
            st.markdown(reply)

            # === 返答の英語部分をTTSで読み上げ（可視プレイヤー） ===
            eng = extract_english_for_tts(reply)
            mp3 = tts_cached(eng, lang="en")
            if mp3:
                st.audio(mp3, format="audio/mp3")
            else:
                st.caption("（音声生成に失敗：ネットワークまたは gTTS の状態をご確認ください）")

        st.session_state[key_name].append({"role": "assistant", "content": reply})

# 共通フッター
st.caption("© 2025 English Practice App — Daily Chat + Shadowing + Roleplay (β)")

# 日常英会話以外では通常フッター位置に表示
if mode != "日常英会話":
    show_footer_counter(placement="footer")
