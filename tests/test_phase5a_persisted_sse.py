from __future__ import annotations

import asyncio
from contextlib import contextmanager
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Iterator
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from product_api.app import ProductApiContainer, create_app
from product_api.scenario1_fixture import Scenario1FixtureSources
from product_api.sse import SseSettings, resolve_sse_cursor
from product_backend.application.lifecycle import ApplicationLifecycleService
from product_backend.contracts.tools import ToolCallContext
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
    normalize_database_url,
)
from product_backend.persistence.uow import SqlAlchemyLifecycleUnitOfWork


REPO_ROOT = Path(__file__).resolve().parents[1]


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    return normalize_database_url(value)


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-ID": tenant_id}


def _new_db():
    engine = create_engine(DatabaseSettings(url=_database_url()))
    return engine, create_session_factory(engine)


def _start_with_testclient(client: TestClient, tenant_id: str) -> dict:
    response = client.post(
        "/api/v1/scenario-1/runs",
        headers=_headers(tenant_id),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _fake_container() -> ProductApiContainer:
    return ProductApiContainer(
        start_service=object(),
        state_service=object(),
        lifecycle_service=object(),
        approval_service=object(),
        fixture=Scenario1FixtureSources(),
        engine=None,
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request_json(
    base_url: str,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: float = 5.0,
) -> tuple[int, dict, dict[str, str]]:
    parsed = urlsplit(base_url)
    connection = http.client.HTTPConnection(
        parsed.hostname,
        parsed.port,
        timeout=timeout,
    )
    payload = None
    request_headers = dict(headers or {})
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    try:
        connection.request(
            method,
            path,
            body=payload,
            headers=request_headers,
        )
        response = connection.getresponse()
        raw = response.read()
        response_headers = {
            key.lower(): value for key, value in response.getheaders()
        }
        data = json.loads(raw.decode("utf-8")) if raw else {}
        return response.status, data, response_headers
    finally:
        connection.close()


@contextmanager
def _running_server() -> Iterator[str]:
    port = _free_port()
    env = os.environ.copy()
    env["SSE_POLL_INTERVAL_SECONDS"] = "0.05"
    env["SSE_HEARTBEAT_INTERVAL_SECONDS"] = "0.15"
    env["SSE_BATCH_SIZE"] = "100"
    env["FRONTEND_ORIGINS"] = (
        "http://localhost:3000,https://phase5.example.test"
    )

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "product_api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"

    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(
                    f"uvicorn exited before readiness with code {process.returncode}"
                )
            try:
                status_code, body, _ = _request_json(
                    base_url,
                    "GET",
                    "/health",
                )
                if status_code == 200 and body.get("status") == "ok":
                    break
            except OSError:
                pass
            time.sleep(0.05)
        else:
            raise AssertionError("uvicorn did not become ready")

        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _start_http(base_url: str, tenant_id: str) -> dict:
    status_code, body, _ = _request_json(
        base_url,
        "POST",
        "/api/v1/scenario-1/runs",
        headers=_headers(tenant_id),
    )
    assert status_code == 201, body
    return body


def _open_sse(
    base_url: str,
    *,
    tenant_id: str,
    run_id: str,
    after_seq: str | None = None,
    last_event_id: str | None = None,
    timeout: float = 5.0,
) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse]:
    parsed = urlsplit(base_url)
    path = f"/api/v1/runs/{run_id}/events/stream"
    if after_seq is not None:
        path = f"{path}?{urlencode({'after_seq': after_seq})}"

    connection = http.client.HTTPConnection(
        parsed.hostname,
        parsed.port,
        timeout=timeout,
    )
    headers = {
        "X-Tenant-ID": tenant_id,
        "Accept": "text/event-stream",
    }
    if last_event_id is not None:
        headers["Last-Event-ID"] = last_event_id

    connection.request("GET", path, headers=headers)
    response = connection.getresponse()
    return connection, response


def _read_sse_frame(response: http.client.HTTPResponse) -> dict:
    lines: list[str] = []
    while True:
        raw = response.readline()
        if raw == b"":
            raise AssertionError("SSE stream closed before a complete frame")
        line = raw.decode("utf-8").rstrip("\r\n")
        if line == "":
            break
        lines.append(line)

    if lines and lines[0].startswith(":"):
        return {"comment": lines[0][1:].strip(), "raw": lines}

    parsed: dict[str, object] = {"raw": lines}
    for line in lines:
        key, separator, value = line.partition(":")
        if not separator:
            continue
        value = value[1:] if value.startswith(" ") else value
        if key == "id":
            parsed["id"] = value
        elif key == "event":
            parsed["event"] = value
        elif key == "data":
            parsed["data"] = json.loads(value)
    return parsed


def _read_next_application_event(
    response: http.client.HTTPResponse,
    *,
    max_frames: int = 10,
) -> dict:
    for _ in range(max_frames):
        frame = _read_sse_frame(response)
        if frame.get("event") == "application.event":
            return frame
    raise AssertionError("No application.event frame arrived")


async def _record_external_signal(
    *,
    tenant_id: str,
    run_id: str,
    marker: str,
):
    engine, factory = _new_db()
    try:
        service = ApplicationLifecycleService(
            lambda: SqlAlchemyLifecycleUnitOfWork(factory)
        )
        return await service.record_external_signal(
            ToolCallContext(tenant_id=tenant_id, run_id=run_id),
            signal_type="phase5a.test",
            details={"marker": marker},
        )
    finally:
        await engine.dispose()


def test_cursor_parser_has_last_event_id_precedence_and_rejects_invalid_values():
    assert resolve_sse_cursor(last_event_id=None, after_seq=None) == 0
    assert resolve_sse_cursor(last_event_id=None, after_seq="7") == 7
    assert resolve_sse_cursor(last_event_id="9", after_seq="7") == 9

    for value in ("-1", "abc", "", "1.5"):
        with pytest.raises(ValueError):
            resolve_sse_cursor(last_event_id=value, after_seq="3")


def test_stream_unknown_run_foreign_tenant_and_invalid_cursor_are_safe():
    tenant_id = f"TENANT-SSE-{uuid4().hex[:8]}"
    other_tenant = f"TENANT-SSE-OTHER-{uuid4().hex[:8]}"

    with TestClient(
        create_app(sse_settings=SseSettings(0.05, 0.15, 100))
    ) as client:
        state = _start_with_testclient(client, tenant_id)
        run_id = state["run"]["run_id"]

        unknown = client.get(
            "/api/v1/runs/RUN-UNKNOWN/events/stream",
            headers=_headers(tenant_id),
        )
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "RUN_NOT_FOUND"

        foreign = client.get(
            f"/api/v1/runs/{run_id}/events/stream",
            headers=_headers(other_tenant),
        )
        assert foreign.status_code == 404
        assert foreign.json()["error"]["code"] == "RUN_NOT_FOUND"

        invalid_query = client.get(
            f"/api/v1/runs/{run_id}/events/stream?after_seq=-1",
            headers=_headers(tenant_id),
        )
        assert invalid_query.status_code == 400
        assert invalid_query.json() == {
            "error": {
                "code": "INVALID_CURSOR",
                "message": "Event cursor must be a non-negative integer.",
                "retryable": False,
                "details": {},
            }
        }

        invalid_header = client.get(
            f"/api/v1/runs/{run_id}/events/stream?after_seq=1",
            headers={
                **_headers(tenant_id),
                "Last-Event-ID": "not-a-number",
            },
        )
        assert invalid_header.status_code == 400
        assert invalid_header.json()["error"]["code"] == "INVALID_CURSOR"


def test_explicit_cors_allows_required_headers_and_rejects_unlisted_origin():
    app = create_app(
        _fake_container(),
        frontend_origins=("http://localhost:3000",),
    )
    with TestClient(app) as client:
        allowed = client.options(
            "/api/v1/runs/RUN-1/events/stream",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": (
                    "x-tenant-id,last-event-id,accept,content-type"
                ),
            },
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == (
            "http://localhost:3000"
        )
        allow_headers = allowed.headers[
            "access-control-allow-headers"
        ].lower()
        assert "x-tenant-id" in allow_headers
        assert "last-event-id" in allow_headers
        assert "accept" in allow_headers
        assert "content-type" in allow_headers
        assert allowed.headers.get("access-control-allow-origin") != "*"

        denied = client.options(
            "/api/v1/runs/RUN-1/events/stream",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-tenant-id",
            },
        )
        assert denied.headers.get("access-control-allow-origin") is None


