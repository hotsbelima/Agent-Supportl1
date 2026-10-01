"use strict";

const KNOWN_SITE_ID = "SITE-KZN-17";

function observedAt() {
  return new Date().toISOString();
}

function foundSiteHealthResponse() {
  return {
    ok: true,
    run_id: "RUN-SPIKE-001",
    tool: "spike_get_site_health",
    observed_at: observedAt(),
    evidence_ref: "EVD-SPIKE-SITE-001",
    data: {
      site_id: KNOWN_SITE_ID,
      overall_status: "HEALTHY",
      internet: "UP",
      default_gateway: "UP",
      core_switch: "UP",
      peer_devices: [
        { device_id: "POS-KZN17-01", status: "HEALTHY" },
        { device_id: "POS-KZN17-02", status: "HEALTHY" },
        { device_id: "POS-KZN17-03", status: "UNREACHABLE" }
      ],
      active_sitewide_alerts: []
    }
  };
}

function notFoundResponse() {
  return {
    ok: false,
    run_id: "RUN-SPIKE-001",
    tool: "spike_get_site_health",
    observed_at: observedAt(),
    error: {
      code: "NOT_FOUND",
      message: "Site not found"
    }
  };
}

function handler(request, response) {
  if (request.method !== "GET") {
    response.setHeader("Allow", "GET");
    return response.status(405).json({ error: "Method not allowed" });
  }

  const siteId = request.query.site_id;
  return response.status(200).json(
    siteId === KNOWN_SITE_ID ? foundSiteHealthResponse() : notFoundResponse()
  );
}

module.exports = handler;
module.exports.foundSiteHealthResponse = foundSiteHealthResponse;
module.exports.notFoundResponse = notFoundResponse;
