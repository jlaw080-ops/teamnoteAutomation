import logging
import re
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Characters illegal in Windows filenames
ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')
MAX_FILENAME_LENGTH = 200


def build_note(template_path: str, parsed_data: dict) -> str:
    """Build an Obsidian markdown note from template and parsed email data.

    Args:
        template_path: Path to the Obsidian template file.
        parsed_data: Dict with keys: title, date, duration, sections, raw_body.

    Returns:
        Complete markdown note content as string.
    """
    template = _load_template(template_path)
    frontmatter = _render_frontmatter(template, parsed_data)
    body = _render_body(parsed_data)
    return frontmatter + "\n" + body


def _load_template(template_path: str) -> str:
    path = Path(template_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        logger.warning("Template file not found: %s. Using default template.", template_path)
        return _default_template()


def _default_template() -> str:
    return """---
tags:
  - Daily
related:
상태:
생성일: "<% tp.date.now("YYYY-MM-DD") %>"
updated: "<% tp.date.now("YYYY-MM-DD") %>"
---
---"""


def _render_frontmatter(template: str, parsed_data: dict) -> str:
    """Replace Templater variables in the template with actual values."""
    today = datetime.now().strftime("%Y-%m-%d")
    meeting_date = parsed_data.get("date", today) or today

    rendered = template

    # Replace Templater date expressions: <% tp.date.now("YYYY-MM-DD") %>
    rendered = re.sub(
        r'<%\s*tp\.date\.now\(["\']YYYY-MM-DD["\']\)\s*%>',
        meeting_date,
        rendered,
    )

    # Replace any other tp.date.now variants
    rendered = re.sub(
        r'<%\s*tp\.date\.now\([^)]*\)\s*%>',
        meeting_date,
        rendered,
    )

    return rendered


def _render_body(parsed_data: dict) -> str:
    """Render the meeting note body from parsed sections."""
    lines = []

    # Meeting info header
    title = parsed_data.get("title", "Untitled Meeting")
    date = parsed_data.get("date", "")
    duration = parsed_data.get("duration", "")

    if date or duration:
        info_parts = []
        if date:
            info_parts.append(f"**Date**: {date}")
        if duration:
            info_parts.append(f"**Duration**: {duration}")
        lines.append(" | ".join(info_parts))
        lines.append("")

    # Render sections
    sections: OrderedDict = parsed_data.get("sections", OrderedDict())
    if sections:
        for heading, content in sections.items():
            lines.append(f"## {heading}")
            lines.append("")
            lines.append(content)
            lines.append("")
    else:
        # Fallback: use raw body
        raw_body = parsed_data.get("raw_body", "")
        if raw_body:
            lines.append(raw_body)
            lines.append("")

    return "\n".join(lines)


def generate_filename(parsed_data: dict, filename_format: str) -> str:
    """Generate a sanitized filename for the Obsidian note.

    Args:
        parsed_data: Dict with title, date, etc.
        filename_format: Format string like "{date} {title}.md"

    Returns:
        Sanitized filename string.
    """
    title = parsed_data.get("title", "Untitled Meeting")
    date = parsed_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    duration = parsed_data.get("duration", "")

    filename = filename_format.format(
        date=date,
        title=title,
        duration=duration,
    )

    # Remove illegal Windows filename characters
    filename = ILLEGAL_FILENAME_CHARS.sub("", filename)

    # Truncate if too long (preserve .md extension)
    if len(filename) > MAX_FILENAME_LENGTH:
        base = filename[:-3]  # remove .md
        base = base[:MAX_FILENAME_LENGTH - 3]
        filename = base.rstrip() + ".md"

    return filename


def save_note(vault_path: str, filename: str, content: str) -> Path:
    """Save the note to the Obsidian vault.

    Returns:
        Path to the created file.
    """
    vault = Path(vault_path)
    filepath = vault / filename

    if filepath.exists():
        logger.warning("Note already exists, skipping: %s", filepath)
        return filepath

    vault.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Note created: %s", filepath)
    return filepath
