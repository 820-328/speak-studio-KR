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

# 対応言語（英語/韓国語）
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

# 既定言語（韓国語練習を想定）
DEFAULT_LANG = "ko"

# LLMモデル（必要に応じて変更可）
OPENAI_MODEL = "gpt-5"
OPENAI_MODEL_MINI = "gpt-5-mini"

# =========================
# シャドーイング用：英語 30文×3段階
# =========================
SHADOWING_CORPUS_EN = {
    "easy": [
        "Hello.",
        "Nice to meet you.",
        "How are you today?",
        "I'm fine, thank you.",
        "What's your name?",
        "My name is Alex.",
        "Where are you from?",
        "I'm from Japan.",
        "Please speak slowly.",
        "Could you repeat that?",
        "I don't understand.",
        "That's okay.",
        "Thank you very much.",
        "See you tomorrow.",
        "Have a nice day.",
        "I'm learning English.",
        "This is my friend.",
        "I like coffee.",
        "Do you have time?",
        "It's very helpful.",
        "Can I take a photo?",
        "How much is this?",
        "Excuse me.",
        "No problem.",
        "I'm a beginner.",
        "Let’s start practice.",
        "I agree with you.",
        "It's interesting.",
        "Could you help me?",
        "I appreciate it.",
    ],
    "normal": [
        "I've been studying English more seriously recently.",
        "Could you recommend a good place to eat nearby?",
        "The meeting will start at two in the afternoon.",
        "I'd like to change my reservation if possible.",
        "Could you explain your proposal in more detail?",
        "I'm planning to meet my friends this weekend.",
        "Sorry for the late reply.",
        "I'll get back to you after reviewing the materials.",
        "I got a little lost, but I finally arrived.",
        "Our productivity has improved quite a lot.",
        "The app crashed, but I restarted it and it worked.",
        "Let me check the schedule and confirm later.",
        "We should compare a few options first.",
        "Could you share the document with me?",
        "I think that's a reasonable approach.",
        "Let's keep this explanation simple and clear.",
        "I need a bit more context to understand.",
        "Please let me know your preferred time.",
        "I'll send you the summary after the call.",
        "I missed your message earlier.",
        "We can iterate based on your feedback.",
        "Thanks for your patience.",
        "I'll try another method as a fallback.",
        "That sounds like a good plan to me.",
        "Please correct me if I'm wrong.",
        "What are the next steps from here?",
        "Let's prioritize the high-impact tasks.",
        "It's important to set clear expectations.",
        "I'll prepare a draft and share it soon.",
        "Could you clarify your main goal?",
    ],
    "hard": [
        "We need to evaluate cost-effectiveness from a long-term perspective.",
        "Incorporating user feedback and adjusting priorities is essential.",
        "The timeline slipped partly due to unexpected variables.",
        "Without proper data quality controls, metrics become unreliable.",
        "We should base decisions on transparent and measurable evidence.",
        "Cross-functional collaboration is critical for this initiative.",
        "Identify risks early and prepare mitigation strategies.",
        "Balance implementation effort and user impact carefully.",
        "Root-cause analysis should precede any permanent fixes.",
        "Expectation management is difficult without clear communication.",
        "Let's define acceptance criteria before development starts.",
        "We need a reproducible evaluation protocol for fairness.",
        "Please document all assumptions and dependencies explicitly.",
        "Align milestones with stakeholder expectations and resources.",
        "We should de-risk unknowns through small experiments.",
        "Benchmark against baselines to validate improvements.",
        "Ensure privacy and compliance in data handling.",
        "We need observability to detect regressions quickly.",
        "Let's separate critical path from nice-to-have tasks.",
        "Adopt a phased rollout to minimize disruptions.",
        "Quantify trade-offs between latency and accuracy.",
        "Create a feedback loop for continuous refinement.",
        "Establish SLAs and escalation procedures upfront.",
        "Design for failure and graceful degradation.",
        "Communicate limitations honestly to build trust.",
        "Track metrics that reflect user value, not vanity.",
        "Prefer simple solutions unless complexity is justified.",
        "Plan for localization and accessibility from the start.",
        "Document edge cases and fallback behaviors thoroughly.",
        "Retrospect and capture lessons learned after delivery.",
    ],
}

