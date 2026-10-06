import { describe, expect, it } from "vitest";

import {
  parseHumanAction,
  parseHumanActionList,
  parseHumanActionResolveResult,
} from "./contracts";
import {
  humanActionFixture,
  humanActionListFixture,
  humanActionResolveResultFixture,
} from "./fixtures";

describe("human action contracts", () => {
  it("parses a versioned list with impact and resolution guidance", () => {
    const parsed = parseHumanActionList(humanActionListFixture);
    expect(parsed.schema_version).toBe("1.0");
    expect(parsed.human_actions).toHaveLength(2);
    expect(parsed.human_actions[0]?.impact).toBeTruthy();
    expect(parsed.human_actions[0]?.resolution.resolvable_via_center).toBe(true);
  });

  it("keeps a delegated resolution non-executable", () => {
    const parsed = parseHumanAction(humanActionListFixture.human_actions[1]);
    expect(parsed.resolution.mode).toBe("PUBLICATION_RESOLUTION");
    expect(parsed.resolution.resolvable_via_center).toBe(false);
  });

  it("rejects an unsupported schema version", () => {
    expect(() =>
      parseHumanActionList({ ...humanActionListFixture, schema_version: "9.9" }),
    ).toThrow(/schema_version/);
  });

  it("rejects a missing resolution block", () => {
    const withoutResolution: Record<string, unknown> = { ...humanActionFixture };
    delete withoutResolution["resolution"];
    expect(() => parseHumanAction(withoutResolution)).toThrow(/resolution/);
  });

  it("parses a resolve result", () => {
    const parsed = parseHumanActionResolveResult(humanActionResolveResultFixture);
    expect(parsed.status).toBe("RESOLVED");
    expect(parsed.idempotent_replay).toBe(false);
    expect(parsed.human_action.status).toBe("RESOLVED");
  });
});
