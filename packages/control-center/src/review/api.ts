/**
 * Cliente REST do Opportunity Inbox/detail e da Human Review (RDR-058..RDR-060).
 *
 * Os erros são sempre acionáveis e nunca carregam o corpo bruto da resposta; um
 * erro estruturado do `radar-api` é propagado apenas com `code`/`message`/
 * `retryable` para a UI decidir sem vazar credenciais ou conteúdo de marketplace
 * (docs/12_SECURITY_AND_COMPLIANCE.md).
 */

import {
  parseHumanReviewList,
  parseReviewDetail,
  parseReviewInbox,
  parseReviewResult,
  type DetailEnvelope,
  type HumanDecision,
  type HumanReviewList,
  type ReviewInbox,
  type ReviewResult,
} from "./contracts";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export const REVIEW_ACTION =
  "Verificar se o radar-api está em execução local (127.0.0.1) e repetir a consulta";

export class ReviewApiError extends Error {
  readonly code: string;
  readonly action: string;
  readonly retryable: boolean;

  constructor(code: string, message: string, retryable = false) {
    super(message);
    this.name = "ReviewApiError";
    this.code = code;
    this.action = REVIEW_ACTION;
    this.retryable = retryable;
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new ReviewApiError("REVIEW_API_INVALID", "Resposta inválida do Control Center");
  }
}

function structuredError(payload: unknown, status: number): ReviewApiError {
  if (typeof payload === "object" && payload !== null && "error" in payload) {
    const error = (payload as { error?: unknown }).error;
    if (typeof error === "object" && error !== null) {
      const code = (error as { code?: unknown }).code;
      const message = (error as { message?: unknown }).message;
      const retryable = (error as { retryable?: unknown }).retryable;
      if (typeof code === "string" && typeof message === "string") {
        return new ReviewApiError(code, message, retryable === true);
      }
    }
  }
  return new ReviewApiError(
    "REVIEW_API_HTTP_ERROR",
    `Control Center API respondeu HTTP ${status}`,
  );
}

async function request(
  url: string,
  fetchImpl: FetchLike,
  init?: RequestInit,
): Promise<unknown> {
  let response: Response;
  try {
    response = await fetchImpl(url, init);
  } catch {
    // A causa do transporte é descartada de propósito (pode conter credenciais).
    throw new ReviewApiError("REVIEW_API_UNREACHABLE", "Control Center API inacessível");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => undefined);
    throw structuredError(payload, response.status);
  }
  return readJson(response);
}

export async function fetchReviewInbox(
  url: string,
  fetchImpl: FetchLike = fetch,
): Promise<ReviewInbox> {
  const payload = await request(url, fetchImpl, { headers: { Accept: "application/json" } });
  try {
    return parseReviewInbox(payload);
  } catch {
    throw new ReviewApiError("REVIEW_INBOX_INVALID", "Contrato do Inbox inválido");
  }
}

export async function fetchReviewDetail(
  url: string,
  fetchImpl: FetchLike = fetch,
): Promise<DetailEnvelope> {
  const payload = await request(url, fetchImpl, { headers: { Accept: "application/json" } });
  try {
    return parseReviewDetail(payload);
  } catch {
    throw new ReviewApiError("REVIEW_DETAIL_INVALID", "Contrato do detalhe inválido");
  }
}

export async function fetchHumanReviews(
  url: string,
  fetchImpl: FetchLike = fetch,
): Promise<HumanReviewList> {
  const payload = await request(url, fetchImpl, { headers: { Accept: "application/json" } });
  try {
    return parseHumanReviewList(payload);
  } catch {
    throw new ReviewApiError("REVIEW_LIST_INVALID", "Contrato das reviews inválido");
  }
}

export interface SubmitReviewInput {
  readonly human_decision: HumanDecision;
  readonly reason: string;
  readonly ai_review_id?: string | null;
  readonly note?: string | null;
  readonly edited_content?: {
    readonly headline: string;
    readonly body: string;
    readonly cta: string;
  } | null;
}

export async function submitHumanReview(
  url: string,
  input: SubmitReviewInput,
  fetchImpl: FetchLike = fetch,
): Promise<ReviewResult> {
  const body = {
    schema_version: "1.0",
    human_decision: input.human_decision,
    reason: input.reason,
    ai_review_id: input.ai_review_id ?? null,
    note: input.note ?? null,
    edited_content: input.edited_content ?? null,
  };
  const payload = await request(url, fetchImpl, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  try {
    return parseReviewResult(payload);
  } catch {
    throw new ReviewApiError("REVIEW_RESULT_INVALID", "Contrato da review inválido");
  }
}