def test_real_http_stream_orders_persisted_events_and_honors_cursor_precedence():
    tenant_id = f"TENANT-SSE-HTTP-{uuid4().hex[:8]}"

    with _running_server() as base_url:
        state = _start_http(base_url, tenant_id)
        run_id = state["run"]["run_id"]

        connection, response = _open_sse(
            base_url,
            tenant_id=tenant_id,
            run_id=run_id,
            after_seq="0",
        )
        try:
            assert response.status == 200
            assert response.getheader("content-type").startswith(
                "text/event-stream"
            )
            frames = [
                _read_next_application_event(response)
                for _ in range(3)
            ]
        finally:
            response.close()
            connection.close()

        assert [int(frame["id"]) for frame in frames] == [1, 2, 3]
        assert [frame["data"]["seq"] for frame in frames] == [1, 2, 3]
        assert all(
            frame["event"] == "application.event" for frame in frames
        )
        assert all(
            frame["data"]["run_id"] == run_id for frame in frames
        )

        status_code, timeline, _ = _request_json(
            base_url,
            "GET",
            f"/api/v1/runs/{run_id}/events?after_seq=0&limit=100",
            headers=_headers(tenant_id),
        )
        assert status_code == 200
        assert [frame["data"] for frame in frames] == timeline["events"]

        connection, response = _open_sse(
            base_url,
            tenant_id=tenant_id,
            run_id=run_id,
            after_seq="0",
            last_event_id="2",
        )
        try:
            assert response.status == 200
            frame = _read_next_application_event(response)
        finally:
            response.close()
            connection.close()

        assert frame["id"] == "3"
        assert frame["data"]["seq"] == 3


