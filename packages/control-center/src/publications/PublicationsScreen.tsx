/**
 * Container da tela Publicações (RDR-061/062).
 *
 * Consulta a API real por REST same-origin e injeta o estado no workspace
 * presentational; a aprovação explícita e as ações auditadas passam pelo contrato
 * público e recarregam o Inbox/detail. Nenhum envio é disparado na consulta.
 */

import { useCallback, useEffect, useState } from "react";

import { PublicationsApiError, submitPublicationAction, submitPublicationApproval } from "./api";
import { PublicationWorkspace } from "./PublicationWorkspace";
import { loadDetail, loadInbox, type DetailState, type InboxState } from "./state";
import type { PublicationAction, PublicationInboxItem } from "./contracts";

const INBOX_URL = "/publications";
const POLL_INTERVAL_MS = 10_000;

function actionFeedback(action: PublicationAction, result: { allowed: boolean; reason_code: string } | null): string {
  if (action === "revalidate" && result !== null) {
    return `Revalidação: ${result.allowed ? "permitida" : "bloqueada"} (${result.reason_code}).`;
  }
  return `Ação ${action} registrada.`;
}

export function PublicationsScreen() {
  const [inbox, setInbox] = useState<InboxState>({ kind: "loading" });
  const [detail, setDetail] = useState<DetailState>({ kind: "loading" });
  const [selected, setSelected] = useState<PublicationInboxItem | null>(null);
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

  const selectItem = useCallback(async (item: PublicationInboxItem) => {
    setSelected(item);
    setDetail({ kind: "loading" });
    setFeedback(null);
    setError(null);
    setDetail(await loadDetail(item));
  }, []);

  const approve = useCallback(
    async (destinationId: string) => {
      if (selected === null || detail.kind !== "ready") {
        return;
      }
      const preview = detail.detail.detail.preview;
      if (preview === null) {
        return;
      }
      setSubmitting(true);
      setFeedback(null);
      setError(null);
      try {
        const result = await submitPublicationApproval(selected.opportunity_id, {
          content_generation_id: preview.content_generation_id,
          destination_id: destinationId,
          idempotency_key: `${selected.opportunity_id}:${destinationId}`,
        });
        setFeedback(
          `Publicação aprovada (${result.status}); external ID ${result.external_message_id ?? "—"}.`,
        );
        await refreshInbox();
      } catch (caught) {
        const apiError = caught instanceof PublicationsApiError ? caught : null;
        setError(
          apiError === null
            ? "Falha ao aprovar a publicação."
            : `${apiError.message}. ${apiError.action}`,
        );
      } finally {
        setSubmitting(false);
      }
    },
    [selected, detail, refreshInbox],
  );

  const act = useCallback(
    async (action: PublicationAction, reason: string) => {
      if (selected === null || selected.publication_id === null) {
        return;
      }
      setSubmitting(true);
      setFeedback(null);
      setError(null);
      try {
        const result = await submitPublicationAction(selected.publication_id, action, reason);
        setFeedback(actionFeedback(action, result));
        await refreshInbox();
        setDetail(await loadDetail(selected));
      } catch (caught) {
        const apiError = caught instanceof PublicationsApiError ? caught : null;
        setError(
          apiError === null
            ? "Falha ao executar a ação."
            : `${apiError.message}. ${apiError.action}`,
        );
      } finally {
        setSubmitting(false);
      }
    },
    [selected, refreshInbox],
  );

  return (
    <PublicationWorkspace
      inbox={inbox}
      detail={detail}
      selectedId={selected?.entry_id ?? null}
      onSelect={(item) => void selectItem(item)}
      onApprove={(destinationId) => void approve(destinationId)}
      onAction={(action, reason) => void act(action, reason)}
      submitting={submitting}
      approvalDisabled={false}
      feedback={feedback}
      error={error}
    />
  );
}
