import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_text(text: str) -> str:
    """NFKD, drop accents, lowercase, every non letter/digit becomes a space, collapse and trim.
    Used by both the seed and search, so the two always agree."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", without_accents.lower()).strip()
