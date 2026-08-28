"""Input sanitizer — Part A §13, §9, T3-1.

Strips characters that could be used for LLM prompt injection before any
citizen-supplied text is passed to the LLM layer (Part A §9, §28).

Usage:

    from security.input_sanitizer import sanitize_text

    clean = sanitize_text(user_description)
"""
from __future__ import annotations

import re

# Characters / patterns that are meaningful to most LLM prompt templates
# and have no legitimate use in civic issue descriptions.
_INJECTION_PATTERN = re.compile(
    r"("
    r"<\|.*?\|>"          # special token delimiters (e.g. <|endoftext|>)
    r"|###"               # markdown heading commonly used as prompt separator
    r"|^system:"          # explicit role injection
    r"|^user:"
    r"|^assistant:"
    r"|\[INST\]"          # Llama instruction tags
    r"|<<SYS>>"
    r"|</s>"              # EOS token literal
    r")",
    re.IGNORECASE | re.MULTILINE,
)

_MAX_LENGTH = 2000  # mirrors ReportCreate.description max_length


def sanitize_text(text: str, max_length: int = _MAX_LENGTH) -> str:
    """Return *text* with LLM injection characters removed and length capped.

    - Strips special token delimiters and role-injection prefixes.
    - Trims leading/trailing whitespace.
    - Truncates to *max_length* characters.

    Args:
        text:       Raw user-supplied string.
        max_length: Maximum allowed character count (default 2000).

    Returns:
        Sanitized string safe for inclusion in LLM prompts.
    """
    cleaned = _INJECTION_PATTERN.sub("", text)
    cleaned = cleaned.strip()
    return cleaned[:max_length]
