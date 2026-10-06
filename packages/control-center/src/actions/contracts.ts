/**
 * Contratos da central de HumanActions (RDR-063, TKT-28).
 *
 * Espelha os payloads versionados de `GET /human-actions`,
 * `GET /human-actions/{id}` e `POST /human-actions/{id}/resolve`. A geração
 * automática a partir do OpenAPI substitui este espelho no ticket de contratos
 * compartilhados (AUT-395).
 */

export const HUMAN_ACTIONS_SCHEMA_VERSION = "1.0";

export interface HumanActionResolution {
  readonly mode: string;
  readonly resolvable_via_center: boolean;
  readonly delegated_to: string | null;
  readonly guidance: string;
}

export interface HumanAction {
  readonly human_action_id: string;
  readonly action_type: string;
  readonly status: string;
  readonly entity_type: string;
  readonly entity_id: string;
  readonly reason: string;
  readonly error_code: string;
  readonly impact: string;
  readonly next_steps: string;
  readonly resolution: HumanActionResolution;
  readonly correlation_id: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface HumanActionList {
  readonly schema_version: string;
  readonly correlation_id: string;
  readonly human_actions: readonly HumanAction[];
}

export interface HumanActionResolveResult {
  readonly schema_version: string;
  readonly status: string;
  readonly idempotent_replay: boolean;
  readonly correlation_id: string;
  readonly human_action: HumanAction;
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

function optionalString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function requireBoolean(record: Record<string, unknown>, key: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") {
    throw new Error(`campo booleano inválido: ${key}`);
  }
  return value;
}

function requireArray(record: Record<string, unknown>, key: string): readonly unknown[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw new Error(`campo deve ser uma lista: ${key}`);
  }
  return value;
}

function requireSchemaVersion(record: Record<string, unknown>): string {
  const value = requireString(record, "schema_version");
  if (value !== HUMAN_ACTIONS_SCHEMA_VERSION) {
    throw new Error(`schema_version não suportado: ${value}`);
  }
  return value;
}

function parseResolution(input: unknown): HumanActionResolution {
  const record = requireRecord(input, "resolution");
  return {
    mode: requireString(record, "mode"),
    resolvable_via_center: requireBoolean(record, "resolvable_via_center"),
    delegated_to: optionalString(record, "delegated_to"),
    guidance: requireString(record, "guidance"),
  };
}

export function parseHumanAction(input: unknown): HumanAction {
  const record = requireRecord(input, "human_action");
  return {
    human_action_id: requireString(record, "human_action_id"),
    action_type: requireString(record, "action_type"),
    status: requireString(record, "status"),
    entity_type: requireString(record, "entity_type"),
    entity_id: requireString(record, "entity_id"),
    reason: requireString(record, "reason"),
    error_code: requireString(record, "error_code"),
    impact: requireString(record, "impact"),
    next_steps: requireString(record, "next_steps"),
    resolution: parseResolution(record["resolution"]),
    correlation_id: requireString(record, "correlation_id"),
    created_at: requireString(record, "created_at"),
    updated_at: requireString(record, "updated_at"),
  };
}

export function parseHumanActionList(input: unknown): HumanActionList {
  const record = requireRecord(input, "human-action-list");
  return {
    schema_version: requireSchemaVersion(record),
    correlation_id: requireString(record, "correlation_id"),
    human_actions: requireArray(record, "human_actions").map((entry) => parseHumanAction(entry)),
  };
}

export function parseHumanActionResolveResult(input: unknown): HumanActionResolveResult {
  const record = requireRecord(input, "human-action-resolve");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    idempotent_replay: requireBoolean(record, "idempotent_replay"),
    correlation_id: requireString(record, "correlation_id"),
    human_action: parseHumanAction(record["human_action"]),
  };
}
