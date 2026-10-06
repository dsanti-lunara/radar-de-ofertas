/**
 * Workspace de publicações (RDR-061/062): compõe Inbox e detail com estados de
 * loading/erro/empty e injeta a aprovação explícita no preview.
 *
 * É um componente de apresentação: recebe os estados já carregados e a decisão de
 * desabilitar a aprovação, então cada transição (vazio, indisponível, carregado)
 * tem um feedback textual real sem simular dados.
 */

import { PublicationApprovalForm } from "./PublicationApprovalForm";
import { PublicationDetail } from "./PublicationDetail";
import { PublicationInbox } from "./PublicationInbox";
import type { InboxState, DetailState } from "./state";
import type { PublicationAction, PublicationInboxItem } from "./contracts";

interface PublicationWorkspaceProps {
  readonly inbox: InboxState;
  readonly detail: DetailState;
  readonly selectedId: string | null;
  readonly onSelect: (item: PublicationInboxItem) => void;
  readonly onApprove: (destinationId: string) => void;
  readonly onAction: (action: PublicationAction, reason: string) => void;
  readonly submitting: boolean;
  readonly approvalDisabled: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
}

export function PublicationWorkspace({
  inbox,
  detail,
  selectedId,
  onSelect,
  onApprove,
  onAction,
  submitting,
  approvalDisabled,
  feedback,
  error,
}: PublicationWorkspaceProps) {
  return (
    <div className="publication-workspace">
      {inbox.kind === "loading" ? (
        <p role="status">Carregando publicações…</p>
      ) : inbox.kind === "empty" ? (
        <p role="status">Nenhuma publicação ou preview no Inbox.</p>
      ) : inbox.kind === "unavailable" ? (
        <p className="alert" role="alert">
          {inbox.error.message}. {inbox.error.action}
        </p>
      ) : (
        <PublicationInbox inbox={inbox.inbox} selectedId={selectedId} onSelect={onSelect} />
      )}

      {selectedId === null ? (
        <p className="muted">Selecione uma publicação no Inbox para consultar.</p>
      ) : detail.kind === "loading" ? (
        <p role="status">Carregando detalhe…</p>
      ) : detail.kind === "unavailable" ? (
        <p className="alert" role="alert">
          {detail.error.message}. {detail.error.action}
        </p>
      ) : (
        <PublicationDetail
          detail={detail.detail}
          onAction={onAction}
          busy={submitting}
          feedback={feedback}
          error={error}
          approvalForm={
            detail.detail.detail.kind === "PREVIEW" ? (
              <PublicationApprovalForm
                onApprove={onApprove}
                busy={submitting}
                disabled={approvalDisabled}
                feedback={feedback}
                error={error}
              />
            ) : undefined
          }
        />
      )}
    </div>
  );
}
