import { describe, expect, it } from "vitest";

import { SystemApiError, type FetchLike } from "./api";
import { integrationsFixture, jobsFixture } from "./fixtures";
import { loadIntegrations, loadJobs } from "./state";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("loadIntegrations", () => {
  it("retorna ready com dados reais", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse(integrationsFixture);
    expect((await loadIntegrations("/integrations", fetchImpl)).kind).toBe("ready");
  });

  it("retorna empty para lista vazia real", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse({
        schema_version: "1.0",
        status: "OK",
        count: 0,
        correlation_id: "cid",
        integrations: [],
      });
    expect((await loadIntegrations("/integrations", fetchImpl)).kind).toBe("empty");
  });

  it("retorna unavailable sem lançar", async () => {
    const fetchImpl: FetchLike = async () => {
      throw new Error("offline");
    };
    const state = await loadIntegrations("/integrations", fetchImpl);
    expect(state.kind).toBe("unavailable");
    if (state.kind === "unavailable") {
      expect(state.error).toBeInstanceOf(SystemApiError);
    }
  });
});

describe("loadJobs", () => {
  it("retorna ready com o listing", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse(jobsFixture);
    const state = await loadJobs("/jobs", fetchImpl);
    expect(state.kind).toBe("ready");
  });

  it("retorna unavailable sem lançar", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse({ error: { code: "RAD-WF-006", message: "x", retryable: false } }, 422);
    expect((await loadJobs("/jobs", fetchImpl)).kind).toBe("unavailable");
  });
});
