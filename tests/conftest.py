import copy

import httpx2
import pytest
from pydantic import SecretStr

from app.config import Settings


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError("Không được gọi mạng trong test")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)


@pytest.fixture
def settings():
    return Settings(supabase_url="https://dictionary.supabase.co",
                    supabase_publishable_key=SecretStr("sb_publishable_test_secret"))


@pytest.fixture
def records():
    """Fixture tổng hợp mô phỏng dữ liệu Wiktionary gốc trong cột JSONB."""
    return [
        {"word": "Beautiful", "lang_code": "en", "pos": "adj", "pos_title": "Tính từ",
         "sounds": [{"ipa": "/ˈbjuː.tɪ.fəl/", "tags": ["UK"]}, {"ipa": "/test/"},
                    {"audio": "source.ogg", "mp3_url": "https://upload.wikimedia.org/audio.mp3", "tags": ["UK"]}],
         "senses": [{"id": "sense-1", "glosses": ["Đẹp; hay."], "examples": [
             {"text": " A beautiful\n garden. ", "translation": "Một khu vườn đẹp."},
             {"text": "Another example.", "ref": "Synthetic reference"}]}]},
        {"word": "Beautiful", "lang_code": "en", "pos": "noun", "pos_title": "Danh từ",
         "senses": [{"glosses": ["Ngữ cảnh cha.", "Nghĩa con tổng hợp."], "tags": ["informal"],
                     "raw_tags": ["nhãn gốc"], "topics": ["test"],
                     "examples": [{"text": "Noun example.", "translation": "Ví dụ danh từ."}]}]},
        {"word": "look up", "lang_code": "en", "pos": "verb", "senses": [{"glosses": ["Tra cứu."]}]},
        {"word": "it's", "lang_code": "en", "senses": [{"glosses": ["Dạng rút gọn."]}]},
    ]


@pytest.fixture
def rows(records):
    from app.validation import normalize_key
    return [{"id": str(index), "word": record["word"], "lookup_key": normalize_key(record["word"]),
             "pos": record.get("pos", ""), "pos_title": record.get("pos_title", ""),
             "source": "Kaikki / Vietnamese Wiktionary", "data": copy.deepcopy(record)}
            for index, record in enumerate(records)]


def row_response(rows, offset=0, total=None):
    total = len(rows) if total is None else total
    content_range = f"{offset}-{offset + len(rows) - 1}/{total}" if rows else "*/0"
    return httpx2.Response(200, json=rows, headers={"content-range": content_range})


@pytest.fixture
def mock_supabase(monkeypatch, rows):
    calls = []
    clients = []
    def handler(request):
        calls.append(request)
        key = request.url.params["lookup_key"].removeprefix("eq.")
        matched = [row for row in rows if row["lookup_key"] == key]
        return row_response(matched)
    def factory(settings):
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        clients.append(client)
        return client
    monkeypatch.setattr("main.create_http_client", factory)
    return calls, clients
