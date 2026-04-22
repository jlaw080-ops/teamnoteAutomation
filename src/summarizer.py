import logging

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 회의록 정리 전문가입니다. 주어진 회의록 내용을 다음 규칙에 따라 요약·정리해주세요.

## 규칙

1. **구조 유지**: 원본의 섹션(항목) 제목은 그대로 유지합니다.
2. **제목 서식**: 각 섹션 제목은 `## **제목**` 형식으로 굵게 표시합니다. 하위 항목 제목은 `### **제목**` 형식을 사용합니다.
3. **본문 요약**: 각 섹션의 본문 내용을 핵심만 간결하게 요약합니다. 불필요한 수식어나 반복을 제거하고, 핵심 사실과 결정사항만 남깁니다.
4. **본문 서식**: 본문에는 굵게(bold) 서식을 적용하지 않습니다. 단, 사람 이름이나 회사명 등 고유명사는 굵게 표시할 수 있습니다.
5. **불릿 리스트**: 본문은 가능한 불릿 리스트(`-`)로 정리합니다.
6. **한국어**: 모든 출력은 한국어로 작성합니다.
7. **Markdown만 출력**: 설명이나 부가 텍스트 없이, 정리된 Markdown 내용만 출력합니다."""

USER_PROMPT_TEMPLATE = """아래 회의록 내용을 규칙에 따라 요약·정리해주세요.

## 회의 정보
- 제목: {title}
- 날짜: {date}
- 시간: {duration}

## 회의록 원문
{body}"""


def summarize_meeting_notes(
    body: str,
    title: str,
    date: str,
    duration: str,
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """Summarize meeting notes using Claude API.

    Returns:
        Summarized and structured Markdown content.
    """
    client = anthropic.Anthropic(api_key=api_key)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=title,
        date=date,
        duration=duration,
        body=body,
    )

    logger.info("Sending meeting notes to Claude for summarization...")

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    result = message.content[0].text
    logger.info("Summarization complete (%d chars)", len(result))
    return result
