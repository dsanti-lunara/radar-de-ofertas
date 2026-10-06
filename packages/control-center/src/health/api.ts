/**
 * Cliente REST do Home health overview (RDR-057, AUT-393).
 *
 * O erro é sempre acionável e nunca carrega o corpo bruto da resposta nem a
 * mensagem do transporte, então uma credencial eventualmente presente na
 * request/response não vaza para a UI (docs/12_SECURITY_AND_COMPLIANCE.md).
 */

import { parseHomeHealth, type HomeHealth } from "../contracts";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export const CONTROL_CENTER_ACTION =
  "Verificar se o radar-api está em execução local (127.0.0.1) e repetir a consulta";

export class HealthPollError extends Error {
  readonly code: string;
  readonly action: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "HealthPollError";
    this.code = code;
    this.action = CONTROL_CENTER_ACTION;
  }
}

export async function fetchHomeHealth(
  url: string,
  fetchImpl: FetchLike = fetch,
): Promise<HomeHealth> {
  let response: Response;
  try {
    response = await fetchImpl(url, { headers: { Accept: "application/json" } });
  } catch {
    // A causa do transporte é descartada de propósito (pode conter credenciais).
    throw new HealthPollError("CONTROL_CENTER_UNREACHABLE", "Control Center API inacessível");
  }

  if (!response.ok) {
    throw new HealthPollError(
      "CONTROL_CENTER_HTTP_ERROR",
      `Control Center API respondeu HTTP ${response.status}`,
    );
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new HealthPollError("HEALTH_OVERVIEW_INVALID", "Resposta de saúde não é JSON válido");
  }

  try {
    return parseHomeHealth(payload);
  } catch {
    throw new HealthPollError("HEALTH_OVERVIEW_INVALID", "Contrato de saúde inválido");
  }
}
