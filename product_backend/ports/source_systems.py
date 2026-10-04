"""Provider-neutral read ports for CMDB, NMS/monitoring, ITSM and KB."""

from __future__ import annotations

from typing import Protocol

from product_backend.domain.enums import DiagnosticType, IncidentSearchScope
from product_backend.domain.models import (
    AccessLinkDiagnosticSnapshot,
    DeviceTopology,
    Incident,
    IncidentSearchSnapshot,
    KbArticle,
    SiteHealthSnapshot,
)


class CmdbPort(Protocol):
    """Return None only for an authoritative not-found result; outages raise."""

    async def get_device(
        self, *, tenant_id: str, run_id: str, device_id: str
    ) -> DeviceTopology | None: ...


class MonitoringPort(Protocol):
    """Return None only for authoritative absence; provider outages raise."""

    async def get_site_health(
        self, *, tenant_id: str, run_id: str, site_id: str
    ) -> SiteHealthSnapshot | None: ...

    async def run_diagnostic(
        self,
        *,
        tenant_id: str,
        run_id: str,
        diagnostic_type: DiagnosticType,
        target_id: str,
    ) -> AccessLinkDiagnosticSnapshot | None: ...


class ItsmPort(Protocol):
    async def get_incident(
        self, *, tenant_id: str, run_id: str, incident_id: str
    ) -> Incident | None: ...

    async def search_incidents(
        self,
        *,
        tenant_id: str,
        run_id: str,
        scope: IncidentSearchScope,
        entity_id: str,
    ) -> IncidentSearchSnapshot: ...


class KnowledgeBasePort(Protocol):
    async def search(
        self, *, tenant_id: str, run_id: str, query: str
    ) -> tuple[KbArticle, ...]: ...
