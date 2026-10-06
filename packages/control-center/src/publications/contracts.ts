/**
 * Contratos da Publication Inbox/detail e das ações auditadas (RDR-061/062).
 *
 * Espelha os payloads versionados de `GET /publications`,
 * `GET /publications/{id}`, `GET /publications/preview/{opportunity_id}` e
 * `POST /publications/{id}/{revalidate,expire,cancel}` e
 * `POST /opportunities/{id}/publications`. A geração automática a partir do
 * OpenAPI substitui este espelho no ticket de contratos compartilhados (AUT-395).
 */

export const PUBLICATIONS_SCHEMA_VERSION = "1.0";

export type PublicationEntryKind = "PUBLICATION" | "PREVIEW";
export type PublicationAction = "revalidate" | "expire" | "cancel";

export interface PublicationProduct {
  readonly marketplace: string | null;
  readonly external_id: string | null;
  readonly title: string | null;
  readonly url: string | null;
  readonly brand: string | null;
  readonly current_price: string | null;
}

export interface PublicationLink {
  readonly affiliate_link_id: string;
  readonly affiliate_url: string;
  readonly productive: boolean;
  readonly generation_method: string;
  readonly status: string;
  readonly tracking_context_id: string;
  readonly tracking_internal_reference: string;
  readonly tracking_label: string;
  readonly tracking_mapping_version: string;
}

export interface PublicationPreview {
  readonly content_generation_id: string;
  readonly channel: string;
  readonly status: string;
  readonly stale: boolean;
  readonly renderer_version: string;
  readonly headline: string;
  readonly body: string;
  readonly cta: string;
  readonly text: string;
  readonly price: string | null;
  readonly affiliate_url: string;
  readonly disclosure: string;
  readonly tracking: Readonly<Record<string, unknown>>;
}

export interface PublicationValidation {
  readonly validated_at: string;
  readonly allowed: boolean | null;
  readonly reason_code: string | null;
  readonly source: string;
}

export interface PublicationTimelineEntry {
  readonly event_type: string;
  readonly source: string;
  readonly occurred_at: string;
  readonly correlation_id: string;
  readonly payload: Readonly<Record<string, unknown>>;
}

export interface PublicationHumanAction {
  readonly human_action_id?: string;
  readonly action_type?: string;
  readonly status?: string;
  readonly reason?: string;
  readonly error_code?: string;
  readonly impact?: string;
  readonly next_steps?: string;
}

export interface PublicationInboxItem {
  readonly entry_id: string;
  readonly kind: PublicationEntryKind;
  readonly publication_id: string | null;
  readonly opportunity_id: string;
  readonly content_generation_id: string | null;
  readonly brand: string | null;
  readonly channel: string | null;
  readonly destination_id: string | null;
  readonly status: string;
  readonly revision: number | null;
  readonly external_message_id: string | null;
  readonly published_price: string | null;
  readonly product: PublicationProduct;
  readonly last_validation: PublicationValidation | null;
  readonly updated_at: string;
}

export interface PublicationInbox {
  readonly schema_version: string;
  readonly status: string;
  readonly correlation_id: string;
  readonly count: number;
  readonly items: readonly PublicationInboxItem[];
}

export interface PublicationSummary {
  readonly publication_id: string;
  readonly opportunity_id: string;
  readonly content_generation_id: string;
  readonly affiliate_link_id: string;
  readonly brand: string;
  readonly channel: string;
  readonly destination_id: string;
  readonly status: string;
  readonly revision: number;
  readonly external_message_id: string | null;
  readonly published_price: string | null;
  readonly correlation_id: string;
  readonly created_at: string;
  readonly published_at: string | null;
}

export interface PublicationDetail {
  readonly kind: PublicationEntryKind;
  readonly opportunity_id: string;
  readonly publication: PublicationSummary | null;
  readonly product: PublicationProduct;
  readonly preview: PublicationPreview | null;
  readonly link: PublicationLink | null;
  readonly revision: number | null;
  readonly external_message_id: string | null;
  readonly last_validation: PublicationValidation | null;
  readonly timeline: readonly PublicationTimelineEntry[];
  readonly human_actions: readonly PublicationHumanAction[];
}

export interface PublicationDetailEnvelope {
  readonly schema_version: string;
  readonly status: string;
  readonly correlation_id: string;
  readonly entry_id: string;
  readonly detail: PublicationDetail;
}

