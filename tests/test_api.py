import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from main import create_app


def test_lookup_health_static_and_client_lifecycle(settings, mock_supabase):
    calls, clients = mock_supabase
    with TestClient(create_app(settings)) as api:
        assert calls == []  # startup không truy cập Supabase
        health = api.get("/api/health")
        assert health.json() == {"status": "ok", "provider": "supabase", "configured": True}
        for path in ["/", "/docs", "/openapi.json", "/static/app.js", "/static/style.css"]:
            assert api.get(path).status_code == 200
        assert calls == []  # health và UI không gọi DB
        result = api.get("/api/dictionary", params={"word": "  BEAUTIFUL "})
        assert result.status_code == 200
        data = result.json()
        assert data["word"] == "beautiful" and data["headword"] == "Beautiful"
        assert data["provider"] == "supabase" and data["source"] == "public.dictionary"
        assert "model" not in data and "ai_generated" not in data
        assert len(data["entries"]) == 2
        assert data["entries"][0]["source"] == "Kaikki / Vietnamese Wiktionary"
        assert data["entries"][0]["audio"][0]["format"] == "mp3"
        assert result.headers["cache-control"] == "no-store"
        assert len(calls) == 1
        absent = api.get("/api/dictionary?word=absent")
        assert absent.status_code == 404 and absent.json()["code"] == "WORD_NOT_FOUND"
        assert "sb_publishable_test_secret" not in result.text + health.text + absent.text
    assert all(client.is_closed for client in clients)


def test_phrase_and_curly_apostrophe(settings, mock_supabase):
    with TestClient(create_app(settings)) as api:
        assert api.get("/api/dictionary", params={"word": " look   UP "}).json()["headword"] == "look up"
        assert api.get("/api/dictionary", params={"word": "IT’S"}).json()["headword"] == "it's"
    assert [r.url.params["lookup_key"] for r in mock_supabase[0]] == ["eq.look up", "eq.it's"]


@pytest.mark.parametrize("query", ["", "?word=", "?word=https%3A%2F%2Fevil.test", "?word=" + "a" * 513, "?word=test%26or%3Dtrue"])
def test_invalid_input_never_queries_database(settings, mock_supabase, query):
    with TestClient(create_app(settings)) as api:
        response = api.get("/api/dictionary" + query)
        assert response.status_code in {400, 422}
        assert response.json()["code"] == "INVALID_INPUT"
    assert mock_supabase[0] == []


def test_missing_config_serves_clear_error_and_ui(mock_supabase):
    with TestClient(create_app(Settings())) as api:
        assert api.get("/").status_code == 200
        assert api.get("/api/health").json()["configured"] is False
        error = api.get("/api/dictionary?word=beautiful")
        assert error.status_code == 503
        assert error.json()["code"] == "SUPABASE_NOT_CONFIGURED"
        assert set(error.json()) == {"code", "message", "retryable"}
    assert mock_supabase[0] == []


def test_cors_and_openapi(settings, mock_supabase):
    from dataclasses import replace
    with TestClient(create_app(replace(settings, cors_origins=("http://localhost:3000",)))) as api:
        response = api.get("/api/health", headers={"origin": "http://localhost:3000"})
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "access-control-allow-origin" not in api.get("/api/health", headers={"origin": "https://evil.test"}).headers
        schema = api.get("/openapi.json").json()
        assert "DictionaryResult" in schema["components"]["schemas"]
        assert "supabase" in str(schema)
        assert "sb_publishable_test_secret" not in str(schema)
        assert "504" in schema["paths"]["/api/dictionary"]["get"]["responses"]


@pytest.mark.parametrize("upstream,status,code", [(401, 503, "SUPABASE_AUTH_ERROR"),
                                                (429, 429, "SUPABASE_RATE_LIMIT"),
                                                (503, 502, "SUPABASE_UNAVAILABLE")])
def test_upstream_errors_reach_client_safely(monkeypatch, settings, upstream, status, code):
    import httpx2
    def factory(settings):
        return httpx2.AsyncClient(transport=httpx2.MockTransport(
            lambda request: httpx2.Response(upstream, text="sb_publishable_test_secret private-error-body")))
    monkeypatch.setattr("main.create_http_client", factory)
    with TestClient(create_app(settings)) as api:
        response = api.get("/api/dictionary?word=beautiful")
        assert response.status_code == status
        assert response.json()["code"] == code
        assert set(response.json()) == {"code", "message", "retryable"}
        assert response.headers["cache-control"] == "no-store"
        assert "sb_publishable_test_secret" not in response.text
        assert "private-error-body" not in response.text
