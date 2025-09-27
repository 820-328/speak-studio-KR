# -*- coding: utf-8 -*-
"""
SpeakStudio (Streamlit)
- スマホ互換: <audio> に WAV と MP3 を両方埋め込み（ブラウザが自動選択）
- 録音: 通常は streamlit-mic-recorder、ダメなら WebRTC 録音（ベータ）に切替
- gTTS強制 / WAV変換 / 代替プレーヤー（HTML直埋め）をサイドバーで切替
- スクロール例文・ダークモード可読CSS・サイドバー案内
"""

from __future__ import annotations
import io
import difflib
import base64
import wave
import numpy as np

import streamlit as st
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr

import constants as ct
import functions as fn

# ---------- ページ設定 ----------
st.set_page_config(page_title=ct.APP_NAME, page_icon="🎧", layout="wide")

# ---------- CSS ----------
st.markdown("""
<style>
:root { --radius: 14px; }

/* 共通ボックス */
.block { border: 1px solid #e5e7eb; padding: 12px 14px; border-radius: var(--radius); background: #ffffff; color: #111; }
.note  { background: #f7faff; border-color: #cfe3ff; color: #111; }
.tran  { background: #fff8e6; border-color: #ffd28a; color: #111; }
small.help { color: #333; }

/* モバイル向けヒント（幅が狭い時だけ表示） */
.mobile-tip { display:none; margin: 8px 0 12px; padding:10px 12px; border:1px dashed #6aa0ff; border-radius:12px; background:#eef5ff; color:#0b1f3a; }
@media (max-width: 768px) { .mobile-tip { display:block; } }

/* 例文のスクロールボックス：30件でも見切れない */
.scroll-list {
  max-height: 50vh; overflow-y: auto; padding: 8px 12px;
  border: 1px solid #e5e7eb; border-radius: 12px; background: #fff; color: #111;
}

/* ダークテーマ時の読みやすさ確保（白地に黒字を強制） */
@media (prefers-color-scheme: dark) {
  .block, .note, .tran, .scroll-list { color: #111; background: #fff; border-color: #e5e7eb; }
  small.help { color: #222; }
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
        "Roleplay": ct.ANSWER_MODE_ROLEPLAY
    }
    mode_label = st.radio("モード", list(mode_map.keys()), index=0)
    mode = mode_map[mode_label]
    st.session_state["mode"] = mode

    st.divider()

    # 即時訳（韓→日）
    show_trans = st.checkbox("即時訳（韓→日）を表示", value=True)

    # 自動再生（スマホはOFF推奨）
    autoplay = st.checkbox("音声の自動再生（iOSはOFF推奨）", value=False)
    st.session_state["autoplay"] = autoplay

    # 互換性オプション
    use_alt_player = st.checkbox("代替プレーヤー（HTML直埋め）を使う", value=True,
                                 help="スマホで再生エラーが出る場合はON。")
    force_gtts = st.checkbox("gTTSを強制（互換性優先）", value=True,
                             help="Edge-TTSで鳴らない端末向け。速度調整は無効。")
    force_wav = st.checkbox("WAVに変換して再生（互換性優先・推奨）", value=True,
                            help="ffmpeg利用。iOS Safari などで安定。")

    st.divider()

    # TTS 設定（gTTS強制時は速度/声の選択を無効化）
    prefer_edge = st.checkbox("Edge-TTSを優先する（速度調整可）",
                              value=not force_gtts, disabled=force_gtts)
    rate = st.slider("音声速度（％）", min_value=-50, max_value=50, value=0, step=5, disabled=force_gtts)
    voices = ct.LANGS[lang].get("edge_voices", [])
    edge_voice = st.selectbox("Edge-TTSの声", voices, index=0 if voices else None, disabled=force_gtts) if voices else None

    st.session_state["tts_cfg"] = {
        "prefer_edge": prefer_edge,
        "rate": rate,
        "edge_voice": edge_voice,
        "use_alt_player": use_alt_player,
        "force_gtts": force_gtts,
        "force_wav": force_wav
    }

    st.divider()
    st.markdown('<div class="block note"><small class="help">録音できない場合は「WebRTC録音（ベータ）」をONに。Safariは録音形式の制約が厳しいため端末差が出ます。</small></div>', unsafe_allow_html=True)

# ---------- ヘッダー ----------
st.markdown(f"## {ct.APP_NAME}")
st.markdown('<div class="mobile-tip">📱 スマホの方へ：左上の<strong>≡（メニュー）</strong>でサイドバーが開きます。</div>', unsafe_allow_html=True)
st.markdown('<div class="block note">英語 / 韓国語の会話練習・シャドーイング・ロールプレイ</div>', unsafe_allow_html=True)

# ---------- 共通ヘルパ ----------
def synth_and_player(text: str, lang_code: str, file_stub: str = "speech"):
    """
    1クリックで MP3 と WAV を両方用意し、<audio> に複数 <source> を埋め込む。
    ブラウザは再生可能な方を自動選択。
    """
    cfg = st.session_state.get(
        "tts_cfg",
        {"prefer_edge": False, "rate": 0, "edge_voice": None,
         "use_alt_player": True, "force_gtts": True, "force_wav": True}
    )

    # 1) MP3 を生成（gTTS強制可）
    mp3_bytes, mp3_mime = fn.tts_synthesize(
        text, lang_code=lang_code,
        rate_pct=cfg["rate"], prefer_edge=cfg["prefer_edge"],
        edge_voice=cfg["edge_voice"], force_wav=False, force_gtts=cfg["force_gtts"]
    )

    # 2) WAV を生成（ffmpeg が無い場合は mp3 のまま返る可能性あり）
    wav_bytes, wav_mime = fn.tts_synthesize(
        text, lang_code=lang_code,
        rate_pct=cfg["rate"], prefer_edge=cfg["prefer_edge"],
        edge_voice=cfg["edge_voice"], force_wav=cfg["force_wav"], force_gtts=cfg["force_gtts"]
    )

    # 3) ソースを組み立て（WAV優先→MP3）
    sources: list[tuple[str, bytes]] = []
    if wav_mime == "audio/wav" and isinstance(wav_bytes, (bytes, bytearray)) and len(wav_bytes) > 44:
        sources.append((wav_mime, wav_bytes))
    if isinstance(mp3_bytes, (bytes, bytearray)) and len(mp3_bytes) > 0:
        sources.append((mp3_mime, mp3_bytes))

    if not sources:
        st.error("音声の生成に失敗しました。サイドバーで「gTTSを強制」「WAVに変換」をONにして再試行してください。")
        return

    # 4) レンダリング
    if cfg.get("use_alt_player", True):
        # HTML <audio> に複数 <source> を埋め込み（playsinline で iOS 対策）
        html = '<audio controls preload="metadata" playsinline>'
        for mime, data in sources:
            b64 = base64.b64encode(data).decode("ascii")
            html += f'<source src="data:{mime};base64,{b64}" type="{mime}"/>'
        html += "</audio>"
        st.markdown(html, unsafe_allow_html=True)

        # ダウンロード（先頭ソース）
        top_mime, top_data = sources[0]
        ext = "wav" if top_mime == "audio/wav" else "mp3"
        st.download_button(
            "⬇️ 音声を保存（再生できない場合）",
            top_data, file_name=f"{file_stub}.{ext}", mime=top_mime,
            use_container_width=True
        )
    else:
        # Streamlit のネイティブプレーヤーは単一フォーマットしか渡せないので WAV を優先
        mime, data = sources[0]
        st.audio(data, format=mime)

# ---- WebRTC録音（ベータ）: 端末によっては mic_recorder が動かないための保険 ----
def record_audio_webrtc_once() -> bytes | None:
    try:
        from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration
        import av
    except Exception:
        st.warning("WebRTC録音を使うには 'streamlit-webrtc' と 'av' が必要です（requirements.txt に追加）。")
        return None

    rtc_conf = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})
    ctx = webrtc_streamer(
        key="webrtc_rec",
        mode=WebRtcMode.SENDONLY,  # クライアント→サーバへ送るだけ
        audio_receiver_size=256,
        media_stream_constraints={"video": False, "audio": True},
        rtc_configuration=rtc_conf,
    )

    # 連続フレーム一時バッファ
    if "webrtc_buf" not in st.session_state:
        st.session_state["webrtc_buf"] = []
        st.session_state["webrtc_rate"] = 48000

    col_a, col_b = st.columns(2)
    with col_a:
        st.caption("🎙️ WebRTC録音（ベータ）を開始→Safari等の録音不具合の保険")
    with col_b:
        stop = st.button("⏹️ 録音を停止して保存", use_container_width=True)

    if ctx.state.playing:
        # 受信フレームを随時追記
        frames = ctx.audio_receiver.get_frames(timeout=1)
        for f in frames:
            arr = f.to_ndarray(format="s16")  # 16bit PCM
            # arr の shape は実装により (channels, samples) or (samples, channels)
            if arr.ndim == 2:
                if arr.shape[0] < arr.shape[1]:  # (channels, samples)
                    mono = arr[0, :]
                else:  # (samples, channels)
                    mono = arr[:, 0]
            else:
                mono = arr
            st.session_state["webrtc_buf"].append(mono.tobytes())
            st.session_state["webrtc_rate"] = int(getattr(f, "sample_rate", 48000))

    if stop and st.session_state["webrtc_buf"]:
        # WAV にまとめる
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # s16
            wf.setframerate(st.session_state["webrtc_rate"])
            wf.writeframes(b"".join(st.session_state["webrtc_buf"]))
        data = buf.getvalue()
        st.session_state["webrtc_buf"] = []
        return data

    return None

def show_translation_if_needed(source_text_ko: str):
    if st.session_state.get("lang") == "ko" and show_trans and source_text_ko.strip():
        jp = fn.translate_text(source_text_ko, target_lang_label="Japanese")
        st.markdown('<div class="block tran">【日本語訳】<br>' + jp + '</div>', unsafe_allow_html=True)

# ========== 1) Daily Chat ==========
if st.session_state["mode"] == ct.ANSWER_MODE_DAILY:
    st.subheader("Daily Chat（フリートーク）")
    st.markdown('<div class="block note">スマホで音が出ない/録音できない場合はサイドバーの互換設定やWebRTC録音をお試しください。</div>', unsafe_allow_html=True)

    if "chat" not in st.session_state:
        st.session_state["chat"] = []

    for i, (who, text) in enumerate(st.session_state["chat"]):
        with st.chat_message(who):
            st.write(text)
            if who == "assistant":
                if st.session_state["lang"] == "ko":
                    show_translation_if_needed(text)
                if st.button("▶️ 再生", key=f"play_hist_{i}"):
                    synth_and_player(text, st.session_state["lang"], file_stub=f"reply_{i}")

    user_text = st.chat_input("メッセージを入力（日本語/英語/韓国語 OK）")
    if user_text:
        st.session_state["chat"].append(("user", user_text))
        with st.chat_message("user"):
            st.write(user_text)

        system_prompt = ct.system_prompt_for(ct.ANSWER_MODE_DAILY, st.session_state["lang"])
        reply = fn.chat_once(system_prompt, user_text, model=ct.OPENAI_MODEL)

        st.session_state["chat"].append(("assistant", reply))
        with st.chat_message("assistant"):
            st.write(reply)
            if st.session_state["lang"] == "ko":
                show_translation_if_needed(reply)

            if st.session_state.get("autoplay", False):
                synth_and_player(reply, st.session_state["lang"], file_stub="reply_new")
            else:
                if st.button("▶️ 再生", key=f"play_new_{len(st.session_state['chat'])}"):
                    synth_and_player(reply, st.session_state["lang"], file_stub="reply_new")

# ========== 2) Shadowing ==========
elif st.session_state["mode"] == ct.ANSWER_MODE_SHADOWING:
    st.subheader("Shadowing（音読・復唱）")

    c1, c2, c3 = st.columns(3)
    with c1:
        level = st.selectbox("難易度", ["easy", "normal", "hard"], index=0)
    with c2:
        repeat_n = st.number_input("回数（同じ文）", min_value=1, max_value=5, value=1, step=1)
    with c3:
        # 録音手段の選択（デフォは mic_recorder、動かないときはWebRTC）
        use_webrtc = st.toggle("WebRTC録音（ベータ）を使う", value=False)

    sents = ct.SHADOWING_CORPUS_KO[level] if st.session_state["lang"] == "ko" else ct.SHADOWING_CORPUS_EN[level]
    st.markdown("#### 例文（30件）")
    st.markdown("<div class='scroll-list'><ol>" + "".join(f"<li>{s}</li>" for s in sents) + "</ol></div>", unsafe_allow_html=True)

    st.markdown("---")
    idx = st.number_input("練習する文番号", min_value=1, max_value=len(sents), value=1, step=1)
    target = sents[idx - 1]

    st.markdown("##### 目標文")
    st.markdown(f'<div class="block">{target}</div>', unsafe_allow_html=True)

    b1, b2, _ = st.columns(3)
    with b1:
        if st.button("▶️ 合成音声を再生"):
            synth_and_player(target, st.session_state["lang"], file_stub=f"shadow_{level}_{idx}")
    with b2:
        wav_bytes = None
        if not use_webrtc:
            mic = mic_recorder(start_prompt="🎙️ 録音開始", stop_prompt="⏹️ 停止",
                               just_once=True, use_container_width=True, key=f"mic_{level}_{idx}")
            if mic and "bytes" in mic:
                wav_bytes = mic["bytes"]
        else:
            wav_bytes = record_audio_webrtc_once()

    if wav_bytes:
        recognizer = sr.Recognizer()
        try:
            with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
                audio = recognizer.record(source)
            transcribed = fn.stt_recognize_from_audio(audio, lang_code=st.session_state["lang"])
        except Exception:
            transcribed = ""

        st.markdown("##### あなたの発話（STT）")
        st.write(transcribed if transcribed else "(聞き取れませんでした)")

        ref = fn.normalize_for_compare(target)
        got = fn.normalize_for_compare(transcribed)
        ratio = difflib.SequenceMatcher(None, ref, got).ratio()
        score = int(ratio * 100)
        st.markdown(f"**スコア：{score} / 100**")

        if st.session_state["lang"] == "ko":
            st.markdown("##### 意味（参考）")
            show_translation_if_needed(target)

        if repeat_n > 1:
            st.info(f"同じ文を {repeat_n} 回練習してみましょう。")

# ========== 3) Roleplay ==========
elif st.session_state["mode"] == ct.ANSWER_MODE_ROLEPLAY:
    st.subheader("Roleplay（韓国語シナリオ）")

    labels = [x["label"] for x in ct.ROLEPLAY_SCENARIOS_KO]
    idx = st.selectbox("シナリオ", list(range(len(labels))), format_func=lambda i: labels[i], index=0)
    scenario = ct.ROLEPLAY_SCENARIOS_KO[idx]

    key = f"rp_{scenario['key']}"
    if key not in st.session_state:
        st.session_state[key] = []

    with st.expander("シナリオ開始例（韓国語）", expanded=False):
        st.markdown(f"- 例: {scenario['opening_user_ko']}")

    for i, (who, text) in enumerate(st.session_state[key]):
        with st.chat_message(who):
            st.write(text)
            if who == "assistant":
                show_translation_if_needed(text)
                if st.button("▶️ 再生", key=f"play_rp_hist_{i}"):
                    synth_and_player(text, "ko", file_stub=f"rp_{scenario['key']}_{i}")

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

            if st.session_state.get("autoplay", False):
                synth_and_player(reply, "ko", file_stub=f"rp_{scenario['key']}_new")
            else:
                if st.button("▶️ 再生", key=f"play_rp_new_{len(st.session_state[key])}"):
                    synth_and_player(reply, "ko", file_stub=f"rp_{scenario['key']}_new")
