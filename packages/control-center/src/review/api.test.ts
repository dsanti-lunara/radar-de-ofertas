import { describe, expect, it } from "vitest";

import {
  fetchHumanReviews,
  fetchReviewDetail,
  fetchReviewInbox,
  ReviewApiError,
  submitHumanReview,
  type FetchLike,
} from "./api";
import { detailFixture, inboxFixture, reviewResultFixture } from "./fixtures";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("fetchReviewInbox", () => {
  it("consome o read model pela fronteira REST local", async () => {
    const calls: string[] = [];
    const fetchImpl: FetchLike = async (input) => {
      calls.push(input);
      return jsonResponse(inboxFixture);
    };
    const inbox = await fetchReviewInbox("/review/inbox", fetchImpl);
    expect(calls).toEqual(["/review/inbox"]);
    expect(inbox.items[0]?.candidate_id).toBe("cand_1");
  });

  it("propaga o erro estruturado do radar-api sem o corpo bruto", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse(
        {
          error: { code: "RAD-UI-003", message: "Candidate da review não encontrado", retryable: false },
        },
        404,
      );
    const error = (await fetchReviewInbox("/review/inbox", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as ReviewApiError;
    expect(error.code).toBe("RAD-UI-003");
    expect(error.retryable).toBe(false);
    expect(error.action.length).toBeGreaterThan(0);
  });

  it("não vaza a causa do transporte em falha de rede", async () => {
    const secret = "RADAR_SUPER_SECRET_TOKEN";
    const fetchImpl: FetchLike = async () => {
      throw new Error(`connect failed with ${secret}`);
    };
    const error = (await fetchReviewInbox("/review/inbox", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as ReviewApiError;
    expect(error.code).toBe("REVIEW_API_UNREACHABLE");
    expect(error.message).not.toContain(secret);
    expect(error.action).not.toContain(secret);
  });

  it("rejeita contrato inválido", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse({ ...inboxFixture, schema_version: "9.9" });
    const error = (await fetchReviewInbox("/review/inbox", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as ReviewApiError;
    expect(error.code).toBe("REVIEW_INBOX_INVALID");
  });
});

describe("fetchReviewDetail", () => {
  it("consome o detalhe versionado", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse(detailFixture);
    const detail = await fetchReviewDetail("/review/candidates/cand_1", fetchImpl);
    expect(detail.detail.candidate.candidate_id).toBe("cand_1");
  });
});

describe("fetchHumanReviews", () => {
  it("consome a lista de reviews", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse({
        schema_version: "1.0",
        status: "OK",
        candidate_id: "cand_1",
        count: 0,
        human_reviews: [],
      });
    const list = await fetchHumanReviews("/candidates/cand_1/human-reviews", fetchImpl);
    expect(list.count).toBe(0);
  });
});

describe("submitHumanReview", () => {
  it("envia decisão, motivo e Correlation ID pelo POST", async () => {
    let method: string | undefined;
    let body: unknown;
    const fetchImpl: FetchLike = async (_input, init) => {
      method = init?.method;
      body = init?.body === undefined ? undefined : JSON.parse(String(init.body));
      return jsonResponse(reviewResultFixture, 201);
    };
    const result = await submitHumanReview(
      "/candidates/cand_1/human-reviews",
      { human_decision: "REJECT", reason: "Preço mudou" },
      fetchImpl,
    );
    expect(method).toBe("POST");
    expect(body).toMatchObject({
      schema_version: "1.0",
      human_decision: "REJECT",
      reason: "Preço mudou",
    });
    expect(result.publication_authorized).toBe(false);
  });

  it("propaga RAD-UI-001 em ação inválida", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse(
        { error: { code: "RAD-UI-001", message: "human_decision inválida", retryable: false } },
        422,
      );
    const error = (await submitHumanReview(
      "/candidates/cand_1/human-reviews",
      { human_decision: "APPROVE", reason: "ok" },
      fetchImpl,
    ).catch((caught: unknown) => caught)) as ReviewApiError;
    expect(error.code).toBe("RAD-UI-001");
  });
});
