/**
 * Fixtures sanitizadas da central de HumanActions (RDR-063).
 *
 * Nenhum dado real, credencial ou conteúdo de marketplace: os payloads têm a
 * forma versionada do contrato e são usados nos testes de contrato/estado/UI.
 */

import type { HumanAction, HumanActionList, HumanActionResolveResult } from "./contracts";

export const humanActionFixture: HumanAction = {
  human_action_id: "ha_1",
  action_type: "DEAD_JOB_REVIEW",
  status: "OPEN",
  entity_type: "candidate",
  entity_id: "cand_1",
  reason: "RETRIES_EXHAUSTED",
  error_code: "RAD-WF-001",
  impact: "Um job entrou na Dead Job Queue e ficou parado até a revisão.",
  next_steps: "Corrigir a causa, reprocessar o job e registrar a resolução.",
  resolution: {
    mode: "OPERATOR_ACK",
    resolvable_via_center: true,
    delegated_to: null,
    guidance: "Corrigir a causa, reprocessar o job e registrar a resolução.",
  },
  correlation_id: "cid-ha",
  created_at: "2026-10-06T12:00:00+00:00",
  updated_at: "2026-10-06T12:00:00+00:00",
};

export const delegatedHumanActionFixture: HumanAction = {
  ...humanActionFixture,
  human_action_id: "ha_pub",
  action_type: "REVIEW_PUBLICATION",
  entity_type: "publication",
  entity_id: "pub_1",
  reason: "SEND_RESULT_UNKNOWN",
  error_code: "RAD-PUB-006",
  resolution: {
    mode: "PUBLICATION_RESOLUTION",
    resolvable_via_center: false,
    delegated_to: "publications",
    guidance: "Resolver pela resolução da publicação, que exige evidência.",
  },
};

export const humanActionListFixture: HumanActionList = {
  schema_version: "1.0",
  correlation_id: "cid-ha",
  human_actions: [humanActionFixture, delegatedHumanActionFixture],
};

export const humanActionResolveResultFixture: HumanActionResolveResult = {
  schema_version: "1.0",
  status: "RESOLVED",
  idempotent_replay: false,
  correlation_id: "cid-ha",
  human_action: { ...humanActionFixture, status: "RESOLVED" },
};
