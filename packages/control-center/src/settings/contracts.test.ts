import { describe, expect, it } from "vitest";

import {
  parseModeChangeResult,
  parseSettings,
  parseStopChangeResult,
} from "./contracts";
import { modeChangeFixture, settingsFixture, stopChangeFixture } from "./fixtures";

describe("settings contracts", () => {
  it("parses the versioned settings snapshot", () => {
    const parsed = parseSettings(settingsFixture);
    expect(parsed.automation_policy.default_mode).toBe("SHADOW");
    expect(parsed.compliance_policy.status).toBe("ACTIVE");
    expect(parsed.publication_policy.hard_cap_per_day).toBe(12);
    expect(parsed.operations.global_mode).toBe("RUNNING");
  });

  it("keeps AUTO eligibility read-only and fail-closed", () => {
    const parsed = parseSettings(settingsFixture);
    expect(parsed.auto_eligibility.eligible).toBe(false);
    expect(parsed.auto_eligibility.promotes_automatically).toBe(false);
    expect(parsed.auto_eligibility.requires_human_decision).toBe(true);
    expect(parsed.auto_eligibility.criteria).toHaveLength(7);
  });

  it("parses the operational change results", () => {
    expect(parseModeChangeResult(modeChangeFixture).state.global_mode).toBe("PAUSED");
    expect(parseStopChangeResult(stopChangeFixture).state.stop_external_actions).toBe(true);
  });

  it("rejects an unsupported schema version", () => {
    expect(() => parseSettings({ ...settingsFixture, schema_version: "9.9" })).toThrow(
      /schema_version/,
    );
  });
});
