import { describe, expect, it } from "vitest";

import { ApiClientError, displayApiError } from "../lib/api";

describe("Phase 9B public demo frontend errors", () => {
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
