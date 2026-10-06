/**
 * Cliente REST de Configurações e controles operacionais (RDR-067, RDR-066).
 *
 * Erros estruturados do `radar-api` são propagados apenas com `code`/`message`/
 * `retryable`; o corpo bruto e a causa do transporte nunca são expostos.
 */

import {
  parseModeChangeResult,
  parseSettings,
  parseStopChangeResult,
  type ModeChangeResult,
  type SettingsSnapshot,
  type StopChangeResult,
} from "./contracts";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export const SETTINGS_ACTION =
  "Verificar se o radar-api está em execução local (127.0.0.1) e repetir a consulta";

export class SettingsApiError extends Error {
  readonly code: string;
  readonly action: string;
  readonly retryable: boolean;

  constructor(code: string, message: string, retryable = false) {
    super(message);
    this.name = "SettingsApiError";
    this.code = code;
    this.action = SETTINGS_ACTION;
    this.retryable = retryable;
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new SettingsApiError("SETTINGS_API_INVALID", "Resposta inválida do Control Center");
  }
}

function structuredError(payload: unknown, status: number): SettingsApiError {
  if (typeof payload === "object" && payload !== null && "error" in payload) {
    const error = (payload as { error?: unknown }).error;
    if (typeof error === "object" && error !== null) {
      const code = (error as { code?: unknown }).code;
      const message = (error as { message?: unknown }).message;
      const retryable = (error as { retryable?: unknown }).retryable;
      if (typeof code === "string" && typeof message === "string") {
        return new SettingsApiError(code, message, retryable === true);
      }
    }
  }
  return new SettingsApiError(
    "SETTINGS_API_HTTP_ERROR",
    `Control Center API respondeu HTTP ${status}`,
  );
}

async function request(url: string, fetchImpl: FetchLike, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetchImpl(url, init);
  } catch {
    throw new SettingsApiError("SETTINGS_API_UNREACHABLE", "Control Center API inacessível");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => undefined);
    throw structuredError(payload, response.status);
  }
  return readJson(response);
}

export async function fetchSettings(
  url: string,
  fetchImpl: FetchLike = fetch,
): Promise<SettingsSnapshot> {
  const payload = await request(url, fetchImpl, { headers: { Accept: "application/json" } });
  try {
    return parseSettings(payload);
  } catch {
    throw new SettingsApiError("SETTINGS_INVALID", "Contrato de Configurações inválido");
  }
}

export async function setGlobalMode(
  mode: string,
  reason: string | null,
  fetchImpl: FetchLike = fetch,
): Promise<ModeChangeResult> {
  const payload = await request("/operations/mode", fetchImpl, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({
      schema_version: "1.0",
      mode,
      reason: reason === null || reason.trim() === "" ? null : reason.trim(),
    }),
  });
  try {
    return parseModeChangeResult(payload);
  } catch {
    throw new SettingsApiError("SETTINGS_MODE_INVALID", "Contrato de modo inválido");
  }
}

export async function setStopExternalActions(
  engaged: boolean,
  reason: string | null,
  fetchImpl: FetchLike = fetch,
): Promise<StopChangeResult> {
  const payload = await request("/operations/stop-external-actions", fetchImpl, {
    method: engaged ? "POST" : "DELETE",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({
      schema_version: "1.0",
      reason: reason === null || reason.trim() === "" ? null : reason.trim(),
    }),
  });
  try {
    return parseStopChangeResult(payload);
  } catch {
    throw new SettingsApiError("SETTINGS_STOP_INVALID", "Contrato de kill switch inválido");
  }
}
