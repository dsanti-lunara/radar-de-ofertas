import { describe, expect, it } from "vitest";

import {
  parseHumanReviewList,
  parseReviewDetail,
  parseReviewInbox,
  parseReviewResult,
  REVIEW_SCHEMA_VERSION,
} from "./contracts";
import { detailFixture, inboxFixture, reviewResultFixture } from "./fixtures";

describe("parseReviewInbox", () => {
  it("aceita o payload versionado do Inbox", () => {
    const inbox = parseReviewInbox(inboxFixture);
    expect(inbox.schema_version).toBe(REVIEW_SCHEMA_VERSION);
    expect(inbox.count).toBe(1);
    expect(inbox.items[0]?.candidate_id).toBe("cand_1");
    expect(inbox.items[0]?.ai_decision).toBe("APPROVE");
    expect(inbox.items[0]?.human_decision).toBeNull();
  });

  it("rejeita schema_version não suportado", () => {
    expect(() => parseReviewInbox({ ...inboxFixture, schema_version: "9.9" })).toThrow();
  });

  it("rejeita item sem campo obrigatório", () => {
    const item = { ...inboxFixture.items[0] } as Record<string, unknown>;
    delete item["marketplace"];
    expect(() => parseReviewInbox({ ...inboxFixture, items: [item] })).toThrow();
  });
});

describe("parseReviewDetail", () => {
  it("expõe breakdown, timeline, versões e o portão operacional", () => {
    const envelope = parseReviewDetail(detailFixture);
    expect(envelope.detail.evaluation?.decision).toBe("APPROVE");
    expect(envelope.detail.price_history).toHaveLength(1);
    expect(envelope.detail.timeline.map((entry) => entry.event_type)).toEqual([
      "CAPTURE_RECEIVED",
      "AI_REVIEW_RECORDED",
    ]);
    expect(envelope.detail.versions.ai_knowledge_version).toBe("knowledge-1.0");
    expect(envelope.detail.automation?.publish_allowed).toBe(false);
    expect(envelope.detail.automation?.automation_mode).toBe("SHADOW");
  });

  it("aceita detalhe sem Evaluation nem automação", () => {
    const detail = {
      ...detailFixture,
      detail: { ...detailFixture.detail, evaluation: null, automation: null },
    };
    const envelope = parseReviewDetail(detail);
    expect(envelope.detail.evaluation).toBeNull();
    expect(envelope.detail.automation).toBeNull();
  });
});

describe("parseReviewResult", () => {
  it("preserva a decisão IA e humana e o motivo", () => {
    const result = parseReviewResult(reviewResultFixture);
    expect(result.publication_authorized).toBe(false);
    expect(result.human_review.ai_decision).toBe("APPROVE");
    expect(result.human_review.human_decision).toBe("REJECT");
    expect(result.human_review.reason).toBe("Preço mudou");
  });

  it("rejeita human_decision fora do enum", () => {
    const bad = {
      ...reviewResultFixture,
      human_review: { ...reviewResultFixture.human_review, human_decision: "PUBLISH" },
    };
    expect(() => parseReviewResult(bad)).toThrow();
  });

  it("faz parse do edited_content do EDIT_CONTENT", () => {
    const payload = {
      ...reviewResultFixture,
      human_review: {
        ...reviewResultFixture.human_review,
        human_decision: "EDIT_CONTENT",
        edited_content: { headline: "h", body: "b", cta: "c" },
      },
    };
    const result = parseReviewResult(payload);
    expect(result.human_review.edited_content).toEqual({ headline: "h", body: "b", cta: "c" });
  });
});

describe("parseHumanReviewList", () => {
  it("aceita lista vazia como estado real", () => {
    const list = parseHumanReviewList({
      schema_version: "1.0",
      status: "OK",
      candidate_id: "cand_1",
      count: 0,
      human_reviews: [],
    });
    expect(list.count).toBe(0);
  });
});
