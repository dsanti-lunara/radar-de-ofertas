/**
 * Contrato do Home health overview consumido pelo Control Center (RDR-057).
 *
 * Espelha o payload versionado de `GET /health/overview`. A geração automática a
 * partir do OpenAPI substitui este espelho no ticket de contratos compartilhados
 * (AUT-395).
 */

export const HOME_HEALTH_SCHEMA_VERSION = "1.0";

export type HealthState = "HEALTHY" | "DEGRADED" | "UNHEALTHY" | "UNKNOWN";

export interface HealthError {
  readonly code: string;
  readonly message: string;
  readonly retryable: boolean;
  readonly action?: string;
  readonly context?: Readonly<Record<string, unknown>>;
}

export interface CapabilityHealth {
  readonly capability: string;
  readonly state: HealthState;
  readonly summary: string;
  readonly source: string;
  readonly reason_code?: string;
  readonly integration?: string;
  readonly integration_state?: string;
  readonly error?: HealthError;
}

export interface HomeHealth {
  readonly schema_version: string;
  readonly status: HealthState;
  readonly engine_version: string;
  readonly app_version: string;
  readonly correlation_id: string;
  readonly observed_at: string;
  readonly items: readonly CapabilityHealth[];
}

/** Capabilities canônicas do health strip (`docs/11_OPERATIONS_AND_UI.md`). */
export const HOME_HEALTH_CAPABILITIES: readonly string[] = [
  "core",
  "database",
  "scheduler",
  "ai",
  "browser",
  "mercado_livre",
  "shopee",
  "whatsapp",
  "telegram",
  "backup",
];

const HEALTH_STATES: readonly HealthState[] = ["HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"];

export function isHealthState(value: unknown): value is HealthState {
  return typeof value === "string" && (HEALTH_STATES as readonly string[]).includes(value);
}

export function isOperational(overview: HomeHealth): boolean {
  return overview.status === "HEALTHY" || overview.status === "DEGRADED";
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

function optionalString(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key];
  if (value === undefined || value === null) {
    return undefined;
  }
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`campo opcional inválido: ${key}`);
  }
  return value;
}

function parseHealthError(input: unknown, index: number): HealthError {
  if (!isRecord(input)) {
    throw new Error(`erro inválido no item ${index}`);
  }
  const code = requireString(input, "code");
  const message = requireString(input, "message");
  const retryable = input.retryable === true;
  const action = typeof input.action === "string" ? input.action : undefined;
  const base: HealthError = { code, message, retryable };
  return action === undefined ? base : { ...base, action };
}

function parseCapabilityHealth(input: unknown, index: number): CapabilityHealth {
  if (!isRecord(input)) {
    throw new Error(`item ${index} deve ser um objeto`);
  }
  const base: CapabilityHealth = {
    capability: requireString(input, "capability"),
    state: requireHealthState(input, "state"),
    summary: requireString(input, "summary"),
    source: requireString(input, "source"),
  };
  const reasonCode = optionalString(input, "reason_code");
  const integration = optionalString(input, "integration");
  const integrationState = optionalString(input, "integration_state");
  const error = input.error === undefined ? undefined : parseHealthError(input.error, index);
  return {
    ...base,
    ...(reasonCode === undefined ? {} : { reason_code: reasonCode }),
    ...(integration === undefined ? {} : { integration }),
    ...(integrationState === undefined ? {} : { integration_state: integrationState }),
    ...(error === undefined ? {} : { error }),
  };
}

function requireItems(record: Record<string, unknown>): readonly CapabilityHealth[] {
  const value = record["items"];
  if (!Array.isArray(value)) {
    throw new Error("campo obrigatório deve ser uma lista: items");
  }
  return value.map((entry, index) => parseCapabilityHealth(entry, index));
}

export function parseHomeHealth(input: unknown): HomeHealth {
  if (!isRecord(input)) {
    throw new Error("overview de saúde deve ser um objeto JSON");
  }
  const schemaVersion = requireString(input, "schema_version");
  if (schemaVersion !== HOME_HEALTH_SCHEMA_VERSION) {
    throw new Error(`schema_version não suportado: ${schemaVersion}`);
  }
  return {
    schema_version: schemaVersion,
    status: requireHealthState(input, "status"),
    engine_version: requireString(input, "engine_version"),
    app_version: requireString(input, "app_version"),
    correlation_id: requireString(input, "correlation_id"),
    observed_at: requireString(input, "observed_at"),
    items: requireItems(input),
  };
}
