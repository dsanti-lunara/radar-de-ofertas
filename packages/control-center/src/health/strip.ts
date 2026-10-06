/**
 * Apresentação do health strip (RDR-057).
 *
 * O status nunca depende só de cor: cada estado tem um rótulo textual e um tom
 * (`docs/11_OPERATIONS_AND_UI.md`, "status não dependem só de cor"). Estados
 * desconhecidos não viram "saudável" e capacidades sem dados aparecem como
 * `UNKNOWN` (sem inventar capacidade).
 */

import {
  HOME_HEALTH_CAPABILITIES,
  type CapabilityHealth,
  type HealthState,
} from "../contracts";

export type HealthTone = "ok" | "warn" | "down" | "unknown";

export interface StatePresentation {
  readonly label: string;
  readonly tone: HealthTone;
}

const PRESENTATION: Record<HealthState, StatePresentation> = {
  HEALTHY: { label: "Saudável", tone: "ok" },
  DEGRADED: { label: "Degradado", tone: "warn" },
  UNHEALTHY: { label: "Indisponível", tone: "down" },
  UNKNOWN: { label: "Desconhecido", tone: "unknown" },
};

const CAPABILITY_LABELS: Readonly<Record<string, string>> = {
  core: "Core",
  database: "Banco",
  scheduler: "Scheduler",
  ai: "IA / ChatGPT",
  browser: "Browser",
  mercado_livre: "Mercado Livre",
  shopee: "Shopee",
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  backup: "Backup",
};

export function describeHealthState(state: HealthState): StatePresentation {
  return PRESENTATION[state] ?? { label: state, tone: "unknown" };
}

export function capabilityLabel(capability: string): string {
  return CAPABILITY_LABELS[capability] ?? capability;
}

/**
 * Strip usada quando a API ainda não respondeu: todas as capacidades ficam
 * `UNKNOWN` (nunca "saudável") até existir evidência real.
 */
export function unknownStrip(): readonly CapabilityHealth[] {
  return HOME_HEALTH_CAPABILITIES.map((capability) => ({
    capability,
    state: "UNKNOWN" as HealthState,
    summary: "Sem dados de saúde ainda",
    source: "unavailable",
  }));
}
