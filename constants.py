# -*- coding: utf-8 -*-
"""
SpeakStudio constants
- Languages, voices, prompts, corpora, scenarios
"""

APP_NAME = "SpeakStudio"

# 利用モード
ANSWER_MODE_DAILY = "daily_chat"
ANSWER_MODE_SHADOWING = "shadowing"
ANSWER_MODE_ROLEPLAY = "roleplay"

# 対応言語（英語は従来通り保持、今回は韓国語中心＋訳は日本語）
LANGS = {
    "en": {
        "label": "英語",
        "stt": "en-US",
        "tts": "en",
        "prompt_name": "English",
        "edge_voices": ["en-US-JennyNeural", "en-US-GuyNeural"],
    },
    "ko": {
        "label": "韓国語",
        "stt": "ko-KR",
        "tts": "ko",
        "prompt_name": "Korean",
        "edge_voices": ["ko-KR-SunHiNeural", "ko-KR-HyunsuNeural"],
    },
}

DEFAULT_LANG = "ko"  # 今回は韓国語練習をデフォルトに

# LLMモデル名（環境に合わせて変更可）
OPENAI_MODEL = "gpt-5"          # 高性能
OPENAI_MODEL_MINI = "gpt-5-mini"  # 軽量

# シャドーイング用：英語（サンプル最小）
SHADOWING_CORPUS_EN = {
    "easy": [
        "Hello, nice to meet you.",
        "Could you speak more slowly, please?",
        "Where are you from?",
    ],
    "normal": [
        "I have been studying English more seriously these days.",
        "Could you recommend a good place to eat around here?",
    ],
    "hard": [
        "We should evaluate the cost-effectiveness from a long-term perspective.",
        "Without proper data quality management, it is hard to trust the metrics.",
    ],
}

# シャドーイング用：韓国語（本命）
SHADOWING_CORPUS_KO = {
    "easy": [
        "안녕하세요. 처음 뵙겠습니다.",
        "천천히 말씀해 주세요.",
        "사진 찍어도 될까요?",
        "얼마인가요?",
        "감사합니다. 좋은 하루 되세요.",
    ],
    "normal": [
        "요즘 한국어를 열심히 공부하고 있어요.",
        "추천해 주실만한 맛집이 있을까요?",
        "예약을 변경하고 싶은데 가능할까요?",
        "연락이 늦어서 죄송합니다.",
        "자료를 검토한 후에 다시 연락드릴게요.",
    ],
    "hard": [
        "장기적인 관점에서 비용 대비 효율을 면밀히 검토해야 합니다.",
        "사용자 피드백을 반영해 우선순위를 조정하는 것이 중요합니다.",
        "데이터 품질 관리 없이는 신뢰할 수 있는 지표를 얻기 어렵습니다.",
        "구현 난이도와 사용자 임팩트를 균형 있게 고려하세요.",
        "명확한 커뮤니케이션 없이는 기대치 관리가 어렵습니다.",
    ],
}

# ロールプレイ韓国語シナリオ雛形
ROLEPLAY_SCENARIOS_KO = [
    {
        "key": "airport_checkin",
        "label": "空港：チェックイン",
        "system_prompt": (
            "あなたは航空会社の地上職員として振る舞います。会話はすべて韓国語です。"
            "丁寧で簡潔。ユーザーの韓国語学習を支援しつつ、現実的なダイアログを維持してください。"
            "一度の返答は短文2～3文程度に留めてください。"
        ),
        "opening_user_ko": "안녕하세요. 김포행 항공편 체크인하고 싶어요.",
    },
    {
        "key": "hotel_checkin",
        "label": "ホテル：チェックイン",
        "system_prompt": (
            "あなたはホテルのフロント係です。会話はすべて韓国語で行い、"
            "チェックイン手続き、本人確認、支払い、館内案内などを適切に進めてください。"
            "一度の返答は短文2～3文程度に留めてください。"
        ),
        "opening_user_ko": "안녕하세요. 오늘 체크인 예약했어요. 이름은 시마다 코헤이입니다.",
    },
    {
        "key": "biz_meeting",
        "label": "仕事MTG：要件確認",
        "system_prompt": (
            "あなたは韓国の取引先の担当者です。会話はすべて韓国語。"
            "会議の目的・スケジュール・必要資料・次アクションの確認を丁寧に進めてください。"
            "一度の返答は短文2～3文程度に留めてください。"
        ),
        "opening_user_ko": "안녕하세요. 오늘 미팅의 목적과 기대 결과를 먼저 확인하고 싶습니다.",
    },
]

# 役割プロンプト（モード別、言語別で利用）
def system_prompt_for(mode: str, lang_code: str) -> str:
    lname = LANGS.get(lang_code, LANGS[DEFAULT_LANG])["prompt_name"]
    if mode == ANSWER_MODE_DAILY:
        return (f"You are a friendly {lname} conversation partner for a Japanese learner. "
                f"Respond only in {lname}, keep it short and natural.")
    if mode == ANSWER_MODE_ROLEPLAY:
        # 個別シナリオで上書きする前提の基本
        return (f"You are a {lname} roleplay partner. Reply only in {lname}, short and natural.")
    return f"You are a helpful {lname} tutor."
