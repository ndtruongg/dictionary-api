import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import SecretStr


@dataclass(frozen=True)
class Settings:
    supabase_url: str = ""
    supabase_publishable_key: SecretStr = field(default_factory=lambda: SecretStr(""), repr=False)
    supabase_timeout_seconds: float = 10.0
    cors_origins: tuple[str, ...] = ()

    def __post_init__(self):
        url = self.supabase_url.strip().rstrip("/")
        if url:
            try:
                parts = urlsplit(url)
                valid = (parts.scheme == "https" and bool(parts.hostname) and not parts.username
                         and not parts.password and not parts.path and not parts.query
                         and not parts.fragment and not any(c.isspace() for c in url))
                _ = parts.port
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("SUPABASE_URL cần HTTPS origin của project, không kèm path, query hay thông tin đăng nhập.")
        object.__setattr__(self, "supabase_url", url)
        if not 1 <= self.supabase_timeout_seconds <= 30:
            raise ValueError("SUPABASE_TIMEOUT_SECONDS cần nằm trong khoảng 1–30 giây.")
        for origin in self.cors_origins:
            parts = urlsplit(origin)
            if (parts.scheme not in {"http", "https"} or not parts.hostname
                    or parts.username or parts.password or parts.path
                    or parts.query or parts.fragment or "*" in origin):
                raise ValueError("CORS_ORIGINS cần origin chính xác, không có path, wildcard hoặc dấu / cuối.")
            _ = parts.port

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key.get_secret_value().strip())

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
        return cls(
            supabase_url=os.getenv("SUPABASE_URL", ""),
            supabase_publishable_key=SecretStr(os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()),
            supabase_timeout_seconds=float(os.getenv("SUPABASE_TIMEOUT_SECONDS", "10")),
            cors_origins=tuple(x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()),
        )
