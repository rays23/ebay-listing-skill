import re

NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalise(token: str) -> str:
    return NON_ALNUM.sub("", token.lower())


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(t for t in (_normalise(part) for part in text.split()) if t)


def title_matches(title: str, query: str, exclude: tuple[str, ...]) -> bool:
    lowered = title.lower()
    flat = NON_ALNUM.sub("", lowered)
    words = {w for w in NON_ALNUM.split(lowered) if w}
    exclude_tokens = tuple(t for t in (_normalise(e) for e in exclude) if t)
    return all(t in flat for t in _tokens(query)) and not any(t in words for t in exclude_tokens)
