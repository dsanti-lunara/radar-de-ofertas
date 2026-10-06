/**
 * Cliente REST da central de HumanActions (RDR-063).
 *
 * Erros são sempre acionáveis e nunca carregam o corpo bruto da resposta; um
 * erro estruturado do `radar-api` é propagado apenas com `code`/`message`/
 * `retryable`, para a UI decidir sem vazar credenciais ou conteúdo externo
 * (docs/12_SECURITY_AND_COMPLIANCE.md).
 */

import {
  parseHumanAction,
  parseHumanActionList,
  parseHumanActionResolveResult,
  type HumanAction,
  type HumanActionList,
  type HumanActionResolveResult,
} from "./contracts";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export const HUMAN_ACTIONS_ACTION =
  "Verificar se o radar-api está em execução local (127.0.0.1) e repetir a consulta";

export class HumanActionsApiError extends Error {
  readonly code: string;
  readonly action: string;
  readonly retryable: boolean;

  constructor(code: string, message: string, retryable = false) {
    super(message);
    this.name = "HumanActionsApiError";
    this.code = code;
    this.action = HUMAN_ACTIONS_ACTION;
    this.retryable = retryable;
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new HumanActionsApiError(
      "HUMAN_ACTIONS_API_INVALID",
      "Resposta inválida do Control Center",
    );
  }
}

function structuredError(payload: unknown, status: number): HumanActionsApiError {
  if (typeof payload === "object" && payload !== null && "error" in payload) {
    const error = (payload as { error?: unknown }).error;
    if (typeof error === "object" && error !== null) {
      const code = (error as { code?: unknown }).code;
      const message = (error as { message?: unknown }).message;
      const retryable = (error as { retryable?: unknown }).retryable;
      if (typeof code === "string" && typeof message === "string") {
        return new HumanActionsApiError(code, message, retryable === true);
      }
    }
  }
  return new HumanActionsApiError(
    "HUMAN_ACTIONS_API_HTTP_ERROR",
    `Control Center API respondeu HTTP ${status}`,
  );
}

async function request(url: string, fetchImpl: FetchLike, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetchImpl(url, init);
  } catch {
    throw new HumanActionsApiError(
      "HUMAN_ACTIONS_API_UNREACHABLE",
      "Control Center API inacessível",
    );
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => undefined);
    throw structuredError(payload, response.status);
  }
  return readJson(response);
}

export async function fetchHumanActions(
  url: string,
  fetchImpl: FetchLike = fetch,
): Promise<HumanActionList> {
  const payload = await request(url, fetchImpl, { headers: { Accept: "application/json" } });
  try {
    return parseHumanActionList(payload);
  } catch {
    throw new HumanActionsApiError("HUMAN_ACTIONS_INBOX_INVALID", "Contrato de Ações inválido");
  }
}

export async function fetchHumanAction(
  path: string,
  fetchImpl: FetchLike = fetch,
): Promise<HumanAction> {
  const payload = await request(path, fetchImpl, { headers: { Accept: "application/json" } });
  try {
    return parseHumanAction(payload);
  } catch {
    throw new HumanActionsApiError("HUMAN_ACTIONS_DETAIL_INVALID", "Contrato da ação inválido");
  }
}

export async function resolveHumanAction(
  humanActionId: string,
  reason: string,
  fetchImpl: FetchLike = fetch,
): Promise<HumanActionResolveResult> {
  const payload = await request(`/human-actions/${humanActionId}/resolve`, fetchImpl, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ schema_version: "1.0", reason: reason.trim() }),
  });
  try {
    return parseHumanActionResolveResult(payload);
  } catch {
    throw new HumanActionsApiError(
      "HUMAN_ACTIONS_RESOLVE_INVALID",
      "Contrato de resolução inválido",
    );
  }
}
