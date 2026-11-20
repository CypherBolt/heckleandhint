"""Text safety filter for player-written text (team names, fun facts).

Two jobs:
1. Strip personal data (phone numbers, emails) BEFORE anything is stored.
2. Flag bad words (English + Vietnamese) so the host must approve the text.

Vietnamese words are matched WITH their accents, because stripping accents
creates false alarms (e.g. "lồn" -> "lon", but "lon" also means a can of beer).
"""
import re
import unicodedata

# English: matched as whole words, case-insensitive.
BAD_EN = {
    "fuck", "fucker", "fucking", "motherfucker", "shit", "bullshit", "bitch",
    "bastard", "asshole", "arsehole", "cunt", "dick", "dickhead", "cock",
    "pussy", "slut", "whore", "fag", "faggot", "retard", "nigger", "nigga",
    "twat", "wanker", "prick", "rape", "rapist", "nazi", "porn", "kys",
}

# Vietnamese with diacritics (substring match, after NFC normalisation).
BAD_VI_ACCENTED = {  # VI-CHECK: native speaker should review this list
    "đụ", "địt", "đéo", "lồn", "cặc", "buồi", "đĩ", "đm", "đcm", "đkm",
    "chó đẻ", "óc chó", "ngu như bò", "mẹ mày", "con điếm", "đồ điếm",
}

# Common no-accent Vietnamese slang abbreviations (whole-word match).
BAD_VI_PLAIN = {  # VI-CHECK
    "dm", "dcm", "dkm", "dmm", "vcl", "vkl", "vl", "clgt", "cmm", "dit me",
    "du ma", "deo", "loz", "cak",
}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", re.UNICODE)
# 8+ digits, allowing spaces/dots/dashes/parentheses/+ between them.
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{6,}\d)")
SOCIAL_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_.]{3,}")


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def redact_personal(text: str) -> tuple[str, bool]:
    """Replace emails / phone numbers / @handles with '•••'. Returns (text, changed)."""
    original = text
    text = EMAIL_RE.sub("•••", text)

    def _phone(m):
        digits = re.sub(r"\D", "", m.group(0))
        return "•••" if len(digits) >= 8 else m.group(0)

    text = PHONE_RE.sub(_phone, text)
    text = SOCIAL_RE.sub("•••", text)
    return text, text != original


def has_bad_words(text: str) -> bool:
    low = _nfc(text).lower()
    words = re.findall(r"[a-z0-9]+", low)
    # catch simple letter-spacing tricks like "f u c k"
    squashed = re.sub(r"[^a-z]", "", low)
    for w in words:
        if w in BAD_EN or w in BAD_VI_PLAIN:
            return True
    for bad in BAD_EN:
        if len(bad) >= 5 and bad in squashed:
            return True
    plain_join = " ".join(words)
    for bad in BAD_VI_PLAIN:
        if " " in bad and bad in plain_join:
            return True
    for bad in BAD_VI_ACCENTED:
        if bad in low:
            return True
    return False


def clean_text(text: str, limit: int) -> dict:
    """Trim, cap length, strip personal data and flag bad words."""
    text = _nfc((text or "").strip())
    text = re.sub(r"\s+", " ", text)[:limit]
    text, redacted = redact_personal(text)
    return {"text": text, "flagged": has_bad_words(text), "redacted": redacted}
