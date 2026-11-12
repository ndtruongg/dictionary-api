import re
import unicodedata

from app.errors import APIError

# English words/phrases, contractions, possessives and hyphenated words.
WORD_PATTERN = re.compile(r"'?[a-z]+(?:['-][a-z]+)*'?(?: '?[a-z]+(?:['-][a-z]+)*'?)*", re.ASCII)


def normalize_key(raw: str) -> str:
    """Khóa so khớp dùng chung cho headword trong file và query."""
    word = unicodedata.normalize("NFKC", raw).translate(str.maketrans({"’": "'", "‘": "'", "‐": "-", "‑": "-"}))
    return " ".join(word.casefold().split())


def normalize_word(raw: str) -> str:
    if len(raw) > 512 or any(unicodedata.category(c) == "Cc" and not c.isspace() for c in raw):
        raise APIError(400, "INVALID_INPUT", "Đầu vào quá dài hoặc có ký tự điều khiển.")
    word = normalize_key(raw)
    if not 1 <= len(word) <= 120 or len(word.split()) > 12 or not WORD_PATTERN.fullmatch(word):
        raise APIError(400, "INVALID_INPUT", "Nhập từ/cụm từ tiếng Anh (tối đa 120 ký tự, 12 từ); cho phép dấu nháy và gạch nối, không nhận URL.")
    return word
