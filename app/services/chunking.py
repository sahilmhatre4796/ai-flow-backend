"""
Splits plain text into ~max_len-character chunks on sentence boundaries,
falling back to a hard wrap for any single run of text (e.g. no punctuation)
that alone exceeds max_len. This is the real chunking logic that determines
the chunk_index/content rows persisted in Postgres — there is no separate
"display" chunk count computed differently from what's actually stored.
"""
import re

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]*")


def chunk_text(text: str, max_len: int = 800) -> list[str]:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return []

    sentences = _SENTENCE_RE.findall(clean) or [clean]
    chunks: list[str] = []
    current = ""

    def flush():
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for sentence in sentences:
        s = sentence
        while len(s) > max_len:
            flush()
            chunks.append(s[:max_len].strip())
            s = s[max_len:]
        if len(current) + len(s) > max_len and current:
            flush()
            current = s
        else:
            current += s

    flush()
    return chunks
