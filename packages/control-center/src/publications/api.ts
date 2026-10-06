/**
 * Cliente REST da Publication Inbox/detail e das ações auditadas (RDR-061/062).
 *
 * Os erros são sempre acionáveis e nunca carregam o corpo bruto da resposta; um
 * erro estruturado do `radar-api` é propagado apenas com `code`/`message`/
 * `retryable`, para a UI decidir sem vazar credenciais ou conteúdo de marketplace
 * (docs/12_SECURITY_AND_COMPLIANCE.md).
 */

import {
  parsePublicationDetail,
  parsePublicationInbox,
  parsePublicationRevalidation,
  type PublicationAction,
  type PublicationDetailEnvelope,
  type PublicationInbox,
  type PublicationRevalidation,
} from "./contracts";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export const PUBLICATIONS_ACTION =
  "Verificar se o radar-api está em execução local (127.0.0.1) e repetir a consulta";

export class PublicationsApiError extends Error {
  readonly code: string;
  readonly action: string;
  readonly retryable: boolean;

  constructor(code: string, message: string, retryable = false) {
    super(message);
    this.name = "PublicationsApiError";
    this.code = code;
    this.action = PUBLICATIONS_ACTION;
    this.retryable = retryable;
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new PublicationsApiError(
      "PUBLICATIONS_API_INVALID",
      "Resposta inválida do Control Center",
    );
  }
}

function structuredError(payload: unknown, status: number): PublicationsApiError {
  if (typeof payload === "object" && payload !== null && "error" in payload) {
    const error = (payload as { error?: unknown }).error;
    if (typeof error === "object" && error !== null) {
      const code = (error as { code?: unknown }).code;
      const message = (error as { message?: unknown }).message;
      const retryable = (error as { retryable?: unknown }).retryable;
      if (typeof code === "string" && typeof message === "string") {
        return new PublicationsApiError(code, message, retryable === true);
      }
    }
  }
  return new PublicationsApiError(
    "PUBLICATIONS_API_HTTP_ERROR",
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
    throw new PublicationsApiError("PUBLICATIONS_API_UNREACHABLE", "Control Center API inacessível");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => undefined);
    throw structuredError(payload, response.status);
  }
  return readJson(response);
}

export async function fetchPublicationInbox(
  url: string,
  fetchImpl: FetchLike = fetch,
): Promise<PublicationInbox> {
  const payload = await request(url, fetchImpl, { headers: { Accept: "application/json" } });
  try {
    return parsePublicationInbox(payload);
  } catch {
    throw new PublicationsApiError("PUBLICATIONS_INBOX_INVALID", "Contrato do Inbox inválido");
  }
}

export async function fetchPublicationDetail(
  path: string,
  entryId: string,
  fetchImpl: FetchLike = fetch,
): Promise<PublicationDetailEnvelope> {
  const payload = await request(path, fetchImpl, { headers: { Accept: "application/json" } });
  try {
    return parsePublicationDetail(payload, entryId);
  } catch {
    throw new PublicationsApiError("PUBLICATIONS_DETAIL_INVALID", "Contrato do detalhe inválido");
  }
}

export async function submitPublicationAction(
  publicationId: string,
  action: PublicationAction,
  reason: string,
  fetchImpl: FetchLike = fetch,
): Promise<PublicationRevalidation | null> {
  const payload = await request(`/publications/${publicationId}/${action}`, fetchImpl, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ schema_version: "1.0", reason: reason.trim() === "" ? null : reason.trim() }),
  });
  if (action !== "revalidate") {
    return null;
  }
  try {
    return parsePublicationRevalidation(payload);
  } catch {
    throw new PublicationsApiError(
      "PUBLICATIONS_REVALIDATION_INVALID",
      "Contrato da revalidação inválido",
    );
  }
}

export interface PublicationApprovalInput {
  readonly content_generation_id: string;
  readonly destination_id: string;
  readonly idempotency_key: string;
}

export interface PublicationApprovalResult {
  readonly publication_id: string;
  readonly status: string;
  readonly external_message_id: string | null;
}

export async function submitPublicationApproval(
  opportunityId: string,
  input: PublicationApprovalInput,
  fetchImpl: FetchLike = fetch,
): Promise<PublicationApprovalResult> {
  const payload = await request(
    `/opportunities/${opportunityId}/publications`,
    fetchImpl,
    {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({
        schema_version: "1.0",
        content_generation_id: input.content_generation_id,
        destination_id: input.destination_id,
        idempotency_key: input.idempotency_key,
        publication_approved: true,
      }),
    },
  );
  if (typeof payload !== "object" || payload === null) {
    throw new PublicationsApiError("PUBLICATIONS_APPROVAL_INVALID", "Contrato da publicação inválido");
  }
  const record = payload as Record<string, unknown>;
  const publicationId = record["publication_id"];
  const status = record["status"];
  if (typeof publicationId !== "string" || typeof status !== "string") {
    throw new PublicationsApiError("PUBLICATIONS_APPROVAL_INVALID", "Contrato da publicação inválido");
  }
  const external = record["external_message_id"];
  return {
    publication_id: publicationId,
    status,
    external_message_id: typeof external === "string" ? external : null,
  };
}
