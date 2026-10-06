import { describe, expect, it } from "vitest";

import type { FetchLike } from "./api";
import { parsePublicationInbox } from "./contracts";
import { inboxFixture, previewDetailFixture, publicationDetailFixture } from "./fixtures";
import { detailPath, loadDetail, loadInbox } from "./state";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("detailPath", () => {
  it("usa a rota de preview para entradas PREVIEW", () => {
    const inbox = parsePublicationInbox(inboxFixture);
    expect(detailPath(inbox.items[1]!)).toBe("/publications/preview/opp_2");
  });

  it("usa a rota de publication para entradas PUBLICATIONS", () => {
    const inbox = parsePublicationInbox(inboxFixture);
    expect(detailPath(inbox.items[0]!)).toBe("/publications/pub_1");
  });
});

describe("loadInbox", () => {
  it("devolve ready com publicações reais", async () => {
    const state = await loadInbox("/publications", async () => jsonResponse(inboxFixture));
    expect(state.kind).toBe("ready");
    if (state.kind === "ready") {
      expect(state.inbox.count).toBe(2);
    }
  });

  it("devolve empty quando o Inbox responde sem itens", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse({ ...inboxFixture, count: 0, items: [] });
    const state = await loadInbox("/publications", fetchImpl);
    expect(state.kind).toBe("empty");
  });

  it("devolve unavailable (não lança) quando a API cai", async () => {
    const state = await loadInbox("/publications", async () => {
      throw new Error("offline");
    });
    expect(state.kind).toBe("unavailable");
    if (state.kind === "unavailable") {
      expect(state.error.code).toBe("PUBLICATIONS_API_UNREACHABLE");
    }
  });
});

describe("loadDetail", () => {
  it("devolve ready para publicações e previews", async () => {
    const inbox = parsePublicationInbox(inboxFixture);
    const publication = await loadDetail(inbox.items[0]!, async () =>
      jsonResponse(publicationDetailFixture),
    );
    expect(publication.kind).toBe("ready");

    const preview = await loadDetail(inbox.items[1]!, async () =>
      jsonResponse(previewDetailFixture),
    );
    expect(preview.kind).toBe("ready");
    if (preview.kind === "ready") {
      expect(preview.detail.detail.kind).toBe("PREVIEW");
    }
  });

  it("devolve unavailable em erro estruturado", async () => {
    const inbox = parsePublicationInbox(inboxFixture);
    const fetchImpl: FetchLike = async () =>
      jsonResponse({ error: { code: "RAD-PUB-002", message: "x", retryable: false } }, 404);
    const state = await loadDetail(inbox.items[0]!, fetchImpl);
    expect(state.kind).toBe("unavailable");
    if (state.kind === "unavailable") {
      expect(state.error.code).toBe("RAD-PUB-002");
    }
  });
});