export interface PublicationRevalidation {
  readonly publication_id: string;
  readonly allowed: boolean;
  readonly reason_code: string;
  readonly message: string;
  readonly content_generation_id: string;
  readonly checked_at: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, field: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error(`campo deve ser um objeto: ${field}`);
  }
  return value;
}

function requireString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`campo obrigatório inválido: ${key}`);
  }
  return value;
}

function requireSchemaVersion(record: Record<string, unknown>): string {
  const value = requireString(record, "schema_version");
  if (value !== PUBLICATIONS_SCHEMA_VERSION) {
    throw new Error(`schema_version não suportado: ${value}`);
  }
  return value;
}

function optionalString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function optionalNumber(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function optionalBoolean(record: Record<string, unknown>, key: string): boolean | null {
  const value = record[key];
  return typeof value === "boolean" ? value : null;
}

function requireArray(record: Record<string, unknown>, key: string): readonly unknown[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw new Error(`campo deve ser uma lista: ${key}`);
  }
  return value;
}

function parseProduct(input: unknown): PublicationProduct {
  if (input === null || input === undefined) {
    return {
      marketplace: null,
      external_id: null,
      title: null,
      url: null,
      brand: null,
      current_price: null,
    };
  }
  const record = requireRecord(input, "product");
  return {
    marketplace: optionalString(record, "marketplace"),
    external_id: optionalString(record, "external_id"),
    title: optionalString(record, "title"),
    url: optionalString(record, "url"),
    brand: optionalString(record, "brand"),
    current_price: optionalString(record, "current_price"),
  };
}

function parseValidation(input: unknown): PublicationValidation | null {
  if (input === null || input === undefined) {
    return null;
  }
  const record = requireRecord(input, "last_validation");
  return {
    validated_at: requireString(record, "validated_at"),
    allowed: optionalBoolean(record, "allowed"),
    reason_code: optionalString(record, "reason_code"),
    source: requireString(record, "source"),
  };
}

function parseInboxItem(input: unknown, index: number): PublicationInboxItem {
  const record = requireRecord(input, `items[${index}]`);
  const kind = requireString(record, "kind");
  if (kind !== "PUBLICATION" && kind !== "PREVIEW") {
    throw new Error(`kind inválido: ${kind}`);
  }
  return {
    entry_id: requireString(record, "entry_id"),
    kind,
    publication_id: optionalString(record, "publication_id"),
    opportunity_id: requireString(record, "opportunity_id"),
    content_generation_id: optionalString(record, "content_generation_id"),
    brand: optionalString(record, "brand"),
    channel: optionalString(record, "channel"),
    destination_id: optionalString(record, "destination_id"),
    status: requireString(record, "status"),
    revision: optionalNumber(record, "revision"),
    external_message_id: optionalString(record, "external_message_id"),
    published_price: optionalString(record, "published_price"),
    product: parseProduct(record["product"]),
    last_validation: parseValidation(record["last_validation"]),
    updated_at: requireString(record, "updated_at"),
  };
}

export function parsePublicationInbox(input: unknown): PublicationInbox {
  const record = requireRecord(input, "publication-inbox");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    correlation_id: requireString(record, "correlation_id"),
    count: optionalNumber(record, "count") ?? 0,
    items: requireArray(record, "items").map((entry, index) => parseInboxItem(entry, index)),
  };
}

function parseLink(input: unknown): PublicationLink | null {
  if (input === null || input === undefined) {
    return null;
  }
  const record = requireRecord(input, "link");
  return {
    affiliate_link_id: requireString(record, "affiliate_link_id"),
    affiliate_url: requireString(record, "affiliate_url"),
    productive: record["productive"] === true,
    generation_method: requireString(record, "generation_method"),
    status: requireString(record, "status"),
    tracking_context_id: requireString(record, "tracking_context_id"),
    tracking_internal_reference: requireString(record, "tracking_internal_reference"),
    tracking_label: requireString(record, "tracking_label"),
    tracking_mapping_version: requireString(record, "tracking_mapping_version"),
  };
}

