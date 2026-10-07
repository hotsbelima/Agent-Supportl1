"""Durable Product operational-event -> native ADK dispatch for Phase 7A."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from agent_runtime.service import DeviceIncidentAgentRuntime, Scenario1AgentRuntime
from agent_runtime.scenario2_service import Scenario2AgentRuntime
from agent_runtime.scenario3_service import Scenario3AgentRuntime
from product_backend.application.lifecycle import ApplicationLifecycleService
from product_backend.application.run_state import RunStateService
from product_backend.application.scenario2_state import Scenario2StateService
from product_backend.contracts.events import (
    AGENT_DISPATCH_TOPIC,
    SCENARIO2_AGENT_DISPATCH_TOPIC,
    ApplicationEventType,
    ApplicationOutboxRecord,
)
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import EvidenceSourceType
from product_backend.domain.scenario2 import OperationalSignalEvidenceSnapshot
from product_backend.ports.events import ApplicationOutboxRepository


class DispatchUnitOfWork(Protocol):
    outbox: ApplicationOutboxRepository

    async def __aenter__(self) -> "DispatchUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


DispatchUowFactory = Callable[[], DispatchUnitOfWork]


def _retry_delay_seconds(attempt_count: int) -> float:
    exponent = max(0, min(attempt_count - 1, 5))
    return float(min(30, 2**exponent))


class Scenario1DispatchWorker:
    """Consume durable Product dispatch envelopes without becoming an agent loop.

    The outbox decides *when* a persisted operational event should wake ADK.
    Google ADK still owns the invocation/tool/session lifecycle. The worker never
    polls Monitoring through the model and never interprets incident evidence.
    """

    def __init__(
        self,
        *,
        uow_factory: DispatchUowFactory,
        state_service: RunStateService,
        agent_runtime: Scenario1AgentRuntime,
        scenario3_agent_runtime: Scenario3AgentRuntime | None = None,
        poll_interval_seconds: float = 0.5,
        lease_seconds: float = 180.0,
        invocation_timeout_seconds: float = 120.0,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if invocation_timeout_seconds <= 0:
            raise ValueError("invocation_timeout_seconds must be positive")
        if lease_seconds <= invocation_timeout_seconds:
            raise ValueError(
                "lease_seconds must exceed invocation_timeout_seconds"
            )
        self._uow_factory = uow_factory
        self._state_service = state_service
        self._agent_runtime = agent_runtime
        self._scenario3_agent_runtime = scenario3_agent_runtime
        self._poll_interval = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._invocation_timeout = invocation_timeout_seconds
        self._wake = asyncio.Event()
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping.clear()
        self._task = asyncio.create_task(
            self._run(),
            name="phase7a-operational-event-dispatch",
        )

    @property
    def running(self) -> bool:
        task = self._task
        return task is not None and not task.done()

    def wake(self) -> None:
        self._wake.set()

    async def close(self) -> None:
        self._stopping.set()
        self._wake.set()
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def _runtime_for_scenario(
        self,
        scenario_id: str,
    ) -> DeviceIncidentAgentRuntime | None:
        if scenario_id == "scenario-1":
            return self._agent_runtime
        if scenario_id == "scenario-3":
            return self._scenario3_agent_runtime
        return None

    async def _claim(self) -> ApplicationOutboxRecord | None:
        async with self._uow_factory() as uow:
            record = await uow.outbox.claim_next(
                topic=AGENT_DISPATCH_TOPIC,
                lease_seconds=self._lease_seconds,
            )
            await uow.commit()
            return record

    async def _mark_delivered(self, record: ApplicationOutboxRecord) -> None:
        async with self._uow_factory() as uow:
            await uow.outbox.mark_delivered(
                tenant_id=record.tenant_id,
                run_id=record.run_id,
                outbox_id=record.outbox_id,
            )
            await uow.commit()

    async def _reschedule(self, record: ApplicationOutboxRecord) -> None:
        async with self._uow_factory() as uow:
            await uow.outbox.reschedule(
                tenant_id=record.tenant_id,
                run_id=record.run_id,
                outbox_id=record.outbox_id,
                delay_seconds=_retry_delay_seconds(record.attempt_count),
            )
            await uow.commit()

    async def dispatch_once(self) -> bool:
        """Process at most one due envelope; useful for deterministic tests."""
        configured_runtimes = [
            runtime
            for runtime in (
                self._agent_runtime,
                self._scenario3_agent_runtime,
            )
            if runtime is not None
        ]
        if not any(runtime.gemini_configured for runtime in configured_runtimes):
            return False

        record = await self._claim()
        if record is None:
            return False

        try:
            event_id = record.payload.get("event_id")
            signal = record.payload.get("signal")
            if not isinstance(event_id, str) or not event_id:
                raise ValueError("dispatch envelope event_id is invalid")
            if not isinstance(signal, dict):
                raise ValueError("dispatch envelope signal is invalid")

            snapshot = await self._state_service.get(
                tenant_id=record.tenant_id,
                run_id=record.run_id,
            )
            if snapshot is None:
                raise RuntimeError("dispatch run state was not found")

            runtime = self._runtime_for_scenario(snapshot.run.scenario_id)
            if runtime is None or not runtime.gemini_configured:
                # Unknown/unconfigured scenarios fail closed on the durable row.
                # Product truth remains committed and the envelope can be retried
                # after runtime wiring is corrected.
                await self._reschedule(record)
                return True

            operational_signal = {
                "event_id": event_id,
                "event_seq": record.event_seq,
                "scenario_id": snapshot.run.scenario_id,
                "signal": signal,
                "incidents": [
                    {
                        "incident_id": incident.incident_id,
                        "site_id": incident.site_id,
                        "reported_device_id": incident.reported_device_id,
                        "symptom": incident.symptom,
                        "status": incident.status.value,
                    }
                    for incident in snapshot.incidents
                ],
            }

            result = await asyncio.wait_for(
                runtime.invoke_operational_event(
                    tenant_id=record.tenant_id,
                    run_id=record.run_id,
                    operational_event_id=event_id,
                    operational_signal=operational_signal,
                ),
                timeout=self._invocation_timeout,
            )
            if snapshot.run.scenario_id == "scenario-3" and not (
                result.awaiting_human_decision
                and result.pending_proposal_id
                and result.paused_function_call_id
            ):
                raise RuntimeError(
                    "Scenario 3 invocation ended before proposal/HITL terminal state"
                )
        except asyncio.CancelledError:
            # Release the durable lease immediately on graceful shutdown when
            # possible. If the DB is unavailable during shutdown, do not turn
            # process termination into a new failure: the existing lease will
            # expire and durable redelivery will reconcile from ADK history.
            try:
                await self._reschedule(record)
            except Exception:
                pass
            raise
        except Exception:
            # Do not log provider payloads/secrets. The durable row remains the
            # recovery source and will be retried with the same event identity.
            await self._reschedule(record)
            return True

        await self._mark_delivered(record)
        return True

    async def _run(self) -> None:
        failure_count = 0
        while not self._stopping.is_set():
            try:
                processed = await self.dispatch_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A transient DB failure during claim/mark/reschedule must not
                # kill the only dispatcher task. Keep the worker alive and
                # retry from durable Product state after bounded backoff.
                failure_count += 1
                delay = min(30.0, float(2 ** min(failure_count - 1, 5)))
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=delay)
                except TimeoutError:
                    pass
                continue

            failure_count = 0
            if processed:
                continue

            self._wake.clear()
            try:
                await asyncio.wait_for(
                    self._wake.wait(),
                    timeout=self._poll_interval,
                )
            except TimeoutError:
                pass


class Scenario2DispatchWorker:
    """Deliver persisted Scenario 2 facts to one native ADK turn per event.

    This is a narrow durable bridge, not an agent loop: it never decides a
    correlation result, owns no session store, and has no Scenario 1 tool or
    field-visit semantics.  Google ADK persists the native Session/Event
    history; Product owns the facts, event envelope and outbox.
    """

    def __init__(
        self,
        *,
        uow_factory: DispatchUowFactory,
        state_service: Scenario2StateService,
        lifecycle_service: ApplicationLifecycleService,
        agent_runtime: Scenario2AgentRuntime,
        poll_interval_seconds: float = 0.5,
        lease_seconds: float = 180.0,
        invocation_timeout_seconds: float = 120.0,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if invocation_timeout_seconds <= 0:
            raise ValueError("invocation_timeout_seconds must be positive")
        if lease_seconds <= invocation_timeout_seconds:
            raise ValueError(
                "lease_seconds must exceed invocation_timeout_seconds"
            )
        self._uow_factory = uow_factory
        self._state_service = state_service
        self._lifecycle_service = lifecycle_service
        self._agent_runtime = agent_runtime
        self._poll_interval = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._invocation_timeout = invocation_timeout_seconds
        self._wake = asyncio.Event()
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping.clear()
        self._task = asyncio.create_task(
            self._run(),
            name="phase7c-scenario2-operational-signal-dispatch",
        )

    @property
    def running(self) -> bool:
        task = self._task
        return task is not None and not task.done()

    def wake(self) -> None:
        self._wake.set()

    async def close(self) -> None:
        self._stopping.set()
        self._wake.set()
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _claim(self) -> ApplicationOutboxRecord | None:
        async with self._uow_factory() as uow:
            record = await uow.outbox.claim_next(
                topic=SCENARIO2_AGENT_DISPATCH_TOPIC,
                lease_seconds=self._lease_seconds,
            )
            await uow.commit()
            return record

    async def _mark_delivered(self, record: ApplicationOutboxRecord) -> None:
        async with self._uow_factory() as uow:
            await uow.outbox.mark_delivered(
                tenant_id=record.tenant_id,
                run_id=record.run_id,
                outbox_id=record.outbox_id,
            )
            await uow.commit()

    async def _reschedule(self, record: ApplicationOutboxRecord) -> None:
        async with self._uow_factory() as uow:
            await uow.outbox.reschedule(
                tenant_id=record.tenant_id,
                run_id=record.run_id,
                outbox_id=record.outbox_id,
                delay_seconds=_retry_delay_seconds(record.attempt_count),
            )
            await uow.commit()

    async def _operational_fact(
        self,
        record: ApplicationOutboxRecord,
    ) -> tuple[str, dict[str, object], bool]:
        """Rehydrate one Product event plus whether this fact requires HITL."""
        payload = record.payload
        event_id = payload.get("event_id")
        event_seq = payload.get("event_seq")
        signal_id = payload.get("signal_id")
        evidence_id = payload.get("evidence_id")
        if not all(
            isinstance(value, str) and value
            for value in (event_id, signal_id, evidence_id)
        ) or not isinstance(event_seq, int) or event_seq != record.event_seq:
            raise ValueError("Scenario 2 dispatch envelope is invalid")

        context = ToolCallContext(
            tenant_id=record.tenant_id,
            run_id=record.run_id,
        )
        events = await self._lifecycle_service.timeline(
            context,
            after_seq=record.event_seq - 1,
            limit=1,
        )
        if len(events) != 1:
            raise RuntimeError("Scenario 2 Product event was not found")
        product_event = events[0]
        if (
            product_event.event_id != event_id
            or product_event.seq != record.event_seq
            or product_event.event_type != ApplicationEventType.EXTERNAL_SIGNAL
            or product_event.payload.get("signal_id") != signal_id
            or product_event.payload.get("evidence_id") != evidence_id
        ):
            raise RuntimeError("Scenario 2 dispatch event identity does not match")

        state = await self._state_service.get(
            tenant_id=record.tenant_id,
            run_id=record.run_id,
        )
        if state is None or state.run.scenario_id != "scenario-2":
            raise RuntimeError("Scenario 2 Product state was not found")
        signal = next(
            (item for item in state.operational_signals if item.signal_id == signal_id),
            None,
        )
        evidence = next(
            (item for item in state.evidence if item.evidence_id == evidence_id),
            None,
        )
        if (
            signal is None
            or evidence is None
            or evidence.source_type != EvidenceSourceType.OPERATIONAL_SIGNAL
            or not isinstance(
                evidence.payload,
                OperationalSignalEvidenceSnapshot,
            )
        ):
            raise RuntimeError("Scenario 2 signal or signal Evidence was not found")
        evidence_payload = evidence.payload
        if (
            signal.signal_id not in evidence.entity_ids
            or evidence_payload.signal_id != signal.signal_id
            or evidence_payload.source is not signal.source
            or evidence_payload.site_id != signal.site_id
            or evidence_payload.service_key != signal.service_key
            or evidence_payload.symptom_key != signal.symptom_key
            or evidence_payload.source_ref != signal.source_ref
        ):
            raise RuntimeError(
                "Scenario 2 Evidence does not match the persisted dispatch signal"
            )
        incident = next(
            (
                item
                for item in state.service_incidents
                if item.incident_id == signal.incident_id
            ),
            None,
        )
        if incident is None:
            raise RuntimeError("Scenario 2 signal ServiceIncident was not found")
        if (
            incident.site_id != signal.site_id
            or incident.service_key != signal.service_key
            or incident.symptom_key != signal.symptom_key
        ):
            raise RuntimeError(
                "Scenario 2 ServiceIncident does not match the dispatch signal"
            )

        signal_index = next(
            index
            for index, item in enumerate(state.operational_signals)
            if item.signal_id == signal.signal_id
        )
        sites_through_event = {
            item.site_id
            for item in state.operational_signals[: signal_index + 1]
        }
        requires_proposal = len(sites_through_event) >= 2

        return event_id, {
            "event": {
                "event_id": product_event.event_id,
                "event_seq": product_event.seq,
                "event_type": product_event.event_type.value,
                "occurred_at": product_event.occurred_at.isoformat(),
            },
            "signal": {
                "signal_id": signal.signal_id,
                "source": signal.source.value,
                "site_id": signal.site_id,
                "service_key": signal.service_key,
                "symptom_key": signal.symptom_key,
                "source_ref": signal.source_ref,
                "received_at": signal.received_at.isoformat(),
                "safe_payload": dict(signal.safe_payload),
                "incident_id": signal.incident_id,
            },
            "evidence": {
                "evidence_id": evidence.evidence_id,
                "source_type": evidence.source_type.value,
                "captured_at": evidence.captured_at.isoformat(),
                "expires_at": (
                    evidence.expires_at.isoformat()
                    if evidence.expires_at is not None
                    else None
                ),
                "entity_ids": list(evidence.entity_ids),
            },
            "service_incident": {
                "incident_id": incident.incident_id,
                "site_id": incident.site_id,
                "service_key": incident.service_key,
                "symptom_key": incident.symptom_key,
                "status": incident.status.value,
            },
        }, requires_proposal

    async def dispatch_once(self) -> bool:
        """Process one due Scenario 2 envelope after a recoverable ADK point."""
        if not self._agent_runtime.gemini_configured:
            return False
        record = await self._claim()
        if record is None:
            return False
        try:
            event_id, fact, requires_proposal = await self._operational_fact(record)
            result = await asyncio.wait_for(
                self._agent_runtime.invoke_operational_signal(
                    tenant_id=record.tenant_id,
                    run_id=record.run_id,
                    product_event_id=event_id,
                    operational_fact=fact,
                    require_proposal_hitl=requires_proposal,
                ),
                timeout=self._invocation_timeout,
            )
            if not result.recoverable:
                raise RuntimeError("native ADK invocation has no recoverable state")
            if requires_proposal and not (
                result.awaiting_human_decision
                and result.pending_proposal_id
                and result.paused_function_call_id
            ):
                raise RuntimeError(
                    "Scenario 2 cross-site invocation ended before proposal/HITL terminal state"
                )
        except asyncio.CancelledError:
            try:
                await self._reschedule(record)
            except Exception:
                pass
            raise
        except Exception:
            await self._reschedule(record)
            return True

        await self._mark_delivered(record)
        return True

    async def _run(self) -> None:
        failure_count = 0
        while not self._stopping.is_set():
            try:
                processed = await self.dispatch_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                failure_count += 1
                delay = min(30.0, float(2 ** min(failure_count - 1, 5)))
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=delay)
                except TimeoutError:
                    pass
                continue
            failure_count = 0
            if processed:
                continue
            self._wake.clear()
            try:
                await asyncio.wait_for(
                    self._wake.wait(),
                    timeout=self._poll_interval,
                )
            except TimeoutError:
                pass


__all__ = ["Scenario1DispatchWorker", "Scenario2DispatchWorker"]
