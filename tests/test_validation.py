import pytest

from app.errors import APIError
from app.validation import normalize_word


@pytest.mark.parametrize(("raw", "expected"), [
    ("  Beautiful  ", "beautiful"), ("look\t UP", "look up"),
    ("mother-in-law", "mother-in-law"), ("It’s", "it's"), ("dogs'", "dogs'"),
    ("rock 'n' roll", "rock 'n' roll"), ("ｂｅａｕｔｉｆｕｌ", "beautiful"),
])
def test_normalization(raw, expected):
    assert normalize_word(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "a" * 121, "a " * 13, "x" * 513,
    "https://evil.test/a", "//evil.test", "../../secret", "word?url=x", "a%2fb", "abc123", "a\x00b", "<script>", "café"])
def test_reject_invalid_input(raw):
    with pytest.raises(APIError) as error:
        normalize_word(raw)
    assert error.value.code == "INVALID_INPUT"
