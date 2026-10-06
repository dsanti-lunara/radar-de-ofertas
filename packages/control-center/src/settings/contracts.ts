/**
 * Contratos de Configurações e elegibilidade AUTO (RDR-067).
 *
 * Espelha o read model `GET /settings` e os controles operacionais
 * (`POST /operations/mode`, `POST`/`DELETE /operations/stop-external-actions`).
 * As políticas são versionadas/hasheadas; a elegibilidade AUTO é read-only e
 * nunca promove uma capability (AUT-257, AUT-258).
 */

export const SETTINGS_SCHEMA_VERSION = "1.0";

export interface OperationalState {
  readonly schema_version: string;
  readonly global_mode: string;
  readonly stop_external_actions: boolean;
  readonly blocks_new_external_actions: boolean;
  readonly reason: string | null;
  readonly updated_at: string | null;
}

export interface AutoEligibilityCriterion {
  readonly criterion: string;
  readonly state: string;
  readonly detail: string;
}

export interface AutoEligibility {
  readonly eligible: boolean;
  readonly promotes_automatically: boolean;
  readonly requires_human_decision: boolean;
  readonly criteria: readonly AutoEligibilityCriterion[];
}

export interface AutomationPolicySummary {
  readonly policy_version: string;
  readonly policy_hash: string;
  readonly default_mode: string;
}

export interface CompliancePolicySummary {
  readonly policy_version: string;
  readonly policy_hash: string;
  readonly status: string;
}

export interface PublicationPolicySummary {
  readonly policy_version: string;
  readonly policy_hash: string;
  readonly timezone: string;
  readonly hard_cap_per_day: number;
  readonly burst_limit: number;
  readonly quiet_windows: number;
}

export interface SettingsIntegration {
  readonly name: string;
  readonly state: string;
  readonly operational: boolean;
}

export interface SettingsSnapshot {
  readonly schema_version: string;
  readonly status: string;
  readonly correlation_id: string;
  readonly observed_at: string;
  readonly operations: OperationalState;
  readonly automation_policy: AutomationPolicySummary;
  readonly compliance_policy: CompliancePolicySummary;
  readonly publication_policy: PublicationPolicySummary;
  readonly integrations: readonly SettingsIntegration[];
  readonly auto_eligibility: AutoEligibility;
}

export interface ModeChangeResult {
  readonly schema_version: string;
  readonly status: string;
  readonly correlation_id: string;
  readonly state: OperationalState;
}

export interface StopChangeResult {
  readonly schema_version: string;
  readonly status: string;
  readonly correlation_id: string;
  readonly state: OperationalState;
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
  if (value !== SETTINGS_SCHEMA_VERSION) {
    throw new Error(`schema_version não suportado: ${value}`);
  }
  return value;
}

export function parseOperationalState(input: unknown): OperationalState {
  const record = requireRecord(input, "operations");
  return {
    schema_version: requireString(record, "schema_version"),
    global_mode: requireString(record, "global_mode"),
    stop_external_actions: requireBoolean(record, "stop_external_actions"),
    blocks_new_external_actions: requireBoolean(record, "blocks_new_external_actions"),
    reason: optionalString(record, "reason"),
    updated_at: optionalString(record, "updated_at"),
  };
}

function parseAutoEligibility(input: unknown): AutoEligibility {
  const record = requireRecord(input, "auto_eligibility");
  return {
    eligible: requireBoolean(record, "eligible"),
    promotes_automatically: requireBoolean(record, "promotes_automatically"),
    requires_human_decision: requireBoolean(record, "requires_human_decision"),
    criteria: requireArray(record, "criteria").map((entry, index) => {
      const criterion = requireRecord(entry, `criteria[${index}]`);
      return {
        criterion: requireString(criterion, "criterion"),
        state: requireString(criterion, "state"),
        detail: requireString(criterion, "detail"),
      };
    }),
  };
}

function parseAutomationPolicy(input: unknown): AutomationPolicySummary {
  const record = requireRecord(input, "automation_policy");
  return {
    policy_version: requireString(record, "policy_version"),
    policy_hash: requireString(record, "policy_hash"),
    default_mode: requireString(record, "default_mode"),
  };
}

function parseCompliancePolicy(input: unknown): CompliancePolicySummary {
  const record = requireRecord(input, "compliance_policy");
  return {
    policy_version: requireString(record, "policy_version"),
    policy_hash: requireString(record, "policy_hash"),
    status: requireString(record, "status"),
  };
}

function parsePublicationPolicy(input: unknown): PublicationPolicySummary {
  const record = requireRecord(input, "publication_policy");
  const limits = requireRecord(record["default_limits"], "default_limits");
  return {
    policy_version: requireString(record, "policy_version"),
    policy_hash: requireString(record, "policy_hash"),
    timezone: requireString(record, "timezone"),
    hard_cap_per_day: requireNumber(limits, "hard_cap_per_day"),
    burst_limit: requireNumber(limits, "burst_limit"),
    quiet_windows: requireArray(record, "quiet_windows").length,
  };
}

function parseSettingsIntegration(input: unknown): SettingsIntegration {
  const record = requireRecord(input, "integration");
  return {
    name: requireString(record, "name"),
    state: requireString(record, "state"),
    operational: requireBoolean(record, "operational"),
  };
}

export function parseSettings(input: unknown): SettingsSnapshot {
  const record = requireRecord(input, "settings");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    correlation_id: requireString(record, "correlation_id"),
    observed_at: requireString(record, "observed_at"),
    operations: parseOperationalState(record["operations"]),
    automation_policy: parseAutomationPolicy(record["automation_policy"]),
    compliance_policy: parseCompliancePolicy(record["compliance_policy"]),
    publication_policy: parsePublicationPolicy(record["publication_policy"]),
    integrations: requireArray(record, "integrations").map((entry) =>
      parseSettingsIntegration(entry),
    ),
    auto_eligibility: parseAutoEligibility(record["auto_eligibility"]),
  };
}

export function parseModeChangeResult(input: unknown): ModeChangeResult {
  const record = requireRecord(input, "mode-change");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    correlation_id: requireString(record, "correlation_id"),
    state: parseOperationalState(record["state"]),
  };
}

export function parseStopChangeResult(input: unknown): StopChangeResult {
  const record = requireRecord(input, "stop-change");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    correlation_id: requireString(record, "correlation_id"),
    state: parseOperationalState(record["state"]),
  };
}
