import { describe, expect, it } from "vitest";

import {
  parsePublicationDetail,
  parsePublicationInbox,
  parsePublicationRevalidation,
} from "./contracts";
import {
  inboxFixture,
  previewDetailFixture,
  publicationDetailFixture,
} from "./fixtures";

describe("parsePublicationInbox", () => {
  it("lê o Inbox real com PUBLICATION e PREVIEW", () => {
    const inbox = parsePublicationInbox(inboxFixture);
    expect(inbox.count).toBe(2);
    expect(inbox.items[0]?.kind).toBe("PUBLICATION");
    expect(inbox.items[0]?.external_message_id).toBe("fake-telegram-dest-tg-sandbox-pub_1");
    expect(inbox.items[1]?.kind).toBe("PREVIEW");
    expect(inbox.items[1]?.publication_id).toBeNull();
  });

  it("rejeita schema_version não suportado", () => {
    expect(() => parsePublicationInbox({ ...inboxFixture, schema_version: "2.0" })).toThrow();
  });
});

describe("parsePublicationDetail", () => {
  it("lê o detalhe de uma publicação com link, tracking e timeline", () => {
    const envelope = parsePublicationDetail(publicationDetailFixture, "pub_1");
    expect(envelope.detail.kind).toBe("PUBLICATION");
    expect(envelope.detail.link?.tracking_label).toBe("rbtgoffer");
    expect(envelope.detail.revision).toBe(1);
    expect(envelope.detail.timeline.map((entry) => entry.event_type)).toEqual([
      "CREATED",
      "PUBLISHED",
    ]);
  });

  it("lê o detalhe de um preview sem publicação persistida", () => {
    const envelope = parsePublicationDetail(previewDetailFixture, "preview:opp_2");
    expect(envelope.detail.kind).toBe("PREVIEW");
    expect(envelope.detail.publication).toBeNull();
    expect(envelope.detail.preview?.content_generation_id).toBe("ctg_2");
  });

  it("rejeita kind inválido", () => {
    const broken = JSON.parse(JSON.stringify(publicationDetailFixture));
    broken.detail.kind = "OTHER";
    expect(() => parsePublicationDetail(broken, "pub_1")).toThrow();
  });
});

describe("parsePublicationRevalidation", () => {
  it("lê o resultado da revalidação auditada", () => {
    const result = parsePublicationRevalidation({
      schema_version: "1.0",
      status: "OK",
      revalidation: {
        publication_id: "pub_1",
        allowed: false,
        reason_code: "REVALIDATION_REQUIRED",
        message: "conteúdo stale",
        content_generation_id: "ctg_1",
        checked_at: "2026-10-06T18:00:00+00:00",
      },
    });
    expect(result.allowed).toBe(false);
    expect(result.reason_code).toBe("REVALIDATION_REQUIRED");
  });
});
