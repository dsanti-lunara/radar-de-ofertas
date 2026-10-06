/**
 * Container polling do Sistema (RDR-064, RDR-065).
 *
 * Consulta `GET /integrations` e `GET /jobs` periodicamente; a alteração de
 * integração é uma mudança auditada com confirmação no formulário.
 */

import { useCallback, useEffect, useState } from "react";

import { SystemApiError, setIntegrationState } from "./api";
import { SystemWorkspace } from "./SystemWorkspace";
import {
  loadIntegrations,
  loadJobs,
  type IntegrationsState,
  type JobsState,
} from "./state";

const INTEGRATIONS_URL = "/integrations";
const JOBS_URL = "/jobs";
const POLL_INTERVAL_MS = 10_000;

export function SystemScreen() {
  const [integrations, setIntegrations] = useState<IntegrationsState>({ kind: "loading" });
  const [jobs, setJobs] = useState<JobsState>({ kind: "loading" });
  const [deadOnly, setDeadOnly] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [nextIntegrations, nextJobs] = await Promise.all([
      loadIntegrations(INTEGRATIONS_URL),
      loadJobs(JOBS_URL),
    ]);
    setIntegrations(nextIntegrations);
    setJobs(nextJobs);
  }, []);

  useEffect(() => {
    void refresh();
    const handle = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => window.clearInterval(handle);
  }, [refresh]);

  const updateIntegration = useCallback(
    async (name: string, state: string) => {
      setSubmitting(true);
      setFeedback(null);
      setError(null);
      try {
        const result = await setIntegrationState(name, state, null);
        setFeedback(
          `Integração ${result.integration.name} agora está ${result.integration.state}.`,
        );
        await refresh();
      } catch (caught) {
        const apiError = caught instanceof SystemApiError ? caught : null;
        setError(
          apiError === null
            ? "Falha ao alterar a integração."
            : `${apiError.message}. ${apiError.action}`,
        );
      } finally {
        setSubmitting(false);
      }
    },
    [refresh],
  );

  return (
    <SystemWorkspace
      integrations={integrations}
      jobs={jobs}
      deadOnly={deadOnly}
      onToggleDeadOnly={setDeadOnly}
      onUpdateIntegration={(name, state) => void updateIntegration(name, state)}
      submitting={submitting}
      feedback={feedback}
      error={error}
    />
  );
}
