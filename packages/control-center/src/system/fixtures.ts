/**
 * Fixtures sanitizadas do Sistema (RDR-064, RDR-065).
 *
 * Nenhum dado real, credencial ou telemetria inventada: os payloads seguem a
 * forma versionada do contrato e são usados nos testes.
 */

import type { IntegrationsList, JobsInbox } from "./contracts";

export const integrationsFixture: IntegrationsList = {
  schema_version: "1.0",
  status: "OK",
  count: 2,
  correlation_id: "cid-sys",
  integrations: [
    {
      name: "telegram",
      state: "ONLINE",
      operational: true,
      summary: "up",
      updated_at: "2026-10-06T12:00:00+00:00",
    },
    {
      name: "shopee",
      state: "AUTH_REQUIRED",
      operational: false,
      summary: "sessão expirada",
      updated_at: "2026-10-06T11:00:00+00:00",
    },
  ],
};

export const jobsFixture: JobsInbox = {
  schema_version: "1.0",
  status: "OK",
  count: 2,
  correlation_id: "cid-jobs",
  jobs: [
    {
      job_id: "job_pending",
      type: "NORMALIZE_CAPTURE",
      status: "PENDING",
      entity_type: "candidate",
      entity_id: "cand_1",
      priority: 0,
      attempts: 0,
      max_attempts: 3,
      available_at: "2026-10-06T12:00:00+00:00",
      correlation_id: "cid-1",
      created_at: "2026-10-06T12:00:00+00:00",
      updated_at: "2026-10-06T12:00:00+00:00",
    },
    {
      job_id: "job_dead",
      type: "PUBLISH_TELEGRAM",
      status: "DEAD",
      entity_type: "candidate",
      entity_id: "cand_2",
      priority: 0,
      attempts: 1,
      max_attempts: 1,
      available_at: "2026-10-06T12:05:00+00:00",
      correlation_id: "cid-2",
      created_at: "2026-10-06T12:05:00+00:00",
      updated_at: "2026-10-06T12:06:00+00:00",
    },
  ],
};