def test_heartbeat_is_transport_only_and_does_not_advance_persisted_sequence():
    tenant_id = f"TENANT-SSE-HB-{uuid4().hex[:8]}"

    with _running_server() as base_url:
        state = _start_http(base_url, tenant_id)
        run_id = state["run"]["run_id"]
        latest_seq = state["latest_event_seq"]

        connection, response = _open_sse(
            base_url,
            tenant_id=tenant_id,
            run_id=run_id,
            after_seq=str(latest_seq),
        )
        try:
            assert response.status == 200
            frame = _read_sse_frame(response)
        finally:
            response.close()
            connection.close()

        assert frame == {
            "comment": "keepalive",
            "raw": [": keepalive"],
        }

        status_code, timeline, _ = _request_json(
            base_url,
            "GET",
            f"/api/v1/runs/{run_id}/events?after_seq={latest_seq}",
            headers=_headers(tenant_id),
        )
        assert status_code == 200
        assert timeline["events"] == []
        assert timeline["next_cursor"] == latest_seq


def test_event_created_after_open_stream_arrives_and_writer_is_not_blocked():
    tenant_id = f"TENANT-SSE-LIVE-{uuid4().hex[:8]}"

    with _running_server() as base_url:
        state = _start_http(base_url, tenant_id)
        run_id = state["run"]["run_id"]
        latest_seq = state["latest_event_seq"]

        connection, response = _open_sse(
            base_url,
            tenant_id=tenant_id,
            run_id=run_id,
            after_seq=str(latest_seq),
        )
        try:
            assert response.status == 200
            time.sleep(0.08)
            started = time.monotonic()
            persisted = asyncio.run(
                _record_external_signal(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    marker="writer-not-blocked",
                )
            )
            elapsed = time.monotonic() - started
            frame = _read_next_application_event(response)
        finally:
            response.close()
            connection.close()

        assert elapsed < 1.0
        assert persisted.seq == latest_seq + 1
        assert frame["id"] == str(persisted.seq)
        assert frame["data"]["event_type"] == "external.signal"
        assert frame["data"]["payload"] == {
            "signal_type": "phase5a.test",
            "details": {"marker": "writer-not-blocked"},
        }


def test_backend_restart_reconnects_from_persisted_last_event_id():
    tenant_id = f"TENANT-SSE-RESTART-{uuid4().hex[:8]}"

    with _running_server() as first_url:
        state = _start_http(first_url, tenant_id)
        run_id = state["run"]["run_id"]
        latest_seq = state["latest_event_seq"]

        connection, response = _open_sse(
            first_url,
            tenant_id=tenant_id,
            run_id=run_id,
            after_seq="0",
        )
        try:
            frames = [
                _read_next_application_event(response)
                for _ in range(3)
            ]
        finally:
            response.close()
            connection.close()
        assert frames[-1]["id"] == str(latest_seq)

    with _running_server() as restarted_url:
        connection, response = _open_sse(
            restarted_url,
            tenant_id=tenant_id,
            run_id=run_id,
            last_event_id=str(latest_seq),
        )
        try:
            persisted = asyncio.run(
                _record_external_signal(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    marker="after-restart",
                )
            )
            frame = _read_next_application_event(response)
        finally:
            response.close()
            connection.close()

        assert persisted.seq == latest_seq + 1
        assert frame["id"] == str(latest_seq + 1)
        assert (
            frame["data"]["payload"]["details"]["marker"]
            == "after-restart"
        )


def test_stream_isolated_by_run_and_safe_payload_contains_no_reasoning_or_secrets():
    tenant_id = f"TENANT-SSE-ISO-{uuid4().hex[:8]}"

    with _running_server() as base_url:
        first = _start_http(base_url, tenant_id)
        second = _start_http(base_url, tenant_id)
        first_run = first["run"]["run_id"]
        second_run = second["run"]["run_id"]

        connection, response = _open_sse(
            base_url,
            tenant_id=tenant_id,
            run_id=first_run,
            after_seq="0",
        )
        try:
            frames = [
                _read_next_application_event(response)
                for _ in range(3)
            ]
        finally:
            response.close()
            connection.close()

        serialized = json.dumps(frames, sort_keys=True).lower()
        assert all(
            frame["data"]["run_id"] == first_run
            for frame in frames
        )
        assert second_run not in serialized
        for forbidden in (
            "chain_of_thought",
            "model_reasoning",
            "google_api_key",
            "postgresql://",
            "password",
            "super_secret",
        ):
            assert forbidden not in serialized
