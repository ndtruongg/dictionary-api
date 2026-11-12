"""Đọc public.dictionary qua Supabase Data API; ánh xạ JSONB cho UI hiện có."""
import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import urlsplit

import httpx2
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings

from app.errors import APIError
from app.schemas import AudioClip, DictionaryResult, Entry, Example, Pronunciation, Sense
from app.validation import normalize_key

logger = logging.getLogger(__name__)


def text(value) -> str | None:
    if not isinstance(value, str):
        return None
    return " ".join(value.split()) or None


def texts(value) -> list[str]:
    return [clean for item in value if (clean := text(item))] if isinstance(value, list) else []


def objects(value) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def audio_url(value) -> str | None:
    """Chỉ trả URL HTTPS từ các host âm thanh có trong dataset đã kiểm tra."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        parts = urlsplit(value)
        if (parts.scheme == "https" and parts.hostname in {"upload.wikimedia.org", "commons.wikimedia.org"}
                and not parts.username and not parts.password and parts.port in {None, 443}):
            return value
    except ValueError:
        pass
    return None


def convert_record(record: dict) -> Entry:
    senses = []
    for sense in objects(record.get("senses")):
        examples = []
        for example in objects(sense.get("examples")):
            english, vietnamese = text(example.get("text")), text(example.get("translation"))
            if english or vietnamese:
                examples.append(Example(english=english, vietnamese=vietnamese, reference=text(example.get("ref"))))
        senses.append(Sense(
            id=text(sense.get("id")), glosses=texts(sense.get("glosses")),
            labels=list(dict.fromkeys(texts(sense.get("tags")) + texts(sense.get("raw_tags")))),
            topics=texts(sense.get("topics")), examples=examples,
        ))
    pronunciations = []
    audio = []
    seen_audio = set()
    for sound in objects(record.get("sounds")):
        labels = list(dict.fromkeys(texts(sound.get("tags")) + texts(sound.get("raw_tags"))))
        if ipa := text(sound.get("ipa")):
            pronunciations.append(Pronunciation(ipa=ipa, labels=labels))
        # Không ghép clip vào IPA ở dòng khác; giữ nhãn của chính sound này.
        for format in ("mp3", "ogg", "wav"):
            if url := audio_url(sound.get(f"{format}_url")):
                key = (url, tuple(labels))
                if key not in seen_audio:
                    audio.append(AudioClip(url=url, format=format, labels=labels))
                    seen_audio.add(key)
                break
    return Entry(headword=record["word"], pos=text(record.get("pos")),
                 part_of_speech=text(record.get("pos_title")) or text(record.get("pos")),
                 pronunciations=pronunciations, audio=audio, senses=senses)


class DictionaryRow(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str = Field(min_length=1)
    word: str = Field(min_length=1)
    lookup_key: str
    pos: str
    pos_title: str
    data: dict[str, Any]
    source: str


def create_http_client(settings: Settings) -> httpx2.AsyncClient:
    """Một connection pool cho mỗi lifespan; không retry hoặc đi theo redirect."""
    return httpx2.AsyncClient(
        timeout=httpx2.Timeout(settings.supabase_timeout_seconds, connect=5.0),
        transport=httpx2.AsyncHTTPTransport(
            retries=0, limits=httpx2.Limits(max_connections=20, max_keepalive_connections=10), trust_env=False,
        ),
        follow_redirects=False,
        trust_env=False,
    )


class SupabaseDictionary:
    PAGE_SIZE = 100
    MAX_ROWS = 1000
    MAX_BYTES = 8 * 1024 * 1024
    SELECT = "id,word,lookup_key,pos,pos_title,data,source"

    def __init__(self, settings: Settings, client: httpx2.AsyncClient):
        self.settings = settings
        self.client = client

    @staticmethod
    def fail(status: int, code: str, message: str, retryable: bool = False, upstream: int | None = None):
        # Không log body, header, key, URL hoặc chuỗi exception từ upstream.
        logger.warning("dictionary_lookup_failed code=%s upstream_status=%s", code, upstream)
        raise APIError(status, code, message, retryable)

    def check_status(self, status: int):
        if status in {200, 206}:
            return
        if status == 401:
            self.fail(503, "SUPABASE_AUTH_ERROR", "Supabase từ chối API key. Kiểm tra SUPABASE_PUBLISHABLE_KEY.", upstream=status)
        if status == 403:
            self.fail(503, "SUPABASE_PERMISSION_DENIED", "Chưa có quyền đọc từ điển trên Supabase. Kiểm tra quyền SELECT và RLS.", upstream=status)
        if status == 429:
            self.fail(429, "SUPABASE_RATE_LIMIT", "Supabase đang giới hạn lưu lượng. Vui lòng thử lại sau.", True, status)
        if status in {400, 404, 406, 416, 422}:
            self.fail(503, "SUPABASE_REQUEST_REJECTED", "Supabase từ chối truy vấn. Kiểm tra bảng public.dictionary, các cột và cấu hình Data API.", upstream=status)
        self.fail(502, "SUPABASE_UNAVAILABLE", "Dịch vụ từ điển tạm thời không khả dụng. Vui lòng thử lại sau.", True, status)

    async def lookup(self, word: str) -> DictionaryResult:
        if not self.settings.configured:
            self.fail(503, "SUPABASE_NOT_CONFIGURED", "Chưa cấu hình SUPABASE_URL và SUPABASE_PUBLISHABLE_KEY trên server.")
        try:
            # Deadline tổng, không gia hạn khi tải thêm trang.
            async with asyncio.timeout(self.settings.supabase_timeout_seconds):
                rows = await self.fetch_rows(word)
            if not rows:
                raise APIError(404, "WORD_NOT_FOUND", "Không tìm thấy từ hoặc cụm từ này trong từ điển.")
            entries = []
            seen_ids = set()
            for raw in rows:
                row = DictionaryRow.model_validate(raw)
                if (row.lookup_key != word or normalize_key(row.word) != word or row.id in seen_ids
                        or row.data.get("lang_code", "en") != "en"):
                    raise ValueError("Row does not match lookup")
                seen_ids.add(row.id)
                # Cột bảng là thông tin đầu mục chính; JSONB chứa sounds/senses gốc.
                record = {**row.data, "word": row.word, "pos": row.pos, "pos_title": row.pos_title}
                entry = convert_record(record)
                if not any(sense.glosses for sense in entry.senses):
                    raise ValueError("Missing definitions")
                entry.source = row.source
                entries.append(entry)
            return DictionaryResult(word=word, normalized_word=word, headword=entries[0].headword, entries=entries)
        except (TimeoutError, httpx2.TimeoutException):
            self.fail(504, "SUPABASE_TIMEOUT", "Hết thời gian chờ Supabase. Vui lòng thử lại.", True)
        except httpx2.RequestError:
            self.fail(502, "SUPABASE_UNAVAILABLE", "Không kết nối được dịch vụ từ điển. Vui lòng thử lại sau.", True)
        except (ValidationError, ValueError, TypeError):
            self.fail(502, "DICTIONARY_INVALID", "Dữ liệu từ điển trên Supabase không đúng cấu trúc. Vui lòng kiểm tra dữ liệu mục từ.")

    async def fetch_rows(self, word: str) -> list[dict]:
        headers = {
            "apikey": self.settings.supabase_publishable_key.get_secret_value().strip(),
            "Accept": "application/json", "Accept-Profile": "public", "Prefer": "count=exact",
        }
        rows = []
        total = None
        byte_count = 0
        while True:
            params = {"select": self.SELECT, "lookup_key": f"eq.{word}", "order": "id.asc",
                      "limit": str(self.PAGE_SIZE), "offset": str(len(rows))}
            async with self.client.stream("GET", f"{self.settings.supabase_url}/rest/v1/dictionary",
                                          headers=headers, params=params) as response:
                self.check_status(response.status_code)
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    byte_count += len(chunk)
                    if byte_count > self.MAX_BYTES:
                        self.fail(502, "DICTIONARY_TOO_LARGE", "Dữ liệu mục từ vượt giới hạn tải của ứng dụng.")
                    body.extend(chunk)
                try:
                    page = json.loads(body)
                    if not isinstance(page, list) or not all(isinstance(row, dict) for row in page):
                        raise ValueError("Expected rows")
                    # count=exact giúp không bỏ mất loại từ nếu Supabase giới hạn số dòng/trang.
                    content_range = response.headers.get("content-range", "")
                    if content_range == "*/0" and not rows and not page:
                        return []
                    match = re.fullmatch(r"(\d+)-(\d+)/(\d+)", content_range)
                    if not match or not page:
                        raise ValueError("Missing range")
                    start, end, count = map(int, match.groups())
                    if (start != len(rows) or end - start + 1 != len(page) or end >= count
                            or (total is not None and total != count)):
                        raise ValueError("Inconsistent range")
                    total = count
                except (ValueError, UnicodeError):
                    self.fail(502, "SUPABASE_INVALID_RESPONSE", "Supabase trả phản hồi không đúng cấu trúc hoặc phân trang không nhất quán.")
            if total > self.MAX_ROWS:
                self.fail(502, "DICTIONARY_TOO_LARGE", "Số mục cho từ này vượt giới hạn tải của ứng dụng.")
            rows.extend(page)
            if len(rows) == total:
                return rows


