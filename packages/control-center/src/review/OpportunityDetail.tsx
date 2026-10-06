/**
 * Opportunity detail (RDR-059): breakdown, warnings, price history, Evidence,
 * AI review, versões, timeline e o portão operacional vigente.
 *
 * O painel de automação mostra que a aprovação do Candidate não libera envio em
 * SHADOW/ASSISTED (GRILL-001); o formulário de review é injetado pelo workspace.
 */

import type { ReactNode } from "react";

import type { DetailEnvelope } from "./contracts";

interface OpportunityDetailProps {
  readonly detail: DetailEnvelope;
  readonly reviewForm?: ReactNode;
}

export function OpportunityDetail({ detail, reviewForm }: OpportunityDetailProps) {
  const { candidate, evaluation, versions, automation } = detail.detail;

  return (
    <section aria-label="Opportunity detail" className="detail">
      <h2>{candidate.title ?? candidate.external_id}</h2>
      <p className="muted">
        {candidate.marketplace} · {candidate.external_id} · {candidate.state}
        {candidate.seller_name === null ? "" : ` · ${candidate.seller_name}`}
      </p>
      <p>
        Preço atual: <strong>{candidate.current_price ?? "—"}</strong>
      </p>

      {automation === null ? null : (
        <section aria-label="Portão operacional">
          <h3>Portão operacional</h3>
          <p data-mode={automation.automation_mode}>
            Modo <strong>{automation.automation_mode}</strong> · envio comercial{" "}
            <strong>{automation.publish_allowed ? "liberado" : "bloqueado"}</strong> (
            {automation.publish_reason_code})
          </p>
          <p className="muted">{automation.publish_message}</p>
        </section>
      )}

      <section aria-label="Score breakdown">
        <h3>Avaliação</h3>
        {evaluation === null ? (
          <p className="muted">Sem Evaluation persistida para este Candidate.</p>
        ) : (
          <>
            <ul>
              <li>Decisão: {evaluation.decision ?? "—"}</li>
              <li>Deal: {evaluation.deal_score ?? "—"}</li>
              <li>Monetization: {evaluation.monetization_score ?? "—"}</li>
              <li>Confidence: {evaluation.confidence ?? "—"}</li>
            </ul>
            {evaluation.failed_rules.length > 0 ? (
              <p className="alert">Hard rules: {evaluation.failed_rules.join(", ")}</p>
            ) : null}
            {evaluation.warnings.length > 0 ? (
              <p className="muted">Warnings: {evaluation.warnings.join(", ")}</p>
            ) : null}
          </>
        )}
      </section>

      <section aria-label="Price history">
        <h3>Histórico de preço</h3>
        {detail.detail.price_history.length === 0 ? (
          <p className="muted">Sem observações de preço.</p>
        ) : (
          <ul>
            {detail.detail.price_history.map((point) => (
              <li key={`${point.observed_at}-${point.price}`}>
                {point.observed_at} · {point.price} ({point.source})
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Evidence">
        <h3>Evidence</h3>
        {detail.detail.evidence.length === 0 ? (
          <p className="muted">Sem Evidence registrada.</p>
        ) : (
          <ul>
            {detail.detail.evidence.map((item, index) => (
              <li key={`${item.field_name}-${index}`}>
                {item.field_name}: {item.value} ({item.source_type})
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="AI review">
        <h3>AI review</h3>
        {detail.detail.ai_reviews.length === 0 ? (
          <p className="muted">Sem AI review.</p>
        ) : (
          <ul>
            {detail.detail.ai_reviews.map((review) => (
              <li key={review.ai_review_id}>
                Decisão IA: {review.decision} · knowledge {review.knowledge_version} · prompt{" "}
                {review.prompt_version}
                {review.editorial_angle === null ? "" : ` · ${review.editorial_angle}`}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Human reviews">
        <h3>Reviews humanas</h3>
        {detail.detail.human_reviews.length === 0 ? (
          <p className="muted">Nenhuma review humana registrada.</p>
        ) : (
          <ul>
            {detail.detail.human_reviews.map((review) => (
              <li key={review.human_review_id}>
                {review.reviewed_at}: {review.human_decision} (IA: {review.ai_decision ?? "—"}) ·{" "}
                {review.reason}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Timeline">
        <h3>Timeline</h3>
        {detail.detail.timeline.length === 0 ? (
          <p className="muted">Sem eventos.</p>
        ) : (
          <ol>
            {detail.detail.timeline.map((entry, index) => (
              <li key={`${entry.event_type}-${entry.recorded_at}-${index}`}>
                {entry.recorded_at} · {entry.event_type} ({entry.source})
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-label="Versions">
        <h3>Versões</h3>
        <ul>
          {Object.entries(versions).map(([name, value]) => (
            <li key={name}>
              {name}: {value ?? "—"}
            </li>
          ))}
        </ul>
      </section>

      {reviewForm}
    </section>
  );
}
