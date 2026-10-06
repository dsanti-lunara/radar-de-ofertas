/**
 * Estados assíncronos da UI de publicações (RDR-061/062).
 *
 * A consulta é isolada da camada React para ser testável sem DOM: cada loader
 * devolve `loading`/`ready`/`empty`/`unavailable`, então a UI sempre mostra um
 * feedback real e nunca uma tela vazia fingindo estar carregada.
 */

import {
  fetchPublicationDetail,
  fetchPublicationInbox,
  PublicationsApiError,
  type FetchLike,
} from "./api";
import type { PublicationDetailEnvelope, PublicationInbox, PublicationInboxItem } from "./contracts";

export type InboxState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly inbox: PublicationInbox }
  | { readonly kind: "empty" }
  | { readonly kind: "unavailable"; readonly error: PublicationsApiError };

export type DetailState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly detail: PublicationDetailEnvelope }
  | { readonly kind: "unavailable"; readonly error: PublicationsApiError };

function toApiError(error: unknown): PublicationsApiError {
  if (error instanceof PublicationsApiError) {
    return error;
  }
  return new PublicationsApiError(
    "PUBLICATIONS_API_UNREACHABLE",
    "Control Center API inacessível",
  );
}

export function detailPath(item: PublicationInboxItem): string {
  if (item.kind === "PREVIEW") {
    return `/publications/preview/${item.opportunity_id}`;
  }
  return `/publications/${item.publication_id ?? item.entry_id}`;
}

export async function loadInbox(url: string, fetchImpl?: FetchLike): Promise<InboxState> {
  try {
    const inbox = await fetchPublicationInbox(url, fetchImpl);
    if (inbox.items.length === 0) {
      return { kind: "empty" };
    }
    return { kind: "ready", inbox };
  } catch (error) {
    return { kind: "unavailable", error: toApiError(error) };
  }
}

export async function loadDetail(
  item: PublicationInboxItem,
  fetchImpl?: FetchLike,
): Promise<DetailState> {
  try {
    const detail = await fetchPublicationDetail(detailPath(item), item.entry_id, fetchImpl);
    return { kind: "ready", detail };
  } catch (error) {
    return { kind: "unavailable", error: toApiError(error) };
  }
}
