/**
 * Contrato de saúde consumido pelo TypeScript (RDR-010 / SPEC-01).
 *
 * Espelha o payload versionado emitido por `radarctl status` e `GET /health`.
 * A geração automática a partir do OpenAPI substitui este espelho no ticket de
 * contratos compartilhados (AUT-395).
 */

export const HEALTH_SCHEMA_VERSION = "1.0";

export type HealthState = "HEALTHY" | "DEGRADED" | "UNHEALTHY" | "UNKNOWN";

export interface HealthError {
  readonly code: string;
  readonly message: string;
  readonly retryable: boolean;
  readonly action?: string;
  readonly context?: Readonly<Record<string, unknown>>;
}

export interface HealthCheck {
  readonly name: string;
  readonly state: HealthState;
  readonly summary: string;
  readonly error?: HealthError;
}

export interface SystemHealth {
  readonly schema_version: string;
  readonly status: HealthState;
  readonly app_version: string;
  readonly correlation_id: string;
  readonly observed_at: string;
  readonly checks: readonly HealthCheck[];
}

const HEALTH_STATES: readonly HealthState[] = ["HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"];

export function isHealthState(value: unknown): value is HealthState {
  return typeof value === "string" && (HEALTH_STATES as readonly string[]).includes(value);
}

export function isOperational(report: SystemHealth): boolean {
  return report.status === "HEALTHY" || report.status === "DEGRADED";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`campo obrigatório inválido: ${key}`);
  }
  return value;
}

function requireHealthState(record: Record<string, unknown>, key: string): HealthState {
  const value = record[key];
  if (!isHealthState(value)) {
    throw new Error(`estado de saúde inválido em ${key}: ${String(value)}`);
  }
  return value;
}

function parseHealthError(input: unknown, index: number): HealthError {
  if (!isRecord(input)) {
    throw new Error(`erro inválido no check ${index}`);
  }
  const code = requireString(input, "code");
  const message = requireString(input, "message");
  const retryable = input.retryable === true;
  const action = typeof input.action === "string" ? input.action : undefined;
  const base: HealthError = { code, message, retryable };
  return action === undefined ? base : { ...base, action };
}

function parseHealthCheck(input: unknown, index: number): HealthCheck {
  if (!isRecord(input)) {
    throw new Error(`check ${index} deve ser um objeto`);
  }
  const name = requireString(input, "name");
  const state = requireHealthState(input, "state");
  const summary = requireString(input, "summary");
  const error = input.error === undefined ? undefined : parseHealthError(input.error, index);
  return error === undefined ? { name, state, summary } : { name, state, summary, error };
}

function requireChecks(record: Record<string, unknown>, key: string): readonly HealthCheck[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw new Error(`campo obrigatório deve ser uma lista: ${key}`);
  }
  return value.map((entry, index) => parseHealthCheck(entry, index));
}

export function parseSystemHealth(input: unknown): SystemHealth {
  if (!isRecord(input)) {
    throw new Error("relatório de saúde deve ser um objeto JSON");
  }
  const schemaVersion = requireString(input, "schema_version");
  if (schemaVersion !== HEALTH_SCHEMA_VERSION) {
    throw new Error(`schema_version não suportado: ${schemaVersion}`);
  }
  return {
    schema_version: schemaVersion,
    status: requireHealthState(input, "status"),
    app_version: requireString(input, "app_version"),
    correlation_id: requireString(input, "correlation_id"),
    observed_at: requireString(input, "observed_at"),
    checks: requireChecks(input, "checks"),
  };
}
