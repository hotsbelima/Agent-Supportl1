"""Scenario 1 composition fixture used by the product API.

Canonical fixture data lives outside product_backend so reusable domain and
application code remain independent from the demo world's concrete IDs.
No hidden root-cause answer is exposed here.
"""

from __future__ import annotations

from product_backend.contracts.run_state import Scenario1Bootstrap
from product_backend.domain.enums import (
    ActionType,
    AdminState,
    ConfigurationState,
    DiagnosisCode,
    DiagnosticType,
    HealthState,
    IncidentSearchScope,
    OperationalState,
    PortSecurityState,
)
from product_backend.domain.models import (
    AccessLinkDiagnosticSnapshot,
    DeviceTopology,
    IncidentSearchSnapshot,
    KbArticle,
    SiteHealthSnapshot,
)


SCENARIO_ID = "scenario-1"
INCIDENT_ID = "INC-1042"
SITE_ID = "SITE-KZN-017"
AFFECTED_DEVICE_ID = "POS-KZN17-02"
PEER_DEVICE_ID = "POS-KZN17-01"
ATTACHMENT_ID = "ATT-KZN17-POS02"
SWITCH_ID = "SW-KZN17-01"
PORT_ID = "Gi1/0/18"

INCIDENT_SYMPTOM = "Payment terminal is unavailable."


class Scenario1FixtureSources:
    """Deterministic Scenario 1 sources plus a narrow Phase 6D test override."""

    def __init__(
        self,
        access_link_operational_overrides: dict[
            tuple[str, str], OperationalState
        ] | None = None,
    ) -> None:
        # Scenario 1 and Scenario 3 may use distinct bootstrap identities while
        # sharing one authoritative process-local monitoring truth for the same
        # physical topology. This is required so human-approval revalidation
        # observes the same access-link override as Scenario 3 diagnostics.
        self._access_link_operational_overrides = (
            access_link_operational_overrides
            if access_link_operational_overrides is not None
            else {}
        )

    def set_access_link_operational_state(
        self,
        *,
        tenant_id: str,
        run_id: str,
        operational_state: OperationalState,
    ) -> None:
        """Acceptance-only override for authoritative revalidation state.

        This is intentionally scoped to one tenant/run and is process-local.
        It is not Product business state, is not persisted, and is never
        exposed to the model as a tool.
        """
        self._access_link_operational_overrides[(tenant_id, run_id)] = (
            operational_state
        )

    def clear_access_link_operational_state(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> None:
        self._access_link_operational_overrides.pop((tenant_id, run_id), None)

    def bootstrap(self) -> Scenario1Bootstrap:
        return Scenario1Bootstrap(
            scenario_id=SCENARIO_ID,
            incident_id=INCIDENT_ID,
            site_id=SITE_ID,
            reported_device_id=AFFECTED_DEVICE_ID,
            symptom=INCIDENT_SYMPTOM,
        )

    async def get_device(
        self,
        *,
        tenant_id: str,
        run_id: str,
        device_id: str,
    ) -> DeviceTopology | None:
        if device_id != AFFECTED_DEVICE_ID:
            return None
        return DeviceTopology(
            device_id=AFFECTED_DEVICE_ID,
            site_id=SITE_ID,
            attachment_id=ATTACHMENT_ID,
            device_type="POS_TERMINAL",
            expected_switch_id=SWITCH_ID,
            expected_port_id=PORT_ID,
        )

    async def get_site_health(
        self,
        *,
        tenant_id: str,
        run_id: str,
        site_id: str,
    ) -> SiteHealthSnapshot | None:
        if site_id != SITE_ID:
            return None
        return SiteHealthSnapshot(
            site_id=SITE_ID,
            site_network=HealthState.HEALTHY,
            payment_service=HealthState.HEALTHY,
            peer_device_id=PEER_DEVICE_ID,
            peer_reachable=True,
            affected_device_id=AFFECTED_DEVICE_ID,
            affected_device_reachable=False,
        )

    async def run_diagnostic(
        self,
        *,
        tenant_id: str,
        run_id: str,
        diagnostic_type: DiagnosticType,
        target_id: str,
    ) -> AccessLinkDiagnosticSnapshot | None:
        if (
            diagnostic_type is not DiagnosticType.ACCESS_LINK
            or target_id != ATTACHMENT_ID
        ):
            return None
        operational_state = self._access_link_operational_overrides.get(
            (tenant_id, run_id),
            OperationalState.DOWN,
        )
        return AccessLinkDiagnosticSnapshot(
            target_id=ATTACHMENT_ID,
            attachment_id=ATTACHMENT_ID,
            switch_id=SWITCH_ID,
            port_id=PORT_ID,
            switch_reachable=True,
            admin_state=AdminState.UP,
            operational_state=operational_state,
            port_security=PortSecurityState.NORMAL,
            configuration=ConfigurationState.EXPECTED,
        )


    async def search_incidents(
        self,
        *,
        tenant_id: str,
        run_id: str,
        scope: IncidentSearchScope,
        entity_id: str,
    ) -> IncidentSearchSnapshot:
        del tenant_id, run_id
        open_incidents: tuple[str, ...] = ()
        if scope is IncidentSearchScope.DEVICE and entity_id == AFFECTED_DEVICE_ID:
            open_incidents = (INCIDENT_ID,)
        elif scope is IncidentSearchScope.SITE and entity_id == SITE_ID:
            open_incidents = (INCIDENT_ID,)

        return IncidentSearchSnapshot(
            scope=scope,
            entity_id=entity_id,
            open_incident_ids=open_incidents,
        )

    async def search(
        self,
        *,
        tenant_id: str,
        run_id: str,
        query: str,
    ) -> tuple[KbArticle, ...]:
        del tenant_id, run_id, query
        return (
            KbArticle(
                article_id="KB-LOCAL-LINK",
                title="Проверка физического пути подключения",
                approved=True,
                diagnosis_codes=(DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,),
                allowed_actions=(ActionType.ONSITE_FIELD_VISIT,),
            ),
        )


__all__ = ["Scenario1FixtureSources"]
