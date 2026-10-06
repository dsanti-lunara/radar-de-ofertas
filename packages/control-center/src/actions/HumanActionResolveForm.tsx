/**
 * Formulário de resolução de uma HumanAction (RDR-063).
 *
 * Resolver é uma mudança auditável: exige motivo e uma confirmação explícita de
 * que a intervenção foi executada. Enquanto a requisição está em andamento o
 * botão fica desabilitado (otimista-zero) e a ação delegada nunca é oferecida
 * aqui (AUT-256, AUT-263).
 */

import { useState } from "react";

export interface HumanActionResolveFormProps {
  readonly humanActionId: string;
  readonly disabled: boolean;
  readonly submitting: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
  readonly onResolve: (reason: string) => void;
}

export function HumanActionResolveForm({
  humanActionId,
  disabled,
  submitting,
  feedback,
  error,
  onResolve,
}: HumanActionResolveFormProps) {
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const invalid = reason.trim() === "" || !confirmed;

  return (
    <form
      className="review-form"
      aria-label="Resolver HumanAction"
      onSubmit={(event) => {
        event.preventDefault();
        if (invalid || submitting || disabled) {
          return;
        }
        onResolve(reason.trim());
      }}
    >
      <h3>Resolver ação</h3>
      <p className="muted">
        Mudança auditada. Descreva como a intervenção foi executada; a resolução não
        executa nenhum envio por conta própria.
      </p>
      <label htmlFor={`reason-${humanActionId}`}>Motivo da resolução</label>
      <textarea
        id={`reason-${humanActionId}`}
        value={reason}
        maxLength={512}
        rows={3}
        onChange={(event) => setReason(event.target.value)}
      />
      <label className="checkbox">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Confirmo que a intervenção foi executada e que é seguro fechar esta ação.
      </label>
      <button type="submit" disabled={invalid || submitting || disabled}>
        {submitting ? "Resolvendo…" : "Resolver ação"}
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
