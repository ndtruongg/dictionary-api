import pytest
from pydantic import SecretStr

from app.config import Settings


@pytest.mark.parametrize("origin", ["*", "https://example.com/path", "https://example.com/", "https://user:pass@example.com", "https://example.com:bad"])
def test_reject_bad_origins(origin):
    with pytest.raises(ValueError):
        Settings(cors_origins=(origin,))


@pytest.mark.parametrize("url", ["http://example.com", "https://example.com/rest/v1", "https://user:pass@example.com",
                                    "https://example.com?key=bad", "https://example.com#fragment", "https://example.com:bad", "https://bad host"])
def test_reject_bad_supabase_url(url):
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        Settings(supabase_url=url)


@pytest.mark.parametrize("timeout", [0, 31, float("nan"), float("inf")])
def test_reject_bad_timeout(timeout):
    with pytest.raises(ValueError, match="SUPABASE_TIMEOUT_SECONDS"):
        Settings(supabase_timeout_seconds=timeout)


def test_missing_or_partial_config():
    assert not Settings().configured
    assert not Settings(supabase_url="https://example.supabase.co").configured
    assert not Settings(supabase_publishable_key=SecretStr("test")).configured


def test_env_and_secret_redaction(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("SUPABASE_URL", " https://example.supabase.co/ ")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_private_test")
    monkeypatch.setenv("SUPABASE_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("GEMINI_API_KEY", "unused-test-key")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    settings = Settings.from_env()
    assert settings.supabase_url == "https://example.supabase.co"
    assert settings.configured and settings.supabase_timeout_seconds == 12
    assert settings.cors_origins == ("http://localhost:3000",)
    assert "sb_publishable_private_test" not in repr(settings)
    assert "sb_publishable_private_test" not in str(settings.supabase_publishable_key)
    assert not hasattr(settings, "gemini_api_key")
