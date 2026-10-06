from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from product_api.app import create_app
from product_api.public_demo import PublicDemoSettings


PUBLIC_TENANT = "TENANT-PUBLIC-DEMO"
ATTACKER_TENANT = "TENANT-EDITED-IN-BROWSER"
DEMO_ORIGIN = "https://agent-demo.example"


def _settings(*, cooldown: float = 60.0) -> PublicDemoSettings:
    return PublicDemoSettings(
        enabled=True,
        tenant_id=PUBLIC_TENANT,
        run_start_cooldown_seconds=cooldown,
    )


def _headers(tenant_id: str = ATTACKER_TENANT) -> dict[str, str]:
    return {"X-Tenant-ID": tenant_id}


def _require_database() -> None:
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is required for Product API integration tests")


def test_public_demo_requires_explicit_exact_frontend_origins(monkeypatch):
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)

    with pytest.raises(RuntimeError, match="FRONTEND_ORIGINS"):
        create_app(public_demo_settings=_settings())

    with pytest.raises(RuntimeError, match="at least one exact origin"):
        create_app(
            public_demo_settings=_settings(),
            frontend_origins=(),
        )

    with pytest.raises(RuntimeError, match="not wildcards"):
        create_app(
            public_demo_settings=_settings(),
            frontend_origins=("*",),
        )

    with pytest.raises(RuntimeError, match="exact http"):
        create_app(
            public_demo_settings=_settings(),
            frontend_origins=("https://agent-demo.example/path",),
        )


def test_public_demo_uses_fixed_server_side_tenant_and_release_health(monkeypatch):
    _require_database()
    monkeypatch.setenv("RELEASE_SHA", "phase9b-test-sha")

    app = create_app(
        public_demo_settings=_settings(),
        frontend_origins=(DEMO_ORIGIN,),
    )
    with TestClient(app) as client:
        started = client.post("/api/v1/scenario-1/runs")
        assert started.status_code == 201, started.text
        body = started.json()
        run_id = body["run"]["run_id"]
        assert body["run"]["tenant_id"] == PUBLIC_TENANT

        # Editing X-Tenant-ID in the browser cannot select another tenant.
        reread = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers("TENANT-SOMETHING-ELSE"),
        )
        assert reread.status_code == 200, reread.text
        assert reread.json()["run"]["tenant_id"] == PUBLIC_TENANT

        oversized_browser_tenant = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers("X" * 512),
        )
        assert oversized_browser_tenant.status_code == 200
        assert oversized_browser_tenant.json()["run"]["tenant_id"] == PUBLIC_TENANT

        health = client.get("/health")
        assert health.status_code == 200
        health_body = health.json()
        assert health_body["phase"] == 9
        assert health_body["checkpoint"] == "9B-lite"
        assert health_body["release_version"] == "0.9.0"
        assert health_body["release_sha"] == "phase9b-test-sha"
        assert health_body["public_demo"] is True
        assert health_body["tenant_policy"] == "fixed_server_side"
        assert health_body["database_reachable"] is True

        allowed = client.options(
            "/health",
            headers={
                "Origin": DEMO_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == DEMO_ORIGIN

        denied = client.options(
            "/health",
            headers={
                "Origin": "https://unrelated.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert denied.status_code == 400
        assert "access-control-allow-origin" not in denied.headers


def test_public_demo_run_start_cooldown_returns_typed_429():
    _require_database()

    app = create_app(
        public_demo_settings=_settings(cooldown=60.0),
        frontend_origins=(DEMO_ORIGIN,),
    )
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/scenario-1/runs",
            headers=_headers(),
        )
        assert first.status_code == 201, first.text

        second = client.post(
            "/api/v1/scenario-3/runs",
            headers=_headers(),
        )
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "PUBLIC_DEMO_COOLDOWN"
        assert second.json()["error"]["retryable"] is True
        retry_after = int(second.headers["Retry-After"])
        assert retry_after >= 1
        assert second.json()["error"]["details"]["retry_after_seconds"] == str(
            retry_after
        )


def test_public_demo_hides_internal_and_acceptance_routes(monkeypatch):
    _require_database()
    monkeypatch.setenv("PHASE6D_ACCEPTANCE_HOOKS", "1")
    monkeypatch.setenv("PHASE6D_ACCEPTANCE_TOKEN", "should-still-not-work")

    app = create_app(
        public_demo_settings=_settings(),
        frontend_origins=(DEMO_ORIGIN,),
    )
    with TestClient(app) as client:
        cases = (
            (
                "/api/v1/runs/RUN-NOT-NEEDED/agent/invoke",
                None,
                {},
            ),
            (
                "/api/v1/scenario-2/runs/RUN-NOT-NEEDED/signals",
                {
                    "source": "MONITORING",
                    "site_id": "SITE-X",
                    "service_key": "SERVICE-X",
                    "symptom_key": "SYMPTOM-X",
                    "source_ref": "REF-X",
                    "safe_payload": {},
                },
                {},
            ),
            (
                "/api/v1/scenario-2/runs/RUN-NOT-NEEDED/acceptance/dependency-status",
                {"dependency_status": "HEALTHY"},
                {},
            ),
            (
                "/api/v1/scenario-2/runs/RUN-NOT-NEEDED/acceptance/matching-major-incident",
                {"major_incident_id": "MI-ACCEPTANCE"},
                {},
            ),
            (
                "/__acceptance/phase6d/runs/RUN-NOT-NEEDED/access-link-state",
                {"operational_state": "UP"},
                {"X-Acceptance-Token": "should-still-not-work"},
            ),
        )

        for path, payload, extra_headers in cases:
            response = client.post(path, headers=extra_headers, json=payload)
            assert response.status_code == 404, (path, response.text)
            assert response.json()["error"]["code"] == "NOT_FOUND"
            assert response.json()["error"]["message"] == "Resource was not found."

        malformed = client.post(
            "/api/v1/scenario-2/runs/RUN-NOT-NEEDED/acceptance/dependency-status/",
            content="{not-json",
            headers={"Content-Type": "application/json"},
            follow_redirects=False,
        )
        assert malformed.status_code == 404
        assert malformed.json()["error"]["code"] == "NOT_FOUND"


def test_public_demo_keeps_scenario2_simulator_available():
    _require_database()

    app = create_app(
        public_demo_settings=_settings(),
        frontend_origins=(DEMO_ORIGIN,),
    )
    with TestClient(app) as client:
        started = client.post("/api/v1/scenario-2/runs")
        assert started.status_code == 201, started.text
        run_id = started.json()["run"]["run_id"]

        advanced = client.post(
            f"/api/v1/scenario-2/runs/{run_id}/simulator/next"
        )
        assert advanced.status_code == 200, advanced.text
        assert advanced.json()["state"]["run"]["run_id"] == run_id


def test_non_public_mode_keeps_existing_tenant_behavior():
    _require_database()

    app = create_app(frontend_origins=("http://localhost:3000",))
    with TestClient(app) as client:
        missing = client.get("/api/v1/runs/RUN-NOT-FOUND")
        assert missing.status_code == 422

        invalid = client.get(
            "/api/v1/runs/RUN-NOT-FOUND",
            headers={"X-Tenant-ID": "bad tenant"},
        )
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "INVALID_TENANT_CONTEXT"
