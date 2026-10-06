import { describe, expect, it } from "vitest";

import {
  parseIntegrationsList,
  parseIntegrationUpdateResult,
  parseJobsInbox,
} from "./contracts";
import { integrationsFixture, jobsFixture } from "./fixtures";

describe("system contracts", () => {
  it("parses integrations with standardized state", () => {
    const parsed = parseIntegrationsList(integrationsFixture);
    expect(parsed.count).toBe(2);
    expect(parsed.integrations[0]?.state).toBe("ONLINE");
    expect(parsed.integrations[1]?.operational).toBe(false);
  });

  it("parses a jobs inbox with real statuses", () => {
    const parsed = parseJobsInbox(jobsFixture);
    expect(parsed.jobs[0]?.status).toBe("PENDING");
    expect(parsed.jobs[1]?.status).toBe("DEAD");
  });

  it("parses an integration update result", () => {
    const parsed = parseIntegrationUpdateResult({
      schema_version: "1.0",
      status: "OK",
      correlation_id: "cid",
      integration: integrationsFixture.integrations[0],
    });
    expect(parsed.integration.name).toBe("telegram");
  });

  it("rejects an unsupported schema version", () => {
    expect(() => parseJobsInbox({ ...jobsFixture, schema_version: "9.9" })).toThrow(
      /schema_version/,
    );
    expect(() =>
      parseIntegrationsList({ ...integrationsFixture, schema_version: "9.9" }),
    ).toThrow(/schema_version/);
  });
});
