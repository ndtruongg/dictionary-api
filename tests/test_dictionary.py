import asyncio
import copy
from dataclasses import replace

import httpx2
import pytest

from app.config import Settings
from app.dictionary import SupabaseDictionary, audio_url, convert_record
from app.errors import APIError
from conftest import row_response


def lookup(settings, handler, word="beautiful"):
    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            return await SupabaseDictionary(settings, client).lookup(word)
    return asyncio.run(run())


def test_exact_query_and_all_entries_keep_example_ownership(settings, rows):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.scheme == "https" and request.url.host == "dictionary.supabase.co"
        assert request.url.path == "/rest/v1/dictionary"
        assert dict(request.url.params) == {"select": SupabaseDictionary.SELECT, "lookup_key": "eq.beautiful",
                                            "order": "id.asc", "limit": "100", "offset": "0"}
        assert request.headers["apikey"] == settings.supabase_publishable_key.get_secret_value()
        assert "authorization" not in request.headers
        assert request.headers["accept-profile"] == "public"
        assert request.headers["prefer"] == "count=exact"
        return row_response(rows[:2])
    result = lookup(settings, handler)
    assert len(calls) == 1
    assert result.headword == "Beautiful" and len(result.entries) == 2
    adjective, noun = result.entries
    assert adjective.part_of_speech == "Tính từ"
    assert adjective.source == "Kaikki / Vietnamese Wiktionary"
    assert adjective.senses[0].examples[0].english == "A beautiful garden."
    assert adjective.senses[0].examples[0].vietnamese == "Một khu vườn đẹp."
    assert len(adjective.senses[0].examples) == 2
    assert noun.senses[0].examples[0].english == "Noun example."
    assert noun.senses[0].glosses == ["Ngữ cảnh cha.", "Nghĩa con tổng hợp."]
    assert noun.senses[0].labels == ["informal", "nhãn gốc"]
    assert noun.senses[0].topics == ["test"]
    assert "sb_publishable_test_secret" not in result.model_dump_json()


def test_all_ipa_and_audio_preserved_with_own_labels(records):
    entry = convert_record(records[0])
    assert [(p.ipa, p.labels) for p in entry.pronunciations] == [("/ˈbjuː.tɪ.fəl/", ["UK"]), ("/test/", [])]
    assert len(entry.audio) == 1
    assert str(entry.audio[0].url) == "https://upload.wikimedia.org/audio.mp3"
    assert entry.audio[0].format == "mp3" and entry.audio[0].labels == ["UK"]


def test_missing_optional_fields(records):
    entry = convert_record(records[2])
    assert entry.part_of_speech == "verb" and entry.pronunciations == []
    assert entry.senses[0].examples == [] and entry.senses[0].id is None
    assert entry.audio == []


def test_column_metadata_overrides_jsonb_metadata(settings, rows):
    row = copy.deepcopy(rows[0])
    row["data"].update(word="wrong", pos="wrong", pos_title="wrong")
    result = lookup(settings, lambda r: row_response([row]))
    assert result.headword == "Beautiful"
    assert result.entries[0].pos == "adj" and result.entries[0].part_of_speech == "Tính từ"


def test_audio_formats_duplicates_and_no_invented_urls():
    entry = convert_record({"word": "test", "sounds": [
        {"mp3_url": "https://upload.wikimedia.org/a.mp3", "ogg_url": "https://commons.wikimedia.org/a.ogg", "raw_tags": ["Mỹ"]},
        {"mp3_url": "https://upload.wikimedia.org/a.mp3", "raw_tags": ["Mỹ"]},
        {"ogg_url": "https://commons.wikimedia.org/b.ogg"},
        {"wav_url": "https://commons.wikimedia.org/c.wav"},
        {"audio": "filename-only.ogg"},
    ]})
    assert [clip.format for clip in entry.audio] == ["mp3", "ogg", "wav"]
    assert entry.audio[0].labels == ["Mỹ"]
    assert len(entry.audio) == 3


@pytest.mark.parametrize("value", [None, "", "javascript:alert(1)", "http://upload.wikimedia.org/x.mp3",
    "https://evil.test/a.mp3", "https://upload.wikimedia.org.evil.test/x.mp3",
    "https://user:pass@upload.wikimedia.org/x.mp3", "https://upload.wikimedia.org:8443/x.mp3"])
def test_invalid_audio_urls_are_not_exposed(value):
    assert audio_url(value) is None


def test_not_found_does_not_fallback(settings):
    calls = []
    def handler(request):
        calls.append(request)
        return row_response([])
    with pytest.raises(APIError) as error:
        lookup(settings, handler, "absent")
    assert error.value.status == 404 and error.value.code == "WORD_NOT_FOUND"
    assert len(calls) == 1


def test_pagination_respects_server_row_cap(settings, rows):
    calls = []
    def handler(request):
        offset = int(request.url.params["offset"])
        calls.append(offset)
        # Server chỉ trả 1 dòng mặc dù client yêu cầu 100.
        return row_response(rows[offset:offset + 1], offset=offset, total=2)
    assert len(lookup(settings, handler).entries) == 2
    assert calls == [0, 1]