# =========================
# シャドーイング用：韓国語 30文×3段階
# =========================
SHADOWING_CORPUS_KO = {
    "easy": [
        "안녕하세요.",
        "처음 뵙겠습니다.",
        "오늘 기분이 어때요?",
        "괜찮아요, 감사합니다.",
        "이름이 뭐예요?",
        "저는 알렉스예요.",
        "어디에서 오셨어요?",
        "저는 일본에서 왔어요.",
        "천천히 말씀해 주세요.",
        "다시 한번 말씀해 주시겠어요?",
        "잘 이해하지 못했어요.",
        "알겠습니다.",
        "정말 감사합니다.",
        "내일 또 봬요.",
        "좋은 하루 보내세요.",
        "한국어를 공부하고 있어요.",
        "이쪽은 제 친구예요.",
        "저는 커피를 좋아해요.",
        "시간 괜찮으세요?",
        "많이 도움이 되네요.",
        "사진 찍어도 될까요?",
        "이거 얼마예요?",
        "실례합니다.",
        "괜찮습니다.",
        "저는 초보자예요.",
        "연습을 시작합시다.",
        "맞다고 생각해요.",
        "재미있네요.",
        "도와주실 수 있나요?",
        "감사하게 생각합니다.",
    ],
    "normal": [
        "요즘 한국어를 더 열심히 공부하고 있어요.",
        "근처에 맛있는 식당을 추천해 주실 수 있나요?",
        "회의는 오후 두 시에 시작할 예정이에요.",
        "가능하다면 예약을 변경하고 싶습니다.",
        "제안 내용을 좀 더 자세히 설명해 주시겠어요?",
        "이번 주말에는 친구들을 만날 계획이에요.",
        "답장이 늦어서 죄송합니다.",
        "자료를 검토한 뒤에 다시 연락드릴게요.",
        "길을 좀 헤맸지만 결국 도착했어요.",
        "생산성이 꽤 많이 향상된 것 같아요.",
        "앱이 중간에 꺼졌지만 다시 실행하니 괜찮았어요.",
        "일정을 확인하고 나중에 알려 드릴게요.",
        "먼저 몇 가지 옵션을 비교해 보죠.",
        "문서를 공유해 주실 수 있나요?",
        "그 접근 방식은 합리적이라고 생각해요.",
        "설명을 간단하고 명확하게 유지합시다.",
        "이해하려면 조금 더 배경이 필요해요.",
        "가능한 시간을 알려 주세요.",
        "통화 이후에 요약본을 보내 드릴게요.",
        "아까 메시지를 놓쳤습니다.",
        "피드バックを 바탕으로 점진적으로 개선하겠습니다.",
        "기다려 주셔서 감사합니다.",
        "대안 방법을 우선적으로 시도해 볼게요.",
        "좋은 계획처럼 들리네요.",
        "틀렸다면 바로 알려 주세요.",
        "여기서 다음 단계는 무엇일까요?",
        "영향이 큰 작업を 우선순위로 두겠습니다.",
        "기대치 설정이 중요합니다.",
        "초안을 만들어 곧 공유할게요.",
        "핵심 목표를 명확히 해 주실 수 있나요?",
    ],
    "hard": [
        "장기적인 관점에서 비용 대비 효율을 평가해야 합니다.",
        "사용자 피드バック을 반영해 우선순위를 조정하는 것이 중요합니다.",
        "예상치 못한 변수들 때문에 일정이 일부 지연되었습니다.",
        "데이터 품질 관리 없이는 지표의 신뢰성을 보장하기 어렵습니다.",
        "투명하고 측정 가능한 근거에 기반해 의사결정해야 합니다.",
        "이 이니셔티브는 부서 간 협업이 필수적입니다.",
        "위험 요소를 조기에 식별하고 완화 전략을 준비합시다.",
        "구현 난이도와 사용자 임팩트를 균형 있게 고려해야 합니다.",
        "지속적인 해결책 전에 근본 원인 분석이 필요합니다.",
        "명확한 커뮤니케이션 없이는 기대치 관리가 어렵습니다.",
        "개발 전에 수용 기준을 정의합시다.",
        "공정성을 위해 재현 가능한 평가 절차가 필요합니다.",
        "모든 가정과 의존성을 명시적으로 문서화해 주세요.",
        "마일스톤을 이해관계자의 기대와 리ソ스에 맞춰 정렬하세요.",
        "작은 실험을 통해 미지의 위험을 완화합시다.",
        "개선 효과는 기준선과의 비교로 검증해야 합니다.",
        "데이터 처리에서 개인정보와 규정을 준수해야 합니다.",
        "회귀를 빠르게 탐지할 수 있도록 가시성을 확보합시다.",
        "핵심 경로와 부가적 작업을 구분하세요.",
        "단계적 롤아웃으로 혼란을 최소화합시다.",
        "지연과 정확도 간의 트레이드오프를 정량화하세요.",
        "지속적 개선을 위한 피드백 루프를 구축하세요.",
        "SLA와 에스컬레이션 절차를 사전에 합의하세요.",
        "장애を 전제로 한 설계와 점진적 강건화를 고려하세요.",
        "한계를 솔직하게 공유해 신뢰를 구축하세요.",
        "허영 지표가 아닌 사용자 가치 지표를 추적하세요.",
        "불필요한 복잡성을 피하고 단순함을 우선하세요.",
        "현지화와 접근성을 초기에 계획하세요.",
        "エッジケースとフォールバックを徹底的に記録하세요.",
        "提供後に振り返りを行い、学びを定着させましょう。",
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
        return (f"You are a {lname} roleplay partner. Reply only in {lname}, short and natural.")
    return f"You are a helpful {lname} tutor."
