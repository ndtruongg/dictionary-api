from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Example(OutputModel):
    english: str | None = None
    vietnamese: str | None = None
    reference: str | None = None


class Pronunciation(OutputModel):
    ipa: str
    labels: list[str] = Field(default_factory=list)


class AudioClip(OutputModel):
    url: HttpUrl
    format: Literal["mp3", "ogg", "wav"]
    labels: list[str] = Field(default_factory=list)


class Sense(OutputModel):
    id: str | None = None
    glosses: list[str] = Field(default_factory=list, description="Giữ các cấp giải nghĩa theo thứ tự trong nguồn.")
    labels: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)


class Entry(OutputModel):
    headword: str
    source: str | None = None
    pos: str | None = None
    part_of_speech: str | None = None
    pronunciations: list[Pronunciation] = Field(default_factory=list)
    audio: list[AudioClip] = Field(default_factory=list)
    senses: list[Sense] = Field(default_factory=list)


class DictionaryResult(OutputModel):
    word: str
    normalized_word: str
    headword: str
    status: Literal["found"] = "found"
    provider: Literal["supabase"] = "supabase"
    source: Literal["public.dictionary"] = "public.dictionary"
    entries: list[Entry] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    code: str
    message: str
    retryable: bool


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    provider: Literal["supabase"] = "supabase"
    configured: bool = Field(description="Chỉ kiểm tra biến môi trường, không xác minh kết nối hoặc quyền đọc.")


ILLUSTRATIVE_RESULT = {
    "word": "beautiful", "normalized_word": "beautiful", "headword": "beautiful",
    "status": "found", "provider": "supabase", "source": "public.dictionary",
    "entries": [{"headword": "beautiful", "pos": "adj", "part_of_speech": "Tính từ",
                 "pronunciations": [{"ipa": "/ˈbjuːtɪ.fəl/", "labels": []}],
                 "senses": [{"id": None, "glosses": ["Đẹp; hay."], "labels": [], "topics": [], "examples": []}]}]
}
