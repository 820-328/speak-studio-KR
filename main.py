# -*- coding: utf-8 -*-
"""
SpeakStudio (Streamlit)
- Modes: Daily Chat / Shadowing / Roleplay
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
import re
import base64
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher, ndiff
from typing import Any, Dict, List, Tuple

import streamlit as st
import streamlit.components.v1 as components

# LLM 呼び出しは api_client に委譲（キー取得は utils 内部で自動解決）
from api_client import chat as llm_chat

APP_VERSION = "2025-09-26_24"

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


def extract_english_for_tts(full_text: str, max_len: int = 600) -> str:
    """
    返答文から日本語要約（JP: または JP： 以降）を除外して英語部分のみをTTS対象に。
    - 行頭/行内どちらの 'JP:' 'JP：' でも検出（大文字小文字を無視）
    - 全角コロン '：' にも対応
    """
    if not full_text:
        return ""
    m = re.search(r'(?im)^\s*jp\s*[:：]', full_text)
    cut = m.start() if m else None
    if cut is None:
        m2 = re.search(r'(?i)\bjp\s*[:：]', full_text)
        cut = m2.start() if m2 else len(full_text)
    eng = (full_text[:cut].strip() or full_text.strip())
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
# Data for Shadowing (各30文)
# ==============================
@dataclass
class ShadowSentence:
    id: str
    text_en: str
    text_ja: str
    hint: str


SENTENCES: List[ShadowSentence] = [
    # -------- やさしい (A1–A2): 30 ----------
    ShadowSentence("A1-001","Hello! Nice to meet you.","こんにちは。はじめまして。","Hello と Nice の母音をはっきり。"),
    ShadowSentence("A1-002","How are you today?","今日の調子はどう？","are を弱く、today に軽い強勢。"),
    ShadowSentence("A1-003","I'm fine, thank you.","元気です、ありがとう。","I'm を短く、thank の th を無声音で。"),
    ShadowSentence("A1-004","What’s your name?","お名前は？","what’s を一息で。"),
    ShadowSentence("A1-005","My name is Ken.","私の名前はケンです。","name に軽く強勢。"),
    ShadowSentence("A1-006","Where are you from?","どこの出身ですか？","are you を連結。"),
    ShadowSentence("A1-007","I'm from Tokyo.","東京出身です。","from を弱く短く。"),
    ShadowSentence("A1-008","What do you do?","お仕事は何ですか？","do you を連結。"),
    ShadowSentence("A1-009","I work in sales.","営業の仕事をしています。","work に強勢、in は弱く。"),
    ShadowSentence("A1-010","Do you like coffee?","コーヒーは好き？","like に強勢。"),
    ShadowSentence("A1-011","Yes, I do.","はい、好きです。","Yes をすっきり短く。"),
    ShadowSentence("A1-012","No, not really.","いいえ、あまり。","not をはっきり。"),
    ShadowSentence("A1-013","What time is it?","今、何時ですか？","time を明瞭に。"),
    ShadowSentence("A1-014","It’s almost noon.","もうすぐ正午です。","almost の l を軽く。"),
    ShadowSentence("A1-015","Could you say that again?","もう一度言ってもらえますか？","that again を滑らかに。"),
    ShadowSentence("A1-016","I don’t understand.","わかりません。","don’t の n’t を弱く。"),
    ShadowSentence("A1-017","Please speak slowly.","ゆっくり話してください。","speak を長くしすぎない。"),
    ShadowSentence("A1-018","Where is the station?","駅はどこですか？","the を弱く、station を明瞭に。"),
    ShadowSentence("A1-019","Turn left at the corner.","角で左に曲がってください。","turn と left にリズム。"),
    ShadowSentence("A1-020","How much is this?","これはいくらですか？","how を上げ調子で。"),
    ShadowSentence("A1-021","I’d like this one.","これをください。","I’d like を滑らかに。"),
    ShadowSentence("A1-022","Can I pay by card?","カードで払えますか？","pay を明瞭に。"),
    ShadowSentence("A1-023","I have a reservation.","予約があります。","have a を連結。"),
    ShadowSentence("A1-024","Just a moment, please.","少々お待ちください。","moment をはっきり。"),
    ShadowSentence("A1-025","I’m learning English.","英語を学んでいます。","learning の ing を弱く。"),
    ShadowSentence("A1-026","I practice every day.","毎日練習しています。","every day を二語で。"),
    ShadowSentence("A1-027","That sounds great!","それはいいですね！","sounds の s をはっきり。"),
    ShadowSentence("A1-028","See you tomorrow.","また明日。","tomorrow の第二音節に強勢。"),
    ShadowSentence("A1-029","Take care on your way.","気をつけて帰ってね。","take care を柔らかく。"),
    ShadowSentence("A1-030","Have a nice weekend!","良い週末を！","nice に軽く強勢。"),

    # -------- ふつう (B1): 30 ----------
    ShadowSentence("B1-001","I started learning English to improve my communication at work.","仕事でのコミュニケーションを高めるために英語を学び始めました。","started と improve の母音。"),
    ShadowSentence("B1-002","Could you give me a quick summary of the meeting?","会議の要点を手短に教えてくれますか？","quick summary を軽快に。"),
    ShadowSentence("B1-003","If we plan ahead, we can avoid most issues.","事前に計画すれば、ほとんどの問題を避けられます。","plan ahead を連結。"),
    ShadowSentence("B1-004","Let me check my schedule and get back to you this afternoon.","予定を確認して、今日の午後に折り返します。","get back to you の弱形。"),
    ShadowSentence("B1-005","I’ll send you the file once I finish editing.","編集が終わったらファイルを送ります。","once I を連結。"),
    ShadowSentence("B1-006","We need to streamline the process to save time.","時間節約のためにプロセスを効率化する必要があります。","streamline を伸ばしすぎない。"),
    ShadowSentence("B1-007","Thanks for your patience while we investigate.","調査の間お待ちいただきありがとうございます。","patience を明瞭に。"),
    ShadowSentence("B1-008","It would help if you could share more context.","詳しい背景を共有していただけると助かります。","would help if を滑らかに。"),
    ShadowSentence("B1-009","I prefer to discuss this in person.","これについては対面で話したいです。","prefer に強勢。"),
    ShadowSentence("B1-010","Can we reschedule for tomorrow morning?","明日の朝に予定変更できますか？","reschedule の /ʃ/。"),
    ShadowSentence("B1-011","I’m not sure yet, but I’ll let you know soon.","まだ分かりませんが、すぐに連絡します。","I’ll let you を連結。"),
    ShadowSentence("B1-012","Let’s focus on the main points first.","まず主要なポイントに集中しましょう。","focus on を連結。"),
    ShadowSentence("B1-013","I really appreciate your feedback.","フィードバックに感謝します。","appreciate の /ʃiːeɪt/。"),
    ShadowSentence("B1-014","We ran into a few unexpected problems.","いくつか予期しない問題が起きました。","ran into を連結。"),
    ShadowSentence("B1-015","I’ll handle the rest from here.","ここから先は私が対応します。","handle の /hæn/。"),
    ShadowSentence("B1-016","Please let me know if anything changes.","何か変更があれば知らせてください。","let me を連結。"),
    ShadowSentence("B1-017","It’s better to keep the explanation simple.","説明はシンプルに保つのが良いです。","better to を弱く。"),
    ShadowSentence("B1-018","We can reduce errors with clearer instructions.","より明確な指示でミスを減らせます。","reduce errors を滑らかに。"),
    ShadowSentence("B1-019","I’ll share the document after the call.","通話後に資料を共有します。","after the の th 弱形。"),
    ShadowSentence("B1-020","Could you walk me through the steps?","手順を順を追って説明してくれますか？","walk me through を連結。"),
    ShadowSentence("B1-021","I’m open to suggestions from the team.","チームからの提案を歓迎します。","open to を連結。"),
    ShadowSentence("B1-022","Let’s take a short break and continue later.","少し休憩して後で続けましょう。","short break を明瞭に。"),
    ShadowSentence("B1-023","We’ll need a couple of days to review this.","これを確認するのに2〜3日必要です。","couple of を /kʌpləv/。"),
    ShadowSentence("B1-024","Thanks for pointing that out.","指摘してくれてありがとう。","pointing that を連結。"),
    ShadowSentence("B1-025","I’ll double-check the numbers before sending.","送信前に数値を再確認します。","double-check に強勢。"),
    ShadowSentence("B1-026","This approach seems more practical.","このアプローチの方が現実的に見えます。","approach の /prou/。"),
    ShadowSentence("B1-027","Let’s keep the conversation respectful and clear.","会話は礼儀正しく明確に進めましょう。","respectful を丁寧に。"),
    ShadowSentence("B1-028","I’m happy to help as needed.","必要に応じて喜んで手伝います。","happy を短くはっきり。"),
    ShadowSentence("B1-029","Please share an example to illustrate your point.","例を挙げて説明してください。","illustrate を /ɪləstreɪt/。"),
    ShadowSentence("B1-030","We’ll follow up with next steps by email.","次の手順はメールで連絡します。","follow up を連結。"),

    # -------- むずかしい (B2): 30 ----------
    ShadowSentence("B2-001","With clearer goals and regular feedback, the team can sustain motivation and keep improving.","目標が明確で定期的なフィードバックがあれば、チームは意欲を維持し成長し続けられます。","clearer と regular のリズム。"),
    ShadowSentence("B2-002","If we align expectations early, we’ll prevent confusion down the line.","期待値を早めに揃えれば、後々の混乱を防げます。","align expectations を滑らかに。"),
    ShadowSentence("B2-003","I recommend prioritizing impact over effort when choosing tasks.","タスク選定では労力より効果を優先することを勧めます。","prioritizing の /praɪ/。"),
    ShadowSentence("B2-004","Given the constraints, this compromise is both realistic and fair.","制約を踏まえると、この妥協案は現実的で公平です。","Given the を弱く。"),
    ShadowSentence("B2-005","Let’s define success metrics before we commit resources.","資源を投下する前に成功指標を定義しましょう。","define success metrics を明瞭に。"),
    ShadowSentence("B2-006","Could you elaborate on the risks you anticipate?","想定しているリスクについて詳しく説明してもらえますか？","elaborate の /ɪˈlæ/。"),
    ShadowSentence("B2-007","We should validate assumptions with a small experiment first.","仮説はまず小さな実験で検証すべきです。","validate assumptions を連結。"),
    ShadowSentence("B2-008","I appreciate the initiative, but we need broader consensus.","主体性は評価しますが、より広い合意が必要です。","initiative の /ɪˈnɪ/。"),
    ShadowSentence("B2-009","Our timeline is ambitious, yet achievable with focus.","スケジュールは野心的ですが、集中すれば達成可能です。","ambitious yet を滑らかに。"),
    ShadowSentence("B2-010","Please back up your proposal with data and examples.","提案をデータと例で裏付けてください。","back up your を連結。"),
    ShadowSentence("B2-011","Let’s document decisions to avoid future ambiguity.","将来の曖昧さを避けるため、決定事項を記録しましょう。","document decisions を明瞭に。"),
    ShadowSentence("B2-012","I’m concerned about hidden costs and maintenance overhead.","隠れたコストと保守の負担が気になります。","maintenance の /meɪn/。"),
    ShadowSentence("B2-013","We can iterate quickly as long as feedback loops are tight.","フィードバックループが短ければ素早く反復できます。","iterate quickly を軽快に。"),
    ShadowSentence("B2-014","This trade-off favors reliability over raw speed.","このトレードオフは速度より信頼性を重視します。","trade-off をはっきり。"),
    ShadowSentence("B2-015","The proposal addresses most concerns but leaves security open.","提案は多くの懸念に対処しますが、セキュリティは未解決です。","addresses most を連結。"),
    ShadowSentence("B2-016","We’ll escalate if the issue persists after mitigation.","緩和策後も問題が続く場合はエスカレーションします。","escalate の /ɛs/。"),
    ShadowSentence("B2-017","It’s essential to separate facts from assumptions.","事実と仮定を切り分けることが重要です。","separate facts を明瞭に。"),
    ShadowSentence("B2-018","Let’s run a retrospective to capture lessons learned.","振り返りを実施して学びを記録しましょう。","retrospective のリズム。"),
    ShadowSentence("B2-019","I suggest we pilot this with a small user group.","小規模なユーザー群で試験運用することを提案します。","pilot this を滑らかに。"),
    ShadowSentence("B2-020","We should clarify ownership to streamline decisions.","意思決定を効率化するため、責任範囲を明確にしましょう。","clarify ownership を明瞭に。"),
    ShadowSentence("B2-021","Please challenge my idea if you see a better path.","より良い道が見えるなら、遠慮なく私の案に異議を唱えてください。","challenge my idea を流れるように。"),
    ShadowSentence("B2-022","Our constraints require creative yet practical solutions.","制約があるため、創造的で実用的な解決策が必要です。","creative yet practical を滑らかに。"),
    ShadowSentence("B2-023","We’ll de-risk this by phasing delivery and gathering feedback.","段階的な提供とフィードバック収集でリスクを下げます。","de-risk を明瞭に。"),
    ShadowSentence("B2-024","Let’s align on scope before discussing timelines.","スケジュールの前にスコープを揃えましょう。","align on scope を連結。"),
    ShadowSentence("B2-025","Please summarize the trade-offs in a single slide.","トレードオフを1枚のスライドに要約してください。","summarize the を連結。"),
    ShadowSentence("B2-026","I’m confident we can reach a balanced decision.","バランスの取れた決定に至れると確信しています。","confident をはっきり。"),
    ShadowSentence("B2-027","Assuming stable requirements, we can deliver in two sprints.","要件が安定していれば、2スプリントで提供できます。","assuming stable を滑らかに。"),
    ShadowSentence("B2-028","This path minimizes risk while preserving flexibility.","この道は柔軟性を保ちながらリスクを最小化します。","minimizes risk を明瞭に。"),
    ShadowSentence("B2-029","We need explicit success criteria to evaluate outcomes.","成果を評価する明確な成功基準が必要です。","explicit success をはっきり。"),
    ShadowSentence("B2-030","Let’s communicate updates proactively to build trust.","信頼を築くため、主体的に進捗を発信しましょう。","communicate updates を連結。"),
]


# ==============================
# Page setup & styles
# ==============================
st.set_page_config(page_title="SpeakStudio", layout="wide")

# ★ モバイルで白文字化されないように、文字色を強制（!important）
CSS_BLOCK = "\n".join(
    [
        "<style>",
        ".note {background:#e9f1ff;border:1px solid #bcd3ff;border-radius:10px;padding:10px 12px;margin:8px 0;}",
        ".warn {background:#fff1ec;border:1px solid #ffc7b5;border-radius:10px;padding:10px 12px;margin:8px 0;}",
        ".good {background:#ecfff1;border:1px solid #b9f5c9;border-radius:10px;padding:10px 12px;margin:8px 0;}",
        ".add {background:#e7ffe7;border:1px solid #b8f5b8;border-radius:6px;padding:1px 4px;margin:0 1px;}",
        ".del {background:#ffecec;border:1px solid #ffc5c5;border-radius:6px;padding:1px 4px;margin:0 1px;text-decoration:line-through;}",
        ".idpill {display:inline-block;background:#222;color:#fff;border-radius:8px;padding:2px 8px;font-size:12px;margin-right:6px;}",
        "/* テキスト色を濃いグレーで強制（内部の子要素も含む） */",
        ".note, .note * { color:#111 !important; }",
        ".warn, .warn * { color:#111 !important; }",
        ".good, .good * { color:#111 !important; }",
        "/* 予防的に、Markdown直下の色が白に上書きされている場合への対策 */",
        ".stMarkdown, .stMarkdown * { -webkit-text-fill-color: inherit !important; }",
        "</style>",
    ]
)
st.markdown(CSS_BLOCK, unsafe_allow_html=True)

# タイトルを一段小さい見出し（h2）で表示
st.header("SpeakStudio")
st.caption("Version: " + APP_VERSION)

# （β）無しのラジオ項目
mode = st.radio("モードを選択", ("日常英会話", "シャドーイング", "ロールプレイ"), index=0)


# Helper for option formatting
def format_sentence_option(sid: str, id_to_sent: Dict[str, ShadowSentence]) -> str:
    s = id_to_sent[sid].text_en
    preview = s[:60] + ("..." if len(s) > 60 else "")
    return f"{sid} : {preview}"


# -------------------------------------------------
# モバイル対応：WebAudioで再生（必要に応じて音量ブースト）
# -------------------------------------------------
def render_inline_play_button(mp3_bytes: bytes | None, label: str = "🔊 再生", boost: float = 1.0) -> None:
    """
    iOS/Android の制限を回避するため、ユーザーのクリック内で
    AudioContext.decodeAudioData → GainNode で再生。boost>1 で増幅。
    """
    if not mp3_bytes:
        st.markdown("<div class='warn'>音声の生成に失敗しました。</div>", unsafe_allow_html=True)
        return

    b64 = base64.b64encode(mp3_bytes).decode("ascii")
    components.html(
        f"""
        <div style="display:flex;gap:8px;align-items:center;">
          <button id="playBtn" style="
              background:#0b5cff;color:#fff;border:none;border-radius:8px;
              padding:8px 14px;cursor:pointer;font-size:14px;">{label}</button>
          <span id="hint" style="font-size:12px;color:#6b7280;"></span>
        </div>
        <script>
        (function(){{
          const b64 = "{b64}";
          const boost = {boost if boost>0 else 1.0};
          let audioCtx;
          let playingSource;

          function base64ToArrayBuffer(b64) {{
            const binary_string = atob(b64);
            const len = binary_string.length;
            const bytes = new Uint8Array(len);
            for (let i=0; i<len; i++) bytes[i] = binary_string.charCodeAt(i);
            return bytes.buffer;
          }}

          async function playOnce() {{
            try {{
              if (!audioCtx) {{
                audioCtx = new (window.AudioContext || window.webkitAudioContext)();
              }}
              if (audioCtx.state === "suspended") {{
                await audioCtx.resume();
              }}
              const ab = base64ToArrayBuffer(b64);
              const buf = await audioCtx.decodeAudioData(ab.slice(0));
              if (playingSource) {{
                try {{ playingSource.stop(); }} catch(_e) {{}}
              }}
              const src = audioCtx.createBufferSource();
              src.buffer = buf;

              const gainNode = audioCtx.createGain();
              gainNode.gain.value = Math.max(0.01, boost); // 1.0=等倍, >1で増幅

              src.connect(gainNode).connect(audioCtx.destination);
              src.start(0);
              playingSource = src;
              document.getElementById("hint").textContent = "";
            }} catch(e) {{
              console.error(e);
              document.getElementById("hint").textContent = "再生できませんでした。端末のサイレント解除・音量をご確認ください。";
            }}
          }}

          document.getElementById("playBtn").addEventListener("click", playOnce);
        }})();
        </script>
        """,
        height=48,
        scrolling=False,
    )


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

            # 英語部分のみTTS → モバイルでも確実に鳴るボタンで再生（少しブースト）
            eng = extract_english_for_tts(reply)
            mp3 = tts_cached(eng, lang="en")
            render_inline_play_button(mp3, label="🔊 英語の返答を再生", boost=1.4)

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

    # レベル → ID リスト（各30）
    levels = {
        "やさしい(A1–A2)": [f"A1-{i:03d}" for i in range(1, 31)],
        "ふつう(B1)": [f"B1-{i:03d}" for i in range(1, 31)],
        "むずかしい(B2)": [f"B2-{i:03d}" for i in range(1, 31)],
    }

    id_to_sent = {s.id: s for s in SENTENCES}

    col1, col2 = st.columns([1, 2])
    with col1:
        level = st.selectbox("レベル", list(levels.keys()), index=0)
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

    # お手本音声（TTS キャッシュ）
    demo_mp3 = tts_cached(target.text_en, lang="en")

    # モバイルでも確実 & 音量ブースト（1.8倍）
    st.markdown(" ")
    st.markdown("#### お手本の発音")
    render_inline_play_button(demo_mp3, label="▶ お手本を再生", boost=1.8)

    st.divider()

    st.markdown(" ")
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
# 3) Roleplay
# ==============================
else:
    st.subheader("ロールプレイ")
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

            # 英語部分のみTTS → モバイル確実再生（少しブースト）
            eng = extract_english_for_tts(reply)
            mp3 = tts_cached(eng, lang="en")
            render_inline_play_button(mp3, label="🔊 英語の返答を再生", boost=1.4)

        st.session_state[key_name].append({"role": "assistant", "content": reply})

# 共通フッター
st.caption("© 2025 SpeakStudio — Daily Chat + Shadowing + Roleplay")

# 日常英会話以外では通常フッター位置に表示
if mode != "日常英会話":
    show_footer_counter(placement="footer")