function parsePreview(input: unknown): PublicationPreview | null {
  if (input === null || input === undefined) {
    return null;
  }
  const record = requireRecord(input, "preview");
  const tracking = record["tracking"];
  return {
    content_generation_id: requireString(record, "content_generation_id"),
    channel: requireString(record, "channel"),
    status: requireString(record, "status"),
    stale: record["stale"] === true,
    renderer_version: requireString(record, "renderer_version"),
    headline: requireString(record, "headline"),
    body: requireString(record, "body"),
    cta: requireString(record, "cta"),
    text: requireString(record, "text"),
    price: optionalString(record, "price"),
    affiliate_url: requireString(record, "affiliate_url"),
    disclosure: optionalString(record, "disclosure") ?? "",
    tracking: isRecord(tracking) ? tracking : {},
  };
}

function parseSummary(input: unknown): PublicationSummary | null {
  if (input === null || input === undefined) {
    return null;
  }
  const record = requireRecord(input, "publication");
  return {
    publication_id: requireString(record, "publication_id"),
    opportunity_id: requireString(record, "opportunity_id"),
    content_generation_id: requireString(record, "content_generation_id"),
    affiliate_link_id: requireString(record, "affiliate_link_id"),
    brand: requireString(record, "brand"),
    channel: requireString(record, "channel"),
    destination_id: requireString(record, "destination_id"),
    status: requireString(record, "status"),
    revision: optionalNumber(record, "revision") ?? 0,
    external_message_id: optionalString(record, "external_message_id"),
    published_price: optionalString(record, "published_price"),
    correlation_id: requireString(record, "correlation_id"),
    created_at: requireString(record, "created_at"),
    published_at: optionalString(record, "published_at"),
  };
}

function parseTimeline(input: readonly unknown[]): readonly PublicationTimelineEntry[] {
  return input.map((entry, index) => {
    const record = requireRecord(entry, `timeline[${index}]`);
    const payload = record["payload"];
    return {
      event_type: requireString(record, "event_type"),
      source: requireString(record, "source"),
      occurred_at: requireString(record, "occurred_at"),
      correlation_id: requireString(record, "correlation_id"),
      payload: isRecord(payload) ? payload : {},
    };
  });
}

function parseHumanActions(input: readonly unknown[]): readonly PublicationHumanAction[] {
  return input.map((entry) => {
    const record = requireRecord(entry, "human_action");
    return {
      human_action_id: optionalString(record, "human_action_id") ?? undefined,
      action_type: optionalString(record, "action_type") ?? undefined,
      status: optionalString(record, "status") ?? undefined,
      reason: optionalString(record, "reason") ?? undefined,
      error_code: optionalString(record, "error_code") ?? undefined,
      impact: optionalString(record, "impact") ?? undefined,
      next_steps: optionalString(record, "next_steps") ?? undefined,
    };
  });
}

export function parsePublicationDetail(
  input: unknown,
  fallbackEntryId: string,
): PublicationDetailEnvelope {
  const record = requireRecord(input, "publication-detail-envelope");
  const detail = requireRecord(record["detail"], "detail");
  const kind = requireString(detail, "kind");
  if (kind !== "PUBLICATION" && kind !== "PREVIEW") {
    throw new Error(`kind inválido: ${kind}`);
  }
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    correlation_id: requireString(record, "correlation_id"),
    entry_id: optionalString(record, "entry_id") ?? fallbackEntryId,
    detail: {
      kind,
      opportunity_id: requireString(detail, "opportunity_id"),
      publication: parseSummary(detail["publication"]),
      product: parseProduct(detail["product"]),
      preview: parsePreview(detail["preview"]),
      link: parseLink(detail["link"]),
      revision: optionalNumber(detail, "revision"),
      external_message_id: optionalString(detail, "external_message_id"),
      last_validation: parseValidation(detail["last_validation"]),
      timeline: parseTimeline(requireArray(detail, "timeline")),
      human_actions: parseHumanActions(requireArray(detail, "human_actions")),
    },
  };
}

export function parsePublicationRevalidation(input: unknown): PublicationRevalidation {
  const record = requireRecord(input, "publication-revalidation");
  const revalidation = requireRecord(record["revalidation"], "revalidation");
  return {
    publication_id: requireString(revalidation, "publication_id"),
    allowed: revalidation["allowed"] === true,
    reason_code: requireString(revalidation, "reason_code"),
    message: requireString(revalidation, "message"),
    content_generation_id: requireString(revalidation, "content_generation_id"),
    checked_at: requireString(revalidation, "checked_at"),
  };
}
