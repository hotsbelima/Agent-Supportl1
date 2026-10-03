from fastapi.testclient import TestClient

from phase2_backend.app import create_app


def test_health_exposes_only_non_secret_runtime_status() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["phase"] == 2
    assert response.json()["model"] == "gemini-3.5-flash-lite"


def test_openapi_does_not_contain_google_api_key() -> None:
    response = TestClient(create_app()).get("/openapi.json")

    assert response.status_code == 200
    assert "GOOGLE_API_KEY" not in response.text
    assert "/spike/runs" in response.json()["paths"]
