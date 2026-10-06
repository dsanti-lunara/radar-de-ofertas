/**
 * Fixtures sanitizadas de Configurações (RDR-067).
 *
 * Nenhum dado real ou credencial; espelham a forma versionada do payload do
 * `radar-api` (as políticas são os documentos aninhados reais).
 */

export const settingsFixture = {
  schema_version: "1.0",
  status: "OK",
  correlation_id: "cid-set",
  observed_at: "2026-10-06T12:00:00+00:00",
  operations: {
    schema_version: "1.0",
    global_mode: "RUNNING",
    stop_external_actions: false,
    blocks_new_external_actions: false,
    reason: null,
    updated_at: "2026-10-06T12:00:00+00:00",
  },
  automation_policy: {
    policy_version: "automation-policy-1.0",
    policy_hash: "aaaaaaaaaaaaaaaaaaaa",
    default_mode: "SHADOW",
  },
  compliance_policy: {
    policy_version: "compliance-policy-1.0",
    policy_hash: "bbbbbbbbbbbbbbbbbbbb",
    status: "ACTIVE",
  },
  publication_policy: {
    schema_version: "1.0",
    policy_version: "publication-policy-1.0",
    policy_hash: "cccccccccccccccccccc",
    timezone: "America/Maceio",
    default_limits: {
      hard_cap_per_day: 12,
      burst_limit: 2,
      burst_window_minutes: 15,
      cooldown_minutes: null,
    },
    channel_limits: {},
    quiet_windows: [],
  },
  integrations: [{ name: "telegram", state: "ONLINE", operational: true }],
  auto_eligibility: {
    eligible: false,
    promotes_automatically: false,
    requires_human_decision: true,
    criteria: [
      { criterion: "compliance_policy", state: "MET", detail: "Compliance vigente" },
      { criterion: "integration_health", state: "MET", detail: "Todas operacionais" },
      { criterion: "open_human_actions", state: "MET", detail: "Nenhuma intervenção aberta" },
      { criterion: "shadow_samples", state: "UNAVAILABLE", detail: "Amostragem não coletada" },
      { criterion: "human_agreement", state: "UNAVAILABLE", detail: "Concordância não coletada" },
      { criterion: "p0_p1_open", state: "UNAVAILABLE", detail: "P0/P1 indisponível" },
      {
        criterion: "validation_failures",
        state: "UNAVAILABLE",
        detail: "Falhas não agregadas",
      },
    ],
  },
};

export const modeChangeFixture = {
  schema_version: "1.0",
  status: "OK",
  correlation_id: "cid-mode",
  state: {
    schema_version: "1.0",
    global_mode: "PAUSED",
    stop_external_actions: false,
    blocks_new_external_actions: true,
    reason: "manutenção",
    updated_at: "2026-10-06T12:05:00+00:00",
  },
};

export const stopChangeFixture = {
  schema_version: "1.0",
  status: "STOPPED",
  correlation_id: "cid-stop",
  state: {
    schema_version: "1.0",
    global_mode: "RUNNING",
    stop_external_actions: true,
    blocks_new_external_actions: true,
    reason: "incidente",
    updated_at: "2026-10-06T12:06:00+00:00",
  },
};
