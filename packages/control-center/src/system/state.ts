/**
 * Estados assíncronos do Sistema (RDR-064, RDR-065).
 *
 * Cada loader devolve `loading`/`ready`/`empty`/`unavailable` e nunca lança,
 * para a UI mostrar um feedback real em vez de uma tela vazia.
 */

import {
  fetchIntegrations,
  fetchJobs,
  SystemApiError,
  type FetchLike,
} from "./api";
import type { IntegrationsList, JobsInbox } from "./contracts";

export type IntegrationsState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly list: IntegrationsList }
  | { readonly kind: "empty" }
  | { readonly kind: "unavailable"; readonly error: SystemApiError };

export type JobsState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly inbox: JobsInbox }
  | { readonly kind: "empty" }
  | { readonly kind: "unavailable"; readonly error: SystemApiError };

function toApiError(error: unknown): SystemApiError {
  if (error instanceof SystemApiError) {
    return error;
  }
  return new SystemApiError("SYSTEM_API_UNREACHABLE", "Control Center API inacessível");
}

export async function loadIntegrations(
  url: string,
  fetchImpl?: FetchLike,
): Promise<IntegrationsState> {
  try {
    const list = await fetchIntegrations(url, fetchImpl);
    if (list.integrations.length === 0) {
      return { kind: "empty" };
    }
    return { kind: "ready", list };
  } catch (error) {
    return { kind: "unavailable", error: toApiError(error) };
  }
}

export async function loadJobs(url: string, fetchImpl?: FetchLike): Promise<JobsState> {
  try {
    const inbox = await fetchJobs(url, fetchImpl);
    if (inbox.jobs.length === 0) {
      return { kind: "empty" };
    }
    return { kind: "ready", inbox };
  } catch (error) {
    return { kind: "unavailable", error: toApiError(error) };
  }
}
