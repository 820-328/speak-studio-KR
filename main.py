# -*- coding: utf-8 -*-
"""
SpeakStudio (Streamlit)
- Modes: Daily Chat / Shadowing / Roleplay
- モバイル最適化: スクロールボックス/配色(ライト/ダーク)/サイドバー案内
"""

from __future__ import annotations
import os
import io
import difflib
from typing import List, Dict, Any, Optional

import streamlit as st
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr

import constants as ct
import functions as fn

# ---------- ページ設定（スマホで分かりにくいので可能ならサイドバーを初期表示） ----------
st.set_page_config(
    page_title=ct.APP_NAME,
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- CSS：ライト/ダーク両対応 + スクロールボックス + モバイル案内 ----------
st.markdown("""
<style>
/* ベース配色：ライト */
html, body, .stApp { background-color: #ffffff; color: #111111; }
.block { background:#ffffff; color:#111111; border:1px solid #e5e7eb; padding:12px 14px; border-radius:14px; }
.note  { background:#f7faff; color:#0f172a; border:1px solid #cfe3ff; }
.tran  { background:#fff8e6; color:#1f2937; border:1px solid #ffd28a; }

/* ダークモード検出時の上書き（スマホのシステムダーク対策） */
@media (prefers-color-scheme: dark){
  html, body, .stApp { background-color: #0e1117 !important; color: #f5f5f5 !important; }
  .block { background:#111827; color:#f9fafb; border-color:#374151; }
  .note  { background:#0b132b; color:#e5e7eb; border-color:#1f3b73; }
  .tran  { background:#2d1b0f; color:#fef3c7; border-color:#a16207; }
}

/* 30件リスト用のスクロール枠（モバイルで全部見える） */
.scrollbox {
  max-height: 60vh; overflow: auto; padding: 10px 12px;
  background: inherit; color: inherit; border:1px dashed #cbd5e1; border-radius:12px;
}

/* モバイル専用ヒント（≡ を案内） */
.mobile-hint { display:none; }
@media (max-width: 640px){
  .mobile-hint {
    display:block; margin: 6px 0 10px 0;
    background:#fffbe6; color:#111827; border:1px solid #ffd666; border-radius:12px;
    padding:8px 10px; font-size:0.95rem;
  }
  @media (prefers-color-scheme: dark){
    .mobile-hint { background:#332d09; color:#fef3c7; border-color:#a27d00; }
  }
}
</style>
""", unsafe_allow_html=True)

# ---------- サイドバー ----------
with st.sidebar:
    st.markdown(f"### {ct.APP_NAME}")

    # 言語選択
    code_list = list(ct.LANGS.keys())
    label_list = [ct.LANGS[c]["label"] for c in code_list]
    lang_idx = st.radio("練習言語", options=range(len(code_list)),
                        format_func=lambda i: label_list[i],
                        index=code_list.index(ct.DEFAULT_LANG))
    lang = code_list[lang_idx]
    st.session_state["lang"] = lang

    # モード選択
    mode_map = {
        "Daily Chat": ct.ANSWER_MODE_DAILY,
        "Shadowing": ct.ANSWER_MODE_SHADOWING,
        "Roleplay": ct.ANSWER_MODE_ROLEPLAY,
    }
    mode_label = st.radio("モード", list(mode_map.keys()), index=0)
    mode = mode_map[mode_label]
    st.session_state["mode"] = mode

    st.divider()

    # 即時訳（韓→日）
    show_trans = st.checkbox("即時訳（韓→日）を表示", value=True,
                             help="アシスタントの韓国語出力を日本語に翻訳して下段に表示します。韓国語モードで有効。")

    st.divider()

    # TTS 設定
    prefer_edge = st.checkbox("Edge-TTSを優先する（速度調整可）", value=True)
    rate = st.slider("音声速度（％）", min_value=-50, max_value=50, value=0, step=5,
                     help="Edge-TTS使用時のみ有効（gTTSでは固定速度）")
    voices = ct.LANGS[lang].get("edge_voices", [])
    edge_voice = st.selectbox("Edge-TTSの声", voices, index=0 if voices else None) if voices else None
    st.session_state["tts_cfg"] = {"prefer_edge": prefer_edge, "rate": rate, "edge_voice": edge_voice}

    st.divider()
    st.markdown('<div class="block note"><small>Edge-TTSが使えない場合は自動でgTTSにフォールバックします。</small></div>', unsafe_allow_html=True)

# ---------- ヘッダー & モバイル案内 ----------
st.markdown(f"## {ct.APP_NAME}")
st.caption("英語 / 韓国語の会話練習・シャドーイング・ロールプレイ")
st.markdown('<div class="mobile-hint">📱 スマホでは左上の <b>≡</b> をタップしてサイドバー（言語・設定）を開けます。</div>', unsafe_allow_html=True)

# ---------- 共通ヘルパ ----------
def say_and_player(text: str, lang_code: str):
    cfg = st.session_state.get("tts_cfg", {"prefer_edge": True, "rate": 0, "edge_voice": None})
    mp3_bytes = fn.tts_synthesize(
        text, lang_code=lang_code,
        rate_pct=cfg["rate"], prefer_edge=cfg["prefer_edge"], edge_voice=cfg["edge_voice"]
    )
    st.audio(mp3_bytes, format="audio/mp3")

def show_translation_if_needed(source_text_ko: str):
    if lang == "ko" and show_trans and source_text_ko.strip():
        jp = fn.translate_text(source_text_ko, target_lang_label="Japanese")
        st.markdown('<div class="block tran">【日本語訳】<br>' + jp + '</div>', unsafe_allow_html=True)

# ========== 1) Daily Chat ==========
if mode == ct.ANSWER_MODE_DAILY:
    st.subheader("Daily Chat（フリートーク）")
    st.markdown('<div class="block note">選択した言語のみで応答し、音声も自動再生します。</div>', unsafe_allow_html=True)

    if "chat" not in st.session_state:
        st.session_state["chat"] = []

    for who, text in st.session_state["chat"]:
        with st.chat_message(who):
            st.write(text)
            if who == "assistant" and lang == "ko":
                show_translation_if_needed(text)

    user_text = st.chat_input("メッセージを入力（日本語/英語/韓国語 OK）")
    if user_text:
        st.session_state["chat"].append(("user", user_text))
        with st.chat_message("user"):
            st.write(user_text)

        system_prompt = ct.system_prompt_for(ct.ANSWER_MODE_DAILY, lang)
        reply = fn.chat_once(system_prompt, user_text, model=ct.OPENAI_MODEL)

        st.session_state["chat"].append(("assistant", reply))
        with st.chat_message("assistant"):
            st.write(reply)
            if lang == "ko":
                show_translation_if_needed(reply)
            say_and_player(reply, lang)

# ========== 2) Shadowing ==========
elif mode == ct.ANSWER_MODE_SHADOWING:
    st.subheader("Shadowing（音読・復唱）")

    cols = st.columns(3)
    with cols[0]:
        level = st.selectbox("難易度", ["easy", "normal", "hard"], index=0)
    with cols[1]:
        repeat_n = st.number_input("回数（同じ文）", min_value=1, max_value=5, value=1, step=1)
    with cols[2]:
        st.write("　")

    # 文リスト
    if lang == "ko":
        sents = ct.SHADOWING_CORPUS_KO[level]
    else:
        sents = ct.SHADOWING_CORPUS_EN[level]

    total = len(sents)
    st.markdown(f"#### 例文（{total}件）")

    # 30件すべて見えるスクロールボックス表示
    list_html = "<br>".join([f"{i}. {s}" for i, s in enumerate(sents, 1)])
    st.markdown(f'<div class="scrollbox">{list_html}</div>', unsafe_allow_html=True)

    # constants.py が古いと 30件に満たない可能性 → 目で分かるよう注意表示
    if total < 30:
        st.warning(f"このレベルの例文は {total} 件です。30件未満の場合は constants.py のコーパスが古い可能性があります。")

    st.markdown("---")
    idx = st.number_input("練習する文番号", min_value=1, max_value=total, value=1, step=1)
    target = sents[idx - 1]

    st.markdown("##### 目標文")
    st.markdown(f'<div class="block">{target}</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("▶️ 合成音声を再生"):
            say_and_player(target, lang)
    with c2:
        mic = mic_recorder(start_prompt="🎙️ 録音開始", stop_prompt="⏹️ 停止", just_once=True)
    with c3:
        st.write("　")

    # STTと評価
    if mic and "bytes" in mic:
        wav_bytes = mic["bytes"]
        recognizer = sr.Recognizer()
        try:
            with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
                audio = recognizer.record(source)
            transcribed = fn.stt_recognize_from_audio(audio, lang_code=lang)
        except Exception:
            transcribed = ""

        st.markdown("##### あなたの発話（STT）")
        st.write(transcribed if transcribed else "(聞き取れませんでした)")

        ref = fn.normalize_for_compare(target)
        got = fn.normalize_for_compare(transcribed)
        ratio = difflib.SequenceMatcher(None, ref, got).ratio()
        score = int(ratio * 100)
        st.markdown(f"**スコア：{score} / 100**")

        if lang == "ko":
            show_translation_if_needed(target)

        if repeat_n > 1:
            st.info(f"同じ文を {repeat_n} 回練習してみましょう。")

# ========== 3) Roleplay ==========
elif mode == ct.ANSWER_MODE_ROLEPLAY:
    st.subheader("Roleplay（韓国語シナリオ）")

    labels = [x["label"] for x in ct.ROLEPLAY_SCENARIOS_KO]
    idx = st.selectbox("シナリオ", list(range(len(labels))), format_func=lambda i: labels[i], index=0)
    scenario = ct.ROLEPLAY_SCENARIOS_KO[idx]

    key = f"rp_{scenario['key']}"
    if key not in st.session_state:
        st.session_state[key] = []

    with st.expander("シナリオ開始例（韓国語）", expanded=False):
        st.markdown(f"- 例: {scenario['opening_user_ko']}")

    for who, text in st.session_state[key]:
        with st.chat_message(who):
            st.write(text)
            if who == "assistant":
                show_translation_if_needed(text)

    user_text = st.chat_input("セリフを入力（日本語/韓国語）")
    if user_text:
        st.session_state[key].append(("user", user_text))
        with st.chat_message("user"):
            st.write(user_text)

        system_base = ct.system_prompt_for(ct.ANSWER_MODE_ROLEPLAY, "ko")
        system_prompt = scenario["system_prompt"] + "\n" + system_base

        reply = fn.chat_once(system_prompt, user_text, model=ct.OPENAI_MODEL)
        st.session_state[key].append(("assistant", reply))
        with st.chat_message("assistant"):
            st.write(reply)
            show_translation_if_needed(reply)
            say_and_player(reply, "ko")
