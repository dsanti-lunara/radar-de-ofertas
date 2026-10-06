/**
 * Cliente REST do Sistema: integrações e Jobs/Dead Jobs (RDR-064, RDR-065).
 *
 * Erros estruturados do `radar-api` são propagados apenas com `code`/`message`/
 * `retryable`; o corpo bruto e a causa do transporte nunca são expostos.
 */

import {
  parseIntegrationsList,
  parseIntegrationUpdateResult,
  parseJobsInbox,
  type IntegrationsList,
  type IntegrationUpdateResult,
  type JobsInbox,
} from "./contracts";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export const SYSTEM_ACTION =
  "Verificar se o radar-api está em execução local (127.0.0.1) e repetir a consulta";

export class SystemApiError extends Error {
  readonly code: string;
  readonly action: string;
  readonly retryable: boolean;

  constructor(code: string, message: string, retryable = false) {
    super(message);
    this.name = "SystemApiError";
    this.code = code;
    this.action = SYSTEM_ACTION;
    this.retryable = retryable;
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new SystemApiError("SYSTEM_API_INVALID", "Resposta inválida do Control Center");
  }
}

function structuredError(payload: unknown, status: number): SystemApiError {
  if (typeof payload === "object" && payload !== null && "error" in payload) {
    const error = (payload as { error?: unknown }).error;
    if (typeof error === "object" && error !== null) {
      const code = (error as { code?: unknown }).code;
      const message = (error as { message?: unknown }).message;
      const retryable = (error as { retryable?: unknown }).retryable;
      if (typeof code === "string" && typeof message === "string") {
        return new SystemApiError(code, message, retryable === true);
      }
    }
  }
  return new SystemApiError("SYSTEM_API_HTTP_ERROR", `Control Center API respondeu HTTP ${status}`);
}

async function request(url: string, fetchImpl: FetchLike, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetchImpl(url, init);
  } catch {
    throw new SystemApiError("SYSTEM_API_UNREACHABLE", "Control Center API inacessível");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => undefined);
    throw structuredError(payload, response.status);
  }
  return readJson(response);
}

export async function fetchIntegrations(
  url: string,
  fetchImpl: FetchLike = fetch,
): Promise<IntegrationsList> {
  const payload = await request(url, fetchImpl, { headers: { Accept: "application/json" } });
  try {
    return parseIntegrationsList(payload);
  } catch {
    throw new SystemApiError("SYSTEM_INTEGRATIONS_INVALID", "Contrato de integrações inválido");
  }
}

export async function fetchJobs(url: string, fetchImpl: FetchLike = fetch): Promise<JobsInbox> {
  const payload = await request(url, fetchImpl, { headers: { Accept: "application/json" } });
  try {
    return parseJobsInbox(payload);
  } catch {
    throw new SystemApiError("SYSTEM_JOBS_INVALID", "Contrato de Jobs inválido");
  }
}

export async function setIntegrationState(
  name: string,
  state: string,
  summary: string | null,
  fetchImpl: FetchLike = fetch,
): Promise<IntegrationUpdateResult> {
  const payload = await request(`/integrations/${name}`, fetchImpl, {
    method: "PUT",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({
      schema_version: "1.0",
      state,
      summary: summary === null || summary.trim() === "" ? null : summary.trim(),
    }),
  });
  try {
    return parseIntegrationUpdateResult(payload);
  } catch {
    throw new SystemApiError("SYSTEM_INTEGRATION_UPDATE_INVALID", "Contrato de integração inválido");
  }
}
