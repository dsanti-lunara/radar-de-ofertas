import { describe, expect, it } from "vitest";

import { HumanActionsApiError, type FetchLike } from "./api";
import { humanActionFixture, humanActionListFixture } from "./fixtures";
import { loadDetail, loadInbox } from "./state";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("loadInbox", () => {
  it("retorna ready com dados reais", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse(humanActionListFixture);
    const state = await loadInbox("/human-actions", fetchImpl);
    expect(state.kind).toBe("ready");
  });

  it("retorna empty para uma lista vazia real", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse({ schema_version: "1.0", correlation_id: "cid", human_actions: [] });
    const state = await loadInbox("/human-actions", fetchImpl);
    expect(state.kind).toBe("empty");
  });

  it("retorna unavailable sem lançar", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse({ error: { code: "RAD-WF-006", message: "x", retryable: false } }, 422);
    const state = await loadInbox("/human-actions", fetchImpl);
    expect(state.kind).toBe("unavailable");
    if (state.kind === "unavailable") {
      expect(state.error).toBeInstanceOf(HumanActionsApiError);
    }
  });
});

describe("loadDetail", () => {
  it("retorna ready com o detalhe", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse(humanActionFixture);
    const state = await loadDetail("ha_1", fetchImpl);
    expect(state.kind).toBe("ready");
  });

  it("retorna unavailable sem lançar", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse({ error: { code: "RAD-WF-011", message: "x", retryable: false } }, 404);
    const state = await loadDetail("ha_missing", fetchImpl);
    expect(state.kind).toBe("unavailable");
  });
});
