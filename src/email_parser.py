import logging
import re
from collections import OrderedDict

logger = logging.getLogger(__name__)

# Known section headings (ordered longest-first to prevent partial matches)
SECTION_HEADINGS = [
    # Korean (Format A)
    "부서별/담당자별 업무 보고",
    "다음 단계 및 실행 항목",
    "주요 결정사항",
    "회의 개요",
    # English (Format B)
    "Key Discussion Points",
    "Technical Deep Dive",
    "Executive Summary",
    "Timeline Analysis",
    "Meeting Overview",
    "Key Decisions",
    "Action Items",
    # Variants
    "기타 사업 개발 및 외부 협력",
]


def parse_email(subject: str, body: str) -> dict:
    """Parse a Genspark meeting notes email into structured data.

    Returns:
        dict with keys: title, date, duration, sections (OrderedDict), raw_body
    """
    title = _extract_title_from_subject(subject)
    metadata = _extract_metadata(body)
    content_body = _extract_content_body(body)

    # If the body already has Markdown formatting (headings, lists),
    # skip section splitting and preserve the original structure.
    if _has_markdown_formatting(content_body):
        sections = OrderedDict()
    else:
        sections = _split_into_sections(content_body)

    return {
        "title": title,
        "date": metadata.get("date", ""),
        "duration": metadata.get("duration", ""),
        "sections": sections,
        "raw_body": content_body,
    }


def _has_markdown_formatting(content: str) -> bool:
    """Check if content already has Markdown formatting to preserve."""
    # Detect presence of markdown headings, lists, or bold
    return bool(
        re.search(r"^#{1,6}\s", content, re.MULTILINE)
        or re.search(r"^\s*[-*+]\s", content, re.MULTILINE)
        or re.search(r"^\s*\d+\.\s", content, re.MULTILINE)
        or "**" in content
    )


def _extract_title_from_subject(subject: str) -> str:
    prefix = "Meeting Notes:"
    if prefix in subject:
        return subject.split(prefix, 1)[1].strip()
    return subject.strip()


def _extract_metadata(body: str) -> dict:
    metadata = {}

    # Extract date: supports "Date\nYYYY-MM-DD", "Date: YYYY-MM-DD", "Date| YYYY-MM-DD"
    date_match = re.search(r"\*?\*?Date\*?\*?[\n\t\s:|]+(\d{4}-\d{2}-\d{2})", body)
    if date_match:
        metadata["date"] = date_match.group(1)

    # Extract duration: supports various separators
    duration_match = re.search(r"\*?\*?Duration\*?\*?[\n\t\s:|]+(\d+\s*mins?)", body)
    if duration_match:
        metadata["duration"] = duration_match.group(1)

    return metadata


def _extract_content_body(body: str) -> str:
    """Strip header preamble and footer, returning only the main content."""
    # Find the end of the metadata block
    duration_match = re.search(r"\*?\*?Duration\*?\*?[\n\t\s:|]+\d+\s*mins?", body)
    if duration_match:
        content_start = duration_match.end()
    else:
        # Fallback: find first section heading (account for leading ## prefix)
        heading_pattern = "|".join(re.escape(h) for h in SECTION_HEADINGS)
        heading_match = re.search(r"(#{1,6}\s+)?(" + heading_pattern + r")", body)
        if heading_match:
            content_start = heading_match.start()
        else:
            content_start = 0

    # Strip footer (www.genspark.ai and trailing whitespace)
    footer_match = re.search(r"\n*(?:www\.)?genspark\.ai", body)
    if footer_match:
        content_end = footer_match.start()
    else:
        content_end = len(body)

    content = body[content_start:content_end].strip()

    # Remove leftover preamble patterns (AI Meeting Notes, Generated, etc.)
    # that may appear at the top after conversion
    lines = content.split("\n")
    cleaned = []
    skip_patterns = [
        r"^\s*(?:Genspark\s+)?AI Meeting Notes\s*$",
        r"^\s*Generated\s*$",
        r"^\s*\d{4}-\d{2}-\d{2}\s*$",
    ]
    for line in lines:
        if any(re.match(p, line) for p in skip_patterns):
            continue
        cleaned.append(line)

    return "\n".join(cleaned).strip()


