/**
 * Workspace de review (RDR-058..RDR-060): compõe Inbox e detail com estados de
 * loading/erro/empty e injeta o formulário de Human Review.
 *
 * É um componente de apresentação: recebe os estados já carregados, então cada
 * transição (vazio, indisponível, carregado) tem um feedback textual real sem
 * simular dados.
 */

import { HumanReviewForm as ReviewForm, type ReviewSubmission } from "./HumanReviewForm";
import { OpportunityDetail } from "./OpportunityDetail";
import { OpportunityInbox } from "./OpportunityInbox";
import type { DetailState, InboxState } from "./state";

interface ReviewWorkspaceProps {
  readonly inbox: InboxState;
  readonly detail: DetailState;
  readonly selectedId: string | null;
  readonly onSelect: (candidateId: string) => void;
  readonly onSubmitReview: (input: ReviewSubmission) => void;
  readonly submitting: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
}

export function ReviewWorkspace({
  inbox,
  detail,
  selectedId,
  onSelect,
  onSubmitReview,
  submitting,
  feedback,
  error,
}: ReviewWorkspaceProps) {
  return (
    <div className="review-workspace">
      {inbox.kind === "loading" ? (
        <p role="status">Carregando Inbox…</p>
      ) : inbox.kind === "empty" ? (
        <p role="status">Nenhum Candidate no Inbox.</p>
      ) : inbox.kind === "unavailable" ? (
        <p className="alert" role="alert">
          {inbox.error.message}. {inbox.error.action}
        </p>
      ) : (
        <OpportunityInbox inbox={inbox.inbox} selectedId={selectedId} onSelect={onSelect} />
      )}

      {selectedId === null ? (
        <p className="muted">Selecione um Candidate no Inbox para revisar.</p>
      ) : detail.kind === "loading" ? (
        <p role="status">Carregando detalhe…</p>
      ) : detail.kind === "unavailable" ? (
        <p className="alert" role="alert">
          {detail.error.message}. {detail.error.action}
        </p>
      ) : (
        <OpportunityDetail
          detail={detail.detail}
          reviewForm={
            <ReviewForm
              onSubmit={onSubmitReview}
              busy={submitting}
              feedback={feedback}
              error={error}
            />
          }
        />
      )}
    </div>
  );
}
