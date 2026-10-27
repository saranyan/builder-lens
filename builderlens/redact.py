"""Scrub secrets and personal identifiers from text before it goes to any LLM.

Conservative by design: it would rather blank a harmless string than leak a key.
"""
import os
import re

_HOME = os.path.expanduser("~")

_RULES = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)"), "[PRIVATE_KEY]"),
    (re.compile(r"\bsk-(?:ant-|proj-|live-|test-)?[A-Za-z0-9_-]{16,}"), "[API_KEY]"),
    (re.compile(r"\b(?:ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}"), "[TOKEN]"),
    (re.compile(r"\bxox[abpors]-[A-Za-z0-9-]{10,}"), "[TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[AWS_KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), "[API_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"), "[JWT]"),
    (re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@/]+@"), "[URL_WITH_CREDENTIALS]@"),
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|token)"
                r"(\s*[:=]\s*|\s+is\s+)([\"']?)[^\s\"',;]{4,}\3"), r"\1\2[REDACTED]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "[EMAIL]"),
    (re.compile(r"\b(?:\+?\d{1,3}[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b[0-9a-fA-F]{40,}\b"), "[HEX]"),
]


def redact(text):
    if not text:
        return ""
    if _HOME and _HOME != "/":
        text = text.replace(_HOME, "~")
    for rx, sub in _RULES:
        text = rx.sub(sub, text)
    return text
