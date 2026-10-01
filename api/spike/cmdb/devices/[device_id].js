"use strict";

const KNOWN_DEVICE_ID = "POS-KZN17-03";

function observedAt() {
  return new Date().toISOString();
}

function foundDeviceResponse() {
  return {
    ok: true,
    run_id: "RUN-SPIKE-001",
    tool: "spike_get_device",
    observed_at: observedAt(),
    evidence_ref: "EVD-SPIKE-CMDB-001",
    data: {
      device_id: KNOWN_DEVICE_ID,
      type: "POS_TERMINAL",
      site_id: "SITE-KZN-17",
      upstream_device_id: "SW-KZN17-01",
      upstream_port: "Gi1/0/23"
    }
  };
}

function notFoundResponse() {
  return {
    ok: false,
    run_id: "RUN-SPIKE-001",
    tool: "spike_get_device",
    observed_at: observedAt(),
    error: {
      code: "NOT_FOUND",
      message: "Device not found"
    }
  };
}

function handler(request, response) {
  if (request.method !== "GET") {
    response.setHeader("Allow", "GET");
    return response.status(405).json({ error: "Method not allowed" });
  }

  const deviceId = request.query.device_id;
  return response.status(200).json(
    deviceId === KNOWN_DEVICE_ID ? foundDeviceResponse() : notFoundResponse()
  );
}

module.exports = handler;
module.exports.foundDeviceResponse = foundDeviceResponse;
module.exports.notFoundResponse = notFoundResponse;
