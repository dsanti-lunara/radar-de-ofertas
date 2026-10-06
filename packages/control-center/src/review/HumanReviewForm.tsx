/**
 * Human Review form (RDR-060): Approve/Reject/Edit content com motivo.
 *
 * A ação é enviada apenas com `human_decision` + `reason` (e o payload de
 * `EDIT_CONTENT`), nunca com um link/preço. O botão fica desabilitado enquanto
 * uma requisição está em andamento e o formulário valida localmente antes de
 * qualquer mutação, para não deixar estado parcial.
 */

import { useState, type FormEvent } from "react";

import type { HumanDecision } from "./contracts";

export interface ReviewSubmission {
  readonly human_decision: HumanDecision;
  readonly reason: string;
  readonly edited_content?: {
    readonly headline: string;
    readonly body: string;
    readonly cta: string;
  } | null;
}

interface HumanReviewFormProps {
  readonly onSubmit: (input: ReviewSubmission) => void;
  readonly busy: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
}

export function HumanReviewForm({ onSubmit, busy, feedback, error }: HumanReviewFormProps) {
  const [decision, setDecision] = useState<HumanDecision>("APPROVE");
  const [reason, setReason] = useState("");
  const [headline, setHeadline] = useState("");
  const [body, setBody] = useState("");
  const [cta, setCta] = useState("");

  const editIncomplete =
    decision === "EDIT_CONTENT" && (headline.trim() === "" || body.trim() === "" || cta.trim() === "");
  const invalid = reason.trim() === "" || editIncomplete;

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (invalid || busy) {
      return;
    }
    onSubmit({
      human_decision: decision,
      reason: reason.trim(),
      edited_content:
        decision === "EDIT_CONTENT"
          ? { headline: headline.trim(), body: body.trim(), cta: cta.trim() }
          : null,
    });
  }

  return (
    <form className="review-form" onSubmit={handleSubmit} aria-label="Human Review">
      <h3>Revisão humana</h3>
      <p className="muted">
        Aprovar um Candidate não autoriza publicação; o envio comercial continua sujeito às
        políticas operacionais.
      </p>

      <fieldset>
        <legend>Decisão</legend>
        <label>
          <input
            type="radio"
            name="decision"
            value="APPROVE"
            checked={decision === "APPROVE"}
            onChange={() => setDecision("APPROVE")}
          />
          Aprovar Candidate
        </label>
        <label>
          <input
            type="radio"
            name="decision"
            value="REJECT"
            checked={decision === "REJECT"}
            onChange={() => setDecision("REJECT")}
          />
          Rejeitar
        </label>
        <label>
          <input
            type="radio"
            name="decision"
            value="EDIT_CONTENT"
            checked={decision === "EDIT_CONTENT"}
            onChange={() => setDecision("EDIT_CONTENT")}
          />
          Editar conteúdo
        </label>
      </fieldset>

      <label>
        Motivo
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          maxLength={512}
          required
        />
      </label>

      {decision === "EDIT_CONTENT" ? (
        <fieldset>
          <legend>Conteúdo editado</legend>
          <label>
            Headline
            <input value={headline} onChange={(event) => setHeadline(event.target.value)} maxLength={512} />
          </label>
          <label>
            Body
            <textarea value={body} onChange={(event) => setBody(event.target.value)} maxLength={512} />
          </label>
          <label>
            CTA
            <input value={cta} onChange={(event) => setCta(event.target.value)} maxLength={512} />
          </label>
        </fieldset>
      ) : null}

      <button type="submit" disabled={invalid || busy}>
        {busy ? "Registrando…" : "Registrar review"}
      </button>

      {feedback === null ? null : (
        <p className="alert alert--ok" role="status">
          {feedback}
        </p>
      )}
      {error === null ? null : (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