def _split_into_sections(content: str) -> OrderedDict:
    """Split content body into sections using known heading patterns."""
    if not content:
        return OrderedDict()

    # Build regex pattern with all known headings (longest first)
    sorted_headings = sorted(SECTION_HEADINGS, key=len, reverse=True)
    heading_pattern = "|".join(re.escape(h) for h in sorted_headings)
    pattern = f"({heading_pattern})"

    parts = re.split(pattern, content)

    sections = OrderedDict()

    # parts[0] is text before any heading (usually empty or whitespace)
    # Then alternating: heading, content, heading, content, ...
    i = 1
    while i < len(parts) - 1:
        heading = parts[i].strip()
        raw_content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        formatted = _format_section_content(heading, raw_content)
        sections[heading] = formatted
        i += 2

    # If no sections were found, use the entire content as a single section
    if not sections and content.strip():
        sections["내용"] = _format_plain_content(content.strip())

    return sections


def _format_section_content(heading: str, raw_content: str) -> str:
    """Format raw section content into readable markdown.

    Handles inline sub-headings (person tags, numbered items) that appear
    without line breaks in the email body.
    """
    TITLES = r"팀장|이사|박사|과장|대리|부장|사원|교수님|총괄"

    # Common Korean surnames for validating person names
    SURNAME_SET = set(
        "김이박최정강조윤장임한오서신권황안송전홍"
        "류고문양손배백허유남심노하곽성차주우민진"
    )

    text = raw_content

    # Find " title:" positions and work backwards to find person names.
    title_colon_pattern = re.compile(
        r"(?:" + TITLES + r")"
        r"(?:\s*&\s*[^\n:]{1,20}(?:" + TITLES + r"|개발팀))?"
        r"\s*[:：]"
    )

    inserts = []
    for m in title_colon_pattern.finditer(text):
        title_start = m.start()
        pos = title_start - 1
        if pos < 0 or text[pos] != " ":
            continue
        pos -= 1  # skip space

        # Try name lengths 1, 2, 3 (Korean names): prefer the one
        # starting with a valid surname character
        candidates = []
        name_end = pos + 1
        for length in range(1, 4):
            start = name_end - length
            if start < 0:
                break
            char = text[start]
            if not re.match(r"[가-힣]", char):
                break
            if char in SURNAME_SET:
                candidates.append(start)

        if not candidates:
            continue

        # Pick the candidate with the longest name that starts with a surname
        # But prefer shorter names when preceded by Korean text (word boundary)
        best = candidates[-1]  # longest name with valid surname
        for cand in candidates:
            # If preceded by non-Korean or line boundary, this is likely correct
            if cand == 0 or not re.match(r"[가-힣]", text[cand - 1]):
                best = cand
                break
        # If all candidates are preceded by Korean, use the shortest (1-char surname)
        else:
            best = candidates[0]

        if best > 0 and text[best - 1] != "\n":
            inserts.append(best)
        elif best == 0:
            inserts.append(0)

    # Insert newlines from end to start to preserve positions
    for pos in sorted(set(inserts), reverse=True):
        if pos > 0:
            text = text[:pos] + "\n" + text[pos:]

    # Split inline numbered items after period: "합니다.2. 기술적"
    text = re.sub(r"\.(\d+\.\s+)", r".\n\1", text)

    lines = text.split("\n")
    formatted_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for person-tagged sub-sections (e.g., "김 팀장: 프로젝트 관리")
        person_match = re.match(
            r"^(.{1,15}(?:팀장|이사|박사|과장|대리|부장|사원|교수님|총괄|개발팀))\s*[:：&]\s*(.+)",
            line,
        )
        if person_match:
            formatted_lines.append(f"\n### {person_match.group(1).strip()}")
            formatted_lines.append(person_match.group(2).strip())
            continue

        # Check for numbered items at the start
        num_match = re.match(r"^(\d+)\.\s+(.+)", line)
        if num_match:
            formatted_lines.append(f"\n### {num_match.group(1)}. {num_match.group(2)}")
            continue

        formatted_lines.append(line)

    result = "\n".join(formatted_lines).strip()

    # Clean up excessive newlines
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result


def _format_plain_content(content: str) -> str:
    """Format content that doesn't have recognized section headings."""
    lines = content.split("\n")
    formatted = []
    for line in lines:
        line = line.strip()
        if line:
            formatted.append(line)
    return "\n".join(formatted)
