from __future__ import annotations

import os
import re

REPLACEMENTS = [
    (re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)\s*[=:]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r'(?i)("username"\s*:\s*)"[^"]*"'), r'\1"[REDACTED]"'),
    (re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"), "[MAC_REDACTED]"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP_REDACTED]"),
]


def sanitize_text(text: str) -> str:
    home = str(os.path.expanduser("~"))
    if home:
        text = text.replace(home, "%USERPROFILE%")
    for pattern, replacement in REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text
