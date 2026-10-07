import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { ApiClientError, apiUrl, displayApiError } from "../lib/api";

const nextConfigSource = readFileSync(
  new URL("../next.config.ts", import.meta.url),
  "utf8",
);

describe("Phase 9B public demo frontend errors", () => {
  it("keeps Product API browser traffic on the stable Vercel origin", () => {
    expect(apiUrl("/health")).toBe("/product-api/health");
    expect(nextConfigSource).toContain('source: "/product-api/:path*"');
    expect(nextConfigSource).toContain("p01--product-api--yxz5y8myjdln.code.run");
  });

  it("distinguishes local demo cooldown from provider quota", () => {
    const demoCooldown = new ApiClientError(
      429,
      "PUBLIC_DEMO_COOLDOWN",
      "Public demo run start is temporarily rate limited.",
      true,
    );
    const providerQuota = new ApiClientError(
      429,
      "RESOURCE_EXHAUSTED",
      "Provider quota exhausted.",
      true,
    );

    expect(displayApiError(demoCooldown)).toBe(
      "Слишком много новых запусков подряд. Повторите попытку через несколько секунд.",
    );
    expect(displayApiError(providerQuota)).toContain("AI-провайдеру");
    expect(displayApiError(providerQuota)).toContain("RESOURCE_EXHAUSTED");
  });
});