@pytest.mark.parametrize("status,code,http_status,retryable", [
    (401, "SUPABASE_AUTH_ERROR", 503, False), (403, "SUPABASE_PERMISSION_DENIED", 503, False),
    (400, "SUPABASE_REQUEST_REJECTED", 503, False), (404, "SUPABASE_REQUEST_REJECTED", 503, False),
    (406, "SUPABASE_REQUEST_REJECTED", 503, False), (416, "SUPABASE_REQUEST_REJECTED", 503, False),
    (429, "SUPABASE_RATE_LIMIT", 429, True), (500, "SUPABASE_UNAVAILABLE", 502, True),
    (503, "SUPABASE_UNAVAILABLE", 502, True), (302, "SUPABASE_UNAVAILABLE", 502, True),
])
def test_status_mapping_no_retry_or_sensitive_logs(settings, caplog, status, code, http_status, retryable):
    calls = []
    secret = settings.supabase_publishable_key.get_secret_value()
    def handler(request):
        calls.append(request)
        return httpx2.Response(status, json={"message": secret + " database-sensitive-detail"},
                               headers={"Location": "https://other.example"})
    with pytest.raises(APIError) as error:
        lookup(settings, handler)
    assert (error.value.code, error.value.status, error.value.retryable) == (code, http_status, retryable)
    assert len(calls) == 1
    output = caplog.text + str(error.value.payload())
    assert secret not in output and "database-sensitive-detail" not in output
    assert code in caplog.text


@pytest.mark.parametrize("exception,code,status", [
    (httpx2.ReadTimeout, "SUPABASE_TIMEOUT", 504), (httpx2.ConnectTimeout, "SUPABASE_TIMEOUT", 504),
    (httpx2.ConnectError, "SUPABASE_UNAVAILABLE", 502),
])
def test_transport_errors_are_safe(settings, caplog, exception, code, status):
    calls = []
    def handler(request):
        calls.append(request)
        raise exception("sb_publishable_test_secret private details", request=request)
    with pytest.raises(APIError) as error:
        lookup(settings, handler)
    assert error.value.code == code and error.value.status == status
    assert len(calls) == 1
    assert "sb_publishable_test_secret" not in caplog.text + str(error.value)


def test_total_deadline(settings):
    async def handler(request):
        await asyncio.sleep(2)
        return row_response([])
    with pytest.raises(APIError) as error:
        lookup(replace(settings, supabase_timeout_seconds=1), handler)
    assert error.value.code == "SUPABASE_TIMEOUT"


@pytest.mark.parametrize("patch", [
    {"data": "not an object"}, {"data": {}}, {"data": {"senses": []}}, {"word": 123},
    {"word": "another"}, {"lookup_key": "another"}, {"pos": None},
    {"data": {"lang_code": "fr", "senses": [{"glosses": ["Bonjour"]}]}},
])
def test_invalid_row_is_explicit_error(settings, rows, patch):
    row = {**rows[0], **patch}
    with pytest.raises(APIError) as error:
        lookup(settings, lambda r: row_response([row]))
    assert error.value.code == "DICTIONARY_INVALID" and error.value.status == 502


@pytest.mark.parametrize("body,content_range", [
    (b"not json", "0-0/1"), (b"null", "*/0"), (b"{}", "*/0"),
    (b"[1]", "0-0/1"), (b"[]", ""), (b"[]", "0-0/1"),
    (b"[{}]", "0-0/*"), (b"[{}]", "1-1/2"), (b"[{}]", "0-2/3"),
])
def test_invalid_api_response(settings, body, content_range):
    with pytest.raises(APIError) as error:
        lookup(settings, lambda r: httpx2.Response(200, content=body, headers={"content-range": content_range}))
    assert error.value.code == "SUPABASE_INVALID_RESPONSE"


def test_duplicate_rows_rejected(settings, rows):
    with pytest.raises(APIError) as error:
        lookup(settings, lambda r: row_response([rows[0], rows[0]]))
    assert error.value.code == "DICTIONARY_INVALID"


def test_limits_fail_without_truncation(settings, rows, monkeypatch):
    monkeypatch.setattr(SupabaseDictionary, "MAX_ROWS", 1)
    with pytest.raises(APIError) as error:
        lookup(settings, lambda r: row_response(rows[:2]))
    assert error.value.code == "DICTIONARY_TOO_LARGE"
    monkeypatch.setattr(SupabaseDictionary, "MAX_BYTES", 1)
    with pytest.raises(APIError) as error:
        lookup(settings, lambda r: row_response(rows[:1]))
    assert error.value.code == "DICTIONARY_TOO_LARGE"


def test_missing_config_no_request():
    def forbidden(request):
        raise AssertionError("Missing config must not call Supabase")
    with pytest.raises(APIError) as error:
        lookup(Settings(), forbidden)
    assert error.value.code == "SUPABASE_NOT_CONFIGURED"


def test_async_parallel_lookups_do_not_mix_words(settings, rows):
    async def handler(request):
        await asyncio.sleep(0)
        key = request.url.params["lookup_key"].removeprefix("eq.")
        return row_response([row for row in rows if row["lookup_key"] == key])
    async def run():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            source = SupabaseDictionary(settings, client)
            words = ["beautiful", "look up", "it's"] * 5
            results = await asyncio.gather(*(source.lookup(word) for word in words))
            assert [result.word for result in results] == words
    asyncio.run(run())
