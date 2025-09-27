# -*- coding: utf-8 -*-
"""
SpeakStudio KR (Streamlit)
- Modes: Daily Chat / Shadowing / Roleplay (Korean)
- Windows 11 + Python 3.10-3.12

Required packages (PowerShell):
    pip install streamlit streamlit-mic-recorder SpeechRecognition gTTS openai python-dotenv

Run:
    streamlit run main.py

Notes:
- Daily Chat / Roleplay need OPENAI_API_KEY (env or st.secrets). If missing, a simple local fallback reply is used.
- Shadowing works offline except gTTS (needs internet). Recording uses browser; STT uses SpeechRecognition.
- KR版: 音声合成(lang)は 'ko'、音声認識(language)は 'ko-KR'。
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

# ===== LLM 呼び出し（ss_api_client → api_client → なし の順でフォールバック） =====
try:
    from ss_api_client import chat as llm_chat  # type: ignore[reportAttributeAccessIssue]
except Exception:
    try:
        from api_client import chat as llm_chat  # type: ignore[reportAttributeAccessIssue]
    except Exception:
        def llm_chat(_messages, model=None):
            return None

APP_VERSION = "2025-09-27_kr4"

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
        "(ローカル簡易応答) 입력하신 문장을 확인했습니다.\n"
        f"당신의 입력: {last_user}\n"
        f"JP: あなたの入力は『{last_user}』でした。"
    )


def tts_bytes(text: str, lang: str = "ko") -> bytes | None:
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
def tts_cached(text: str, lang: str = "ko") -> bytes | None:
    """TTSをキャッシュ（同一セッション & 同一テキスト）"""
    return tts_bytes(text, lang)


def extract_non_jp_for_tts(full_text: str, max_len: int = 600) -> str:
    """
    返答文から日本語の要約行（JP:／JP：以降）を除外して、
    先頭（=韓国語本文）だけをTTS対象にする。全角コロンにも対応。
    """
    if not full_text:
        return ""
    m = re.search(r"(?im)^\s*jp\s*[:：]", full_text)
    cut = m.start() if m else None
    if cut is None:
        m2 = re.search(r"(?i)\bjp\s*[:：]", full_text)
        cut = m2.start() if m2 else len(full_text)
    head = (full_text[:cut].strip() or full_text.strip())
    return head[:max_len]


def stt_from_wav_bytes(wav_bytes: bytes, language: str = "ko-KR") -> Tuple[bool, str]:
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
# Data for Shadowing (KR 各30文)
# ==============================
@dataclass
class ShadowSentence:
    id: str
    text_ko: str
    text_ja: str
    hint: str


SENTENCES: List[ShadowSentence] = [
    # -------- やさしい (A1–A2): 30 ----------
    ShadowSentence("A1-001", "안녕하세요. 처음 뵙겠습니다.", "こんにちは。はじめまして。", "『안녕하세요』の語尾はやわらかく、二拍で。"),
    ShadowSentence("A1-002", "오늘 기분이 어때요?", "今日の気分はどう？", "『어때요』の語尾を上げ調子に。"),
    ShadowSentence("A1-003", "저는 괜찮아요. 감사합니다.", "私は大丈夫です。ありがとうございます。", "『괜찮아요』はクェンチャ나요。鼻音を意識。"),
    ShadowSentence("A1-004", "이름이 뭐예요?", "お名前は？", "『뭐예요』はムォエヨに近い響き。"),
    ShadowSentence("A1-005", "제 이름은 켄이에요.", "私の名前はケンです。", "『이에요/예요』の区別に注意。"),
    ShadowSentence("A1-006", "어디에서 오셨어요?", "どこから来ましたか？", "『오셨어요』のㅆ発音を弱く素早く。"),
    ShadowSentence("A1-007", "저는 도쿄에서 왔어요.", "私は東京から来ました。", "『왔어요』はワッソヨ。『ㅆ』ははっきり。"),
    ShadowSentence("A1-008", "직업이 뭐예요?", "お仕事は何ですか？", "『ㅂ이』の連結を滑らかに。"),
    ShadowSentence("A1-009", "저는 영업 일을 해요.", "私は営業の仕事をしています。", "『영업』の 받침は軽く、次に連結。"),
    ShadowSentence("A1-010", "커피 좋아해요?", "コーヒーは好き？", "『좋아해요』はチョアヘヨ。ㅎは弱く。"),
    ShadowSentence("A1-011", "네, 좋아해요.", "はい、好きです。", "リズムよく二音節＋三音節。"),
    ShadowSentence("A1-012", "아니요, 별로예요.", "いいえ、あまりです。", "『아니요』の最後は弱く下げる。"),
    ShadowSentence("A1-013", "지금 몇 시예요?", "今、何時ですか？", "『몇 시』はミョッシ。連音変化。"),
    ShadowSentence("A1-014", "거의 정오예요.", "ほぼ正午です。", "『거의』は語頭を軽く。"),
    ShadowSentence("A1-015", "다시 한 번 말해 주세요.", "もう一度言ってください。", "『말해 주세요』を滑らかに。"),
    ShadowSentence("A1-016", "잘 이해하지 못했어요.", "よく理解できませんでした。", "『하지』はハジ。子音を強くしすぎない。"),
    ShadowSentence("A1-017", "천천히 말해 주세요.", "ゆっくり話してください。", "『천천히』はチョンチョニ。"),
    ShadowSentence("A1-018", "역이 어디예요?", "駅はどこですか？", "『어디예요』は滑らかに一息で。"),
    ShadowSentence("A1-019", "코너에서 왼쪽으로 도세요.", "角で左に曲がってください。", "『왼쪽』はウェンッチョク。二重子音。"),
    ShadowSentence("A1-020", "이거 얼마예요?", "これはいくらですか？", "『얼마예요』は語尾上げ。"),
    ShadowSentence("A1-021", "이걸로 주세요.", "これをください。", "語尾『-요』を丁寧に。"),
    ShadowSentence("A1-022", "카드로 결제해도 돼요?", "カードで払えますか？", "『돼요』はデヨに近い。"),
    ShadowSentence("A1-023", "예약했어요.", "予約しました。", "『했어요』はヘッソヨ。"),
    ShadowSentence("A1-024", "잠시만 기다려 주세요.", "少々お待ちください。", "『잠시만』は三拍、均等に。"),
    ShadowSentence("A1-025", "저는 한국어를 배우고 있어요.", "私は韓国語を学んでいます。", "『를』の発音は軽く次へ連結。"),
    ShadowSentence("A1-026", "매일 연습해요.", "毎日練習します。", "『연습해요』はヨンスペヨ。"),
    ShadowSentence("A1-027", "정말 좋네요!", "本当にいいですね！", "感嘆符は明るく。『좋-』はチョッ。"),
    ShadowSentence("A1-028", "내일 봐요.", "また明日。", "『봐요』はプァヨに近い。"),
    ShadowSentence("A1-029", "조심해서 가세요.", "気をつけて帰ってね。", "『해서』はヘソ、連結を意識。"),
    ShadowSentence("A1-030", "즐거운 주말 보내세요!", "良い週末を！", "『주말』の子音は弱く短く。"),

    # -------- ふつう (B1): 30 ----------
    ShadowSentence("B1-001", "직장에서 소통을 늘리고 싶어서 한국어를 배우기 시작했어요.", "職場でのコミュニケーション向上のため韓国語を学び始めました。", "『시작했어요』の連結を滑らかに。"),
    ShadowSentence("B1-002", "회의 내용을 짧게 요약해 주실 수 있을까요?", "会議の要点を手短に教えていただけますか？", "『-실 수 있을까요』を一息で。"),
    ShadowSentence("B1-003", "미리 계획하면 대부분의問題를 피할 수 있어요.", "事前に計画すれば多くの問題を避けられます。", "『대부분의』の連結。"),
    ShadowSentence("B1-004", "일정을 확인하고 오늘 오후에 다시 연락드릴게요.", "予定を確認して今日の午後に折り返します。", "『연락드릴게요』末尾を柔らかく下げる。"),
    ShadowSentence("B1-005", "수정이 끝나면 파일을 보내 드릴게요.", "編集が終わったらファイルを送ります。", "『보내 드릴게요』丁寧な連結。"),
    ShadowSentence("B1-006", "시간을 절약하려면 프로세스를 간소화해야 해요.", "時間を節約するにはプロセスを簡素化すべきです。", "『해야 해요』はヘヤヘヨ。"),
    ShadowSentence("B1-007", "조사하는 동안 기다려 주셔서 감사합니다.", "調査の間お待ちいただきありがとうございます。", "『주셔서』はチュショソ。"),
    ShadowSentence("B1-008", "배경 정보를 조금 더 공유해 주시면 도움이 돼요.", "背景情報をもう少し共有していただけると助かります。", "『돼요』の発音に注意。"),
    ShadowSentence("B1-009", "이건 직접 만나서 이야기하고 싶어요.", "これは対面で話したいです。", "『직접』の받침は軽く。"),
    ShadowSentence("B1-010", "내일 아침으로 일정 변경할 수 있을까요?", "明日の朝に予定変更できますか？", "『-을 수 있을까요』のリズム。"),
    ShadowSentence("B1-011", "아직 확실하지 않지만 곧 알려 드릴게요.", "まだ分かりませんが、すぐ連絡します。", "『않지만』はアンチマン。"),
    ShadowSentence("B1-012", "먼저 핵심 포인트에 집중합시다.", "まず主要なポイントに集中しましょう。", "『집중합시다』末尾は穏やかに。"),
    ShadowSentence("B1-013", "피드백 주셔서 정말 감사해요.", "フィードバックありがとうございます。", "『정말』はチョンマル。"),
    ShadowSentence("B1-014", "예상치 못한 문제가 몇 가지 있었어요.", "予想外の問題がいくつかありました。", "『몇 가지』はミョッガジ。"),
    ShadowSentence("B1-015", "여기서부터는 제가 맡아서 진행할게요.", "ここから先は私が対応します。", "『진행할게요』は軽く下げる。"),
    ShadowSentence("B1-016", "변경 사항이 있으면 알려 주세요.", "何か変更があれば知らせてください。", "『-면 알려』を滑らかに。"),
    ShadowSentence("B1-017", "설명은 간단하게 유지하는 게 좋아요.", "説明はシンプルに保つのが良いです。", "『유지하는 게』自然な連結。"),
    ShadowSentence("B1-018", "지시를 더 명확히 하면 실수를 줄일 수 있어요.", "指示を明確にすればミスを減らせます。", "『명확히』はミョンファキ。"),
    ShadowSentence("B1-019", "통화가 끝나면 문서를 공유할게요.", "通話後に資料を共有します。", "『-면』は短く。"),
    ShadowSentence("B1-020", "단계를 순서대로 설명해 주실래요?", "手順を順を追って説明してくれますか？", "『주실래요』カジュアル丁寧。"),
    ShadowSentence("B1-021", "팀의 제안을 기꺼이 환영해요.", "チームからの提案を歓迎します。", "『기꺼이』は二拍で。"),
    ShadowSentence("B1-022", "잠깐 쉬었다가 나중에 이어서 합시다.", "少し休憩して後で続けましょう。", "『이어-』の連結を滑らかに。"),
    ShadowSentence("B1-023", "검토에는 이틀 정도 필요해요.", "確認には2〜3日必要です。", "『정도』を弱く。"),
    ShadowSentence("B1-024", "지적해 주셔서 고맙습니다.", "指摘してくれてありがとうございます。", "『주셔서』の舌位置を安定。"),
    ShadowSentence("B1-025", "보내기 전에 숫자를 다시 확인할게요.", "送る前に数値を再確認します。", "『확인할게요』は自然に。"),
    ShadowSentence("B1-026", "이 접근 방식이 더 현실적이에요.", "このアプローチの方が現実的です。", "『접근』はチョプグン。"),
    ShadowSentence("B1-027", "대화는 예의 바르고 명확하게 이어 가요.", "会話は礼儀正しく明確に進めましょう。", "『예의』はイェイ。"),
    ShadowSentence("B1-028", "필요하다면 기꺼이 도와드릴게요.", "必要に応じて喜んで手伝います。", "『도와드릴게요』丁寧表現。"),
    ShadowSentence("B1-029", "예시를 하나 들어서 설명해 주세요.", "例を挙げて説明してください。", "『들어서』はドゥロソ。"),
    ShadowSentence("B1-030", "다음 단계는 이메일로 안내드릴게요.", "次の手順はメールで案内します。", "『안내드릴게요』語尾を丁寧に。"),

    # -------- むずかしい (B2): 30 ----------
    ShadowSentence("B2-001", "목표를 더 분명히 하고 정기적으로 피드백을 주면, 팀은 동기를 유지하며 성장할 수 있어요.", "目標を明確にし定期的にフィードバックすれば、チームは意欲を保ち成長できます。", "句の切れ目で軽くポーズ。"),
    ShadowSentence("B2-002", "기대치를 초기에 맞춰 두면 나중의 혼란을 막을 수 있습니다.", "期待値を早めに揃えれば後々の混乱を防げます。", "『맞춰 두면』連結を滑らかに。"),
    ShadowSentence("B2-003", "업무를 고를 때는 노력보다 영향에 우선을 두는 게 좋습니다.", "タスク選定では労力より効果を優先しましょう。", "『영향』はヨンヒャン。"),
    ShadowSentence("B2-004", "여건을 고려하면 이 절충안이 가장 현실적이고 공정해요.", "制約を踏まえるとこの妥協案が現実的で公平です。", "『절충안』子音をはっきり。"),
    ShadowSentence("B2-005", "자원을 투입하기 전에 성공 지표를 먼저 정의합시다.", "資源投入の前に成功指標を定義しましょう。", "『정의합시다』はチョンウィ。"),
    ShadowSentence("B2-006", "예상하시는 위험 요소를 좀 더 자세히 설명해 주시겠어요?", "想定しているリスクを詳しく説明してもらえますか？", "丁寧表現をゆっくり。"),
    ShadowSentence("B2-007", "가설은 작은 실험으로 먼저 검증하는 게 바람직해요.", "仮説は小さな実験で先に検証すべきです。", "『바람직-』の破裂音を弱く。"),
    ShadowSentence("B2-008", "주도성을 높이 평가하지만, 더 넓은 합의가 필요합니다.", "主体性は評価しますが、より広い合意が必要です。", "対比はややゆっくり。"),
    ShadowSentence("B2-009", "일정은 도전적이지만 집중하면 충분히 달성 가능해요.", "スケジュールは野心的ですが集中すれば達成可能です。", "『달성』タルソン。"),
    ShadowSentence("B2-010", "제안에는 데이터와 구체적인 예를 반드시 덧붙여 주세요.", "提案はデータと具体例で裏付けてください。", "『덧붙여』はトッブチョ。"),
    ShadowSentence("B2-011", "향후의 모호함을 피하려면 결정 사항을 문서화합시다.", "将来の曖昧さを避けるには決定事項を文書化しましょう。", "『문서화-』は連結。"),
    ShadowSentence("B2-012", "숨은 비용과 유지보수 부담이 걱정됩니다.", "隠れたコストと保守負担が気になります。", "『유지보수』語中の母音を明瞭に。"),
    ShadowSentence("B2-013", "피드백 고리를 촘촘하게 만들면 빠르게 반복할 수 있어요.", "フィードバックループが短ければ素早く反復できます。", "『촘촘하게』は四拍で。"),
    ShadowSentence("B2-014", "이 트레이드오프는 속도보다 신뢰성을 중시합니다.", "このトレードオフは速度より信頼性を重視します。", "外来語の区切りを意識。"),
    ShadowSentence("B2-015", "대부분의 우려를 다뤘지만 보안은 아직 열려 있어요.", "多くの懸念に対応しましたが、セキュリティは未解決です。", "『다뤘-』はダルォッ。"),
    ShadowSentence("B2-016", "완화 조치 후에도 문제 지속 시에는 에스컬레이션합시다.", "緩和後も問題が続く場合はエスカレーションします。", "『에스컬레이션』区切りよく。"),
    ShadowSentence("B2-017", "사실과 가정을 확실히 구분하는 것이 중요합니다.", "事実と仮定を明確に分けることが重要です。", "『구분하는 것』の連結。"),
    ShadowSentence("B2-018", "회고를 진행해서 배운 점을 정리해 둡시다.", "振り返りを実施し学びを記録しましょう。", "『정리해 둡시다』末尾を丁寧に。"),
    ShadowSentence("B2-019", "작은 사용자 그룹으로 시범 운영을 제안합니다.", "小規模ユーザー群でパイロット運用を提案します。", "『시범』シボム。"),
    ShadowSentence("B2-020", "의사 결정을 신속히 하려면 소유권を 명확히 해야 해요.", "意思決定を迅速にするには責任範囲を明確に。", "『소유권』ソユクォン。"),
    ShadowSentence("B2-021", "더 나은 길이 보이면 제 의견에 기꺼이 이의를 제기해 주세요.", "より良い道があれば遠慮なく異議を唱えてください。", "『이의』はイウィ。"),
    ShadowSentence("B2-022", "제약이 있으니 창의적이면서도 실용적인 해법이 필요해요.", "制約があるため創造的かつ実用的な解決策が必要です。", "『창의적이면서도』のリズム。"),
    ShadowSentence("B2-023", "단계적 제공과 피드백 수집으로 위험을 낮추겠습니다.", "段階的提供とFB収集でリスクを下げます。", "『낮추-』はナチュ。"),
    ShadowSentence("B2-024", "일정을 논의하기 전에 범위를 먼저 맞춰 둡시다.", "スケジュール前にスコープを合わせましょう。", "『맞춰 둡시다』丁寧に。"),
    ShadowSentence("B2-025", "장단점을 한 장의 슬라이드로 간결히 정리해 주세요.", "トレードオフを1枚に要約してください。", "『간결히』は軽く。"),
    ShadowSentence("B2-026", "균형 잡힌 결론에 도달할 수 있다고 확신합니다.", "バランスの取れた結論に至れると確信しています。", "『확신합니다』語尾は下降。"),
    ShadowSentence("B2-027", "요건이 안정적이라면 두 스프린트 내 제공이 가능합니다.", "要件が安定していれば二スプリントで提供可能。", "外来語の区切りを丁寧に。"),
    ShadowSentence("B2-028", "유연성을 유지하면서 위험을 최소화하는 길입니다.", "柔軟性を保ちつつリスクを最小化します。", "『최소화』チェソファ。"),
    ShadowSentence("B2-029", "성과 평가를 위해 명시적 성공 기준이 필요합니다.", "成果評価に明示的成功基準が必要です。", "『명시적』ミョンシジョク。"),
    ShadowSentence("B2-030", "신뢰를 쌓기 위해 변화를 선제적으로 알립시다.", "信頼を築くため主体的に進捗を発信しましょう。", "『선제적으로』四拍で。"),
]


# ==============================
# Page setup & styles
# ==============================
st.set_page_config(page_title="SpeakStudio KR", layout="wide")

CSS_BLOCK = "\n".join(
    [
        "<style>",
        ".note {background:#e9f1ff;border:1px solid #bcd3ff;border-radius:10px;padding:10px 12px;margin:8px 0;}",
        ".warn {background:#fff1ec;border:1px solid #ffc7b5;border-radius:10px;padding:10px 12px;margin:8px 0;}",
        ".good {background:#ecfff1;border:1px solid #b9f5c9;border-radius:10px;padding:10px 12px;margin:8px 0;}",
        ".add {background:#e7ffe7;border:1px solid #b8f5b8;border-radius:6px;padding:1px 4px;margin:0 1px;}",
        ".del {background:#ffecec;border:1px solid #ffc5c5;border-radius:6px;padding:1px 4px;margin:0 1px;text-decoration:line-through;}",
        ".idpill {display:inline-block;background:#222;color:#fff;border-radius:8px;padding:2px 8px;font-size:12px;margin-right:6px;}",
        ".stMarkdown, .stMarkdown * { -webkit-text-fill-color: inherit !important; }",
        "</style>",
    ]
)
st.markdown(CSS_BLOCK, unsafe_allow_html=True)

# タイトル（h2）
st.header("SpeakStudio KR")
st.caption("Version: " + APP_VERSION)

# モード
mode = st.radio("モードを選択", ("日常韓国語会話", "シャドーイング", "ロールプレイ"), index=0)


# Helper for option formatting
def format_sentence_option(sid: str, id_to_sent: Dict[str, ShadowSentence]) -> str:
    s = id_to_sent[sid].text_ko
    preview = s[:60] + ("..." if len(s) > 60 else "")
    return f"{sid} : {preview}"


# -------------------------------------------------
# モバイル対応：WebAudioで再生
# -------------------------------------------------
def render_inline_play_button(mp3_bytes: bytes | None, label: str = "🔊 再生", boost: float = 1.0) -> None:
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
              gainNode.gain.value = Math.max(0.01, boost);

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
# 1) Daily Chat (KR)
# ==============================
if mode == "日常韓国語会話":
    st.subheader("日常韓国語会話")
    st.caption("※ OpenAI キーがない場合は簡易ローカル応答（音声なし）")

    if "daily_messages" not in st.session_state:
        st.session_state.daily_messages = [
            {
                "role": "system",
                "content": (
                    "You are a friendly Korean conversation partner. "
                    "Keep each reply under 120 words. Use simple, natural Korean. "
                    "At the end, add one short follow-up question. "
                    "After your Korean reply, add a concise Japanese line starting with 'JP:'."
                ),
            }
        ]

    # render history (skip system)
    for m in st.session_state.daily_messages:
        if m["role"] == "system":
            continue
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    user_text = st.chat_input("韓国語で話しかけてみよう…（日本語でもOK）", key="dc_input")
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

            # 韓国語部分のみTTS → モバイルでも確実に鳴るボタンで再生
            ko = extract_non_jp_for_tts(reply)
            mp3 = tts_cached(ko, lang="ko")
            render_inline_play_button(mp3, label="🔊 韓国語の返答を再生", boost=1.4)

        st.session_state.daily_messages.append({"role": "assistant", "content": reply})

    show_footer_counter(placement="below_input")


# ==============================
# 2) Shadowing (KR)
# ==============================
elif mode == "シャドーイング":
    st.subheader("シャドーイング（韓国語）")
    NOTE_HTML = (
        "<div class='note'>韓国語のモデル音声を聞いてすぐ重ねて話す練習です。録音後に文字起こしし、類似度と差分を表示します。</div>"
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
            "<span class='idpill'>" + target.id + "</span> **" + target.text_ko + "**",
            unsafe_allow_html=True,
        )
        with st.expander("和訳とヒント", expanded=False):
            st.write(target.text_ja)
            st.caption(target.hint)

    # お手本音声（TTS キャッシュ）
    demo_mp3 = tts_cached(target.text_ko, lang="ko")

    # モバイルでも確実 & 音量ブースト
    st.markdown(" ")
    st.markdown("#### お手本の発音（韓国語）")
    render_inline_play_button(demo_mp3, label="▶ お手本を再生", boost=1.8)

    st.divider()

    st.markdown(" ")
    st.markdown("#### あなたの発話を録音 / アップロード")
    wav_bytes: bytes | None = None
    tabs = st.tabs(["マイクで録音", "WAV をアップロード"])

    with tabs[0]:
        if not MIC_OK:
            MIC_WARN = (
                "<div class='warn'>`streamlit-mic-recorder` が未インストールのため、マイク録音は使用できません。"
                "下の『WAV をアップロード』を利用してください。<br>インストール: "
                "<code>pip install streamlit-mic-recorder</code></div>"
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
            ok, text_or_err = stt_from_wav_bytes(wav_bytes, language="ko-KR")
        if ok:
            recognized = text_or_err
            st.markdown("#### 認識結果 (あなたの発話・韓国語)")
            st.write(recognized)

            score = similarity_score(target.text_ko, recognized)
            st.markdown("#### 類似度スコア: **" + f"{score*100:.1f}%" + "**")

            st.markdown("#### 差分 (緑=追加/置換, 赤=不足)")
            html = diff_html(target.text_ko, recognized)
            st.markdown("<div class='note'>" + html + "</div>", unsafe_allow_html=True)

            fb: List[str] = []
            if score < 0.5:
                fb.append("まずはゆっくり・正確に。短い区切りで練習しましょう。")
            elif score < 0.75:
                fb.append("主要語の発音と抑揚を意識。機能語は弱く短く。")
            else:
                fb.append("良い感じ！ 連結やリズムをさらに自然に。")
            if any(w in target.text_ko for w in ["은", "는", "이", "가", "을", "를", "에", "에서"]):
                fb.append("助詞（은/는/이/가 など）の弱形と連結を意識しましょう。")
            st.markdown("#### フィードバック")
            for line in fb:
                st.markdown("- " + line)
        else:
            st.error(text_or_err)
    else:
        st.info("録音または WAV をアップロードすると評価します。")


# ==============================
# 3) Roleplay (KR)
# ==============================
else:
    st.subheader("ロールプレイ（韓国語）")
    st.caption("※ OpenAI キーがない場合は簡易ローカル応答（音声なし）")

    scenarios = {
        "ホテルのチェックイン": (
            "You are a hotel front desk staff speaking Korean. Be polite and concise. "
            "Ask for the guest's name and reservation details. Reply only in Korean, then add 'JP:' line."
        ),
        "ミーティングの進行": (
            "You are a meeting facilitator at a tech company speaking Korean. Keep the discussion on track "
            "and ask clarifying questions. Reply only in Korean, then add 'JP:' line."
        ),
        "カスタマーサポート": (
            "You are a customer support agent speaking Korean. Empathize and guide to solutions step by step. "
            "Reply only in Korean, then add 'JP:' line."
        ),
    }

    col_l, col_r = st.columns([1, 2])
    with col_l:
        scenario = st.selectbox("シナリオを選択", list(scenarios.keys()), index=0)
        tone = st.select_slider(
            "丁寧さ/カジュアル度",
            options=["フォーマル", "標準", "カジュアル"],
            value="標準",
        )
    with col_r:
        RP_NOTE = (
            "<div class='note'>相手役（AI）と韓国語で会話します。最後に短い質問を付け、"
            "JP: で日本語要約も付きます。</div>"
        )
        st.markdown(RP_NOTE, unsafe_allow_html=True)

    key_name = f"roleplay_messages::{scenario}::{tone}"
    if key_name not in st.session_state:
        style = {
            "フォーマル": "Use polite expressions and a formal tone.",
            "標準": "Use a neutral, business-casual tone.",
            "カジュアル": "Use friendly, casual expressions.",
        }[tone]
        sys_prompt = (
            scenarios[scenario] + " " + style
            + " Keep replies under 120 words. Ask one short follow-up question. "
            + "After the Korean reply, add a concise Japanese line starting with 'JP:'."
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

            # 韓国語部分のみTTS
            ko = extract_non_jp_for_tts(reply)
            mp3 = tts_cached(ko, lang="ko")
            render_inline_play_button(mp3, label="🔊 韓国語の返答を再生", boost=1.4)

        st.session_state[key_name].append({"role": "assistant", "content": reply})

# 共通フッター
st.caption("© 2025 SpeakStudio KR — Daily Chat + Shadowing + Roleplay")

# 日常会話以外では通常フッター位置に表示
if mode != "日常韓国語会話":
    show_footer_counter(placement="footer")
