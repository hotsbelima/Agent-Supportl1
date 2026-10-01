"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const deviceTool = require("../api/spike/cmdb/devices/[device_id].js");
const siteHealthTool = require("../api/spike/monitoring/sites/[site_id].js");

function invoke(handler, { method = "GET", query }) {
  const result = { statusCode: undefined, headers: {}, body: undefined };
  const response = {
    setHeader(name, value) {
      result.headers[name] = value;
    },
    status(code) {
      result.statusCode = code;
      return this;
    },
    json(body) {
      result.body = body;
      return this;
    }
  };
  handler({ method, query }, response);
  return result;
}

test("device tool exposes the canonical site relation", () => {
  const result = invoke(deviceTool, { query: { device_id: "POS-KZN17-03" } });

  assert.equal(result.statusCode, 200);
  assert.equal(result.body.ok, true);
  assert.equal(result.body.data.site_id, "SITE-KZN-17");
  assert.equal(result.body.evidence_ref, "EVD-SPIKE-CMDB-001");
  assert.match(result.body.observed_at, /^\d{4}-\d{2}-\d{2}T/);
});

test("unknown device stays a structured domain observation", () => {
  const result = invoke(deviceTool, { query: { device_id: "UNKNOWN" } });

  assert.equal(result.statusCode, 200);
  assert.deepEqual(result.body.error, {
    code: "NOT_FOUND",
    message: "Device not found"
  });
});

test("site-health tool shows a healthy site with one unreachable POS", () => {
  const result = invoke(siteHealthTool, { query: { site_id: "SITE-KZN-17" } });

  assert.equal(result.statusCode, 200);
  assert.equal(result.body.ok, true);
  assert.equal(result.body.data.overall_status, "HEALTHY");
  assert.deepEqual(result.body.data.peer_devices.at(-1), {
    device_id: "POS-KZN17-03",
    status: "UNREACHABLE"
  });
});

test("unknown site stays a structured domain observation", () => {
  const result = invoke(siteHealthTool, { query: { site_id: "UNKNOWN" } });

  assert.equal(result.statusCode, 200);
  assert.deepEqual(result.body.error, {
    code: "NOT_FOUND",
    message: "Site not found"
  });
});

test("only GET is supported", () => {
  const result = invoke(deviceTool, {
    method: "POST",
    query: { device_id: "POS-KZN17-03" }
  });

  assert.equal(result.statusCode, 405);
  assert.equal(result.headers.Allow, "GET");
});
