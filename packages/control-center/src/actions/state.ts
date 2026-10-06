/**
 * Estados assíncronos da central de HumanActions (RDR-063).
 *
 * A consulta é isolada da camada React para ser testável sem DOM: cada loader
 * devolve `loading`/`ready`/`empty`/`unavailable`, então a UI sempre mostra um
 * feedback real e nunca uma tela vazia fingindo estar carregada.
 */

import {
  fetchHumanAction,
  fetchHumanActions,
  HumanActionsApiError,
  type FetchLike,
} from "./api";
import type { HumanAction, HumanActionList } from "./contracts";

export type InboxState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly inbox: HumanActionList }
  | { readonly kind: "empty" }
  | { readonly kind: "unavailable"; readonly error: HumanActionsApiError };

export type DetailState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly action: HumanAction }
  | { readonly kind: "unavailable"; readonly error: HumanActionsApiError };

function toApiError(error: unknown): HumanActionsApiError {
  if (error instanceof HumanActionsApiError) {
    return error;
  }
  return new HumanActionsApiError("HUMAN_ACTIONS_API_UNREACHABLE", "Control Center API inacessível");
}

export async function loadInbox(
  url: string,
  fetchImpl?: FetchLike,
): Promise<InboxState> {
  try {
    const inbox = await fetchHumanActions(url, fetchImpl);
    if (inbox.human_actions.length === 0) {
      return { kind: "empty" };
    }
    return { kind: "ready", inbox };
  } catch (error) {
    return { kind: "unavailable", error: toApiError(error) };
  }
}

export async function loadDetail(
  humanActionId: string,
  fetchImpl?: FetchLike,
): Promise<DetailState> {
  try {
    const action = await fetchHumanAction(`/human-actions/${humanActionId}`, fetchImpl);
    return { kind: "ready", action };
  } catch (error) {
    return { kind: "unavailable", error: toApiError(error) };
  }
}
