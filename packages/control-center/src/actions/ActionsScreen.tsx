/**
 * Container polling da central de HumanActions (RDR-063).
 *
 * Consulta `GET /human-actions` periodicamente, carrega o detail selecionado e
 * envia a resolução auditada. Estados assíncronos e erros são testáveis sem DOM
 * (`.../actions/state.ts` e `.../actions/api.ts`).
 */

import { useCallback, useEffect, useState } from "react";

import { ActionsWorkspace } from "./ActionsWorkspace";
import { HumanActionsApiError, resolveHumanAction } from "./api";
import { loadDetail, loadInbox, type DetailState, type InboxState } from "./state";

const INBOX_URL = "/human-actions";
const POLL_INTERVAL_MS = 10_000;

export function ActionsScreen() {
  const [inbox, setInbox] = useState<InboxState>({ kind: "loading" });
  const [detail, setDetail] = useState<DetailState>({ kind: "loading" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshInbox = useCallback(async () => {
    setInbox(await loadInbox(INBOX_URL));
  }, []);

  useEffect(() => {
    void refreshInbox();
    const handle = window.setInterval(() => void refreshInbox(), POLL_INTERVAL_MS);
    return () => window.clearInterval(handle);
  }, [refreshInbox]);

  const select = useCallback(async (humanActionId: string) => {
    setSelectedId(humanActionId);
    setDetail({ kind: "loading" });
    setFeedback(null);
    setError(null);
    setDetail(await loadDetail(humanActionId));
  }, []);

  const resolve = useCallback(
    async (reason: string) => {
      if (selectedId === null) {
        return;
      }
      setSubmitting(true);
      setFeedback(null);
      setError(null);
      try {
        const result = await resolveHumanAction(selectedId, reason);
        setFeedback(
          result.idempotent_replay
            ? "Ação já estava resolvida."
            : `Ação resolvida (${result.human_action.action_type}).`,
        );
        setDetail(await loadDetail(selectedId));
        void refreshInbox();
      } catch (caught) {
        const apiError = caught instanceof HumanActionsApiError ? caught : null;
        setError(
          apiError === null
            ? "Falha ao resolver a ação."
            : `${apiError.message}. ${apiError.action}`,
        );
      } finally {
        setSubmitting(false);
      }
    },
    [selectedId, refreshInbox],
  );

  return (
    <ActionsWorkspace
      inbox={inbox}
      detail={detail}
      selectedId={selectedId}
      onSelect={(humanActionId) => void select(humanActionId)}
      onResolve={(reason) => void resolve(reason)}
      submitting={submitting}
      feedback={feedback}
      error={error}
    />
  );
}
