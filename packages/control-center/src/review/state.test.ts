import { describe, expect, it } from "vitest";

import type { FetchLike } from "./api";
import { detailFixture, inboxFixture } from "./fixtures";
import { loadDetail, loadInbox } from "./state";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("loadInbox", () => {
  it("devolve ready quando há Candidates", async () => {
    const state = await loadInbox("/review/inbox", async () => jsonResponse(inboxFixture));
    expect(state.kind).toBe("ready");
    if (state.kind === "ready") {
      expect(state.inbox.count).toBe(1);
    }
  });

  it("devolve empty quando o Inbox responde sem itens", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse({ ...inboxFixture, count: 0, items: [] });
    const state = await loadInbox("/review/inbox", fetchImpl);
    expect(state.kind).toBe("empty");
  });

  it("devolve unavailable (não lança) quando a API cai", async () => {
    const state = await loadInbox("/review/inbox", async () => {
      throw new Error("offline");
    });
    expect(state.kind).toBe("unavailable");
    if (state.kind === "unavailable") {
      expect(state.error.code).toBe("REVIEW_API_UNREACHABLE");
    }
  });
});

describe("loadDetail", () => {
  it("devolve ready com o detalhe real", async () => {
    const state = await loadDetail("cand_1", async () => jsonResponse(detailFixture));
    expect(state.kind).toBe("ready");
    if (state.kind === "ready") {
      expect(state.detail.detail.candidate.candidate_id).toBe("cand_1");
    }
  });

  it("devolve unavailable em erro estruturado", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse({ error: { code: "RAD-UI-003", message: "x", retryable: false } }, 404);
    const state = await loadDetail("cand_missing", fetchImpl);
    expect(state.kind).toBe("unavailable");
    if (state.kind === "unavailable") {
      expect(state.error.code).toBe("RAD-UI-003");
    }
  });
});
