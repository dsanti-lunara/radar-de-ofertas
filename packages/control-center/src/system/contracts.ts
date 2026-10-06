/**
 * Contratos do Sistema: integrações e Jobs/Dead Jobs (RDR-064, RDR-065).
 *
 * Espelha `GET /integrations`, `PUT /integrations/{name}` e `GET /jobs`.
 */

export const SYSTEM_SCHEMA_VERSION = "1.0";

export interface Integration {
  readonly name: string;
  readonly state: string;
  readonly operational: boolean;
  readonly summary: string;
  readonly updated_at: string | null;
}

export interface IntegrationsList {
  readonly schema_version: string;
  readonly status: string;
  readonly count: number;
  readonly correlation_id: string;
  readonly integrations: readonly Integration[];
}

export interface IntegrationUpdateResult {
  readonly schema_version: string;
  readonly status: string;
  readonly correlation_id: string;
  readonly integration: Integration;
}

export interface Job {
  readonly job_id: string;
  readonly type: string;
  readonly status: string;
  readonly entity_type: string | null;
  readonly entity_id: string | null;
  readonly priority: number;
  readonly attempts: number;
  readonly max_attempts: number;
  readonly available_at: string;
  readonly correlation_id: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface JobsInbox {
  readonly schema_version: string;
  readonly status: string;
  readonly count: number;
  readonly correlation_id: string;
  readonly jobs: readonly Job[];
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

function requireNumber(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`campo numérico inválido: ${key}`);
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
  if (value !== SYSTEM_SCHEMA_VERSION) {
    throw new Error(`schema_version não suportado: ${value}`);
  }
  return value;
}

export function parseIntegration(input: unknown): Integration {
  const record = requireRecord(input, "integration");
  return {
    name: requireString(record, "name"),
    state: requireString(record, "state"),
    operational: record["operational"] === true,
    summary: requireString(record, "summary"),
    updated_at: optionalString(record, "updated_at"),
  };
}

export function parseIntegrationsList(input: unknown): IntegrationsList {
  const record = requireRecord(input, "integrations-list");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    count: requireNumber(record, "count"),
    correlation_id: requireString(record, "correlation_id"),
    integrations: requireArray(record, "integrations").map((entry) => parseIntegration(entry)),
  };
}

export function parseIntegrationUpdateResult(input: unknown): IntegrationUpdateResult {
  const record = requireRecord(input, "integration-update");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    correlation_id: requireString(record, "correlation_id"),
    integration: parseIntegration(record["integration"]),
  };
}

export function parseJob(input: unknown): Job {
  const record = requireRecord(input, "job");
  return {
    job_id: requireString(record, "job_id"),
    type: requireString(record, "type"),
    status: requireString(record, "status"),
    entity_type: optionalString(record, "entity_type"),
    entity_id: optionalString(record, "entity_id"),
    priority: requireNumber(record, "priority"),
    attempts: requireNumber(record, "attempts"),
    max_attempts: requireNumber(record, "max_attempts"),
    available_at: requireString(record, "available_at"),
    correlation_id: requireString(record, "correlation_id"),
    created_at: requireString(record, "created_at"),
    updated_at: requireString(record, "updated_at"),
  };
}

export function parseJobsInbox(input: unknown): JobsInbox {
  const record = requireRecord(input, "jobs-inbox");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    count: requireNumber(record, "count"),
    correlation_id: requireString(record, "correlation_id"),
    jobs: requireArray(record, "jobs").map((entry) => parseJob(entry)),
  };
}
