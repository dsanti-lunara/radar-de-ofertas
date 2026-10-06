/**
 * Estados assíncronos da UI de review (RDR-058..RDR-060).
 *
 * A consulta é isolada da camada React para ser testável sem DOM: cada loader
 * devolve `loading`/`ready`/`empty`/`unavailable`, então a UI sempre mostra um
 * feedback real e nunca uma tela vazia fingindo estar carregada.
 */

import {
  fetchReviewDetail,
  fetchReviewInbox,
  ReviewApiError,
  type FetchLike,
} from "./api";
import type { DetailEnvelope, ReviewInbox } from "./contracts";

export type InboxState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly inbox: ReviewInbox }
  | { readonly kind: "empty" }
  | { readonly kind: "unavailable"; readonly error: ReviewApiError };

export type DetailState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly detail: DetailEnvelope }
  | { readonly kind: "unavailable"; readonly error: ReviewApiError };

function toApiError(error: unknown): ReviewApiError {
  if (error instanceof ReviewApiError) {
    return error;
  }
  return new ReviewApiError("REVIEW_API_UNREACHABLE", "Control Center API inacessível");
}

export async function loadInbox(url: string, fetchImpl?: FetchLike): Promise<InboxState> {
  try {
    const inbox = await fetchReviewInbox(url, fetchImpl);
    if (inbox.items.length === 0) {
      return { kind: "empty" };
    }
    return { kind: "ready", inbox };
  } catch (error) {
    return { kind: "unavailable", error: toApiError(error) };
  }
}

export async function loadDetail(
  candidateId: string,
  fetchImpl?: FetchLike,
): Promise<DetailState> {
  try {
    const detail = await fetchReviewDetail(`/review/candidates/${candidateId}`, fetchImpl);
    return { kind: "ready", detail };
  } catch (error) {
    return { kind: "unavailable", error: toApiError(error) };
  }
}
