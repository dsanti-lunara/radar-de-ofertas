/**
 * Formulário de aprovação explícita de publicação (RDR-061/GRILL-001).
 *
 * A aprovação é separada da review de Candidate: o operador precisa confirmar
 * explicitamente, informar o destino e o envio continua sujeito ao portão
 * operacional e à revalidação. Nenhum link/preço é digitado aqui.
 */

import { useState, type FormEvent } from "react";

interface PublicationApprovalFormProps {
  readonly onApprove: (destinationId: string) => void;
  readonly busy: boolean;
  readonly disabled: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
}

export function PublicationApprovalForm({
  onApprove,
  busy,
  disabled,
  feedback,
  error,
}: PublicationApprovalFormProps) {
  const [destinationId, setDestinationId] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const invalid = destinationId.trim() === "" || !confirmed;

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (invalid || busy || disabled) {
      return;
    }
    onApprove(destinationId.trim());
  }

  return (
    <form className="publication-approval" onSubmit={handleSubmit} aria-label="Aprovar publicação">
      <h3>Aprovar publicação</h3>
      <p className="muted">
        Aprovar um Candidate não autoriza envio; esta aprovação é explícita e o envio ainda depende
        do portão operacional e da revalidação vigentes.
      </p>
      <label>
        Destino
        <input
          value={destinationId}
          onChange={(event) => setDestinationId(event.target.value)}
          maxLength={128}
          required
        />
      </label>
      <label>
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Confirmo a aprovação explícita desta publicação
      </label>
      <button type="submit" disabled={invalid || busy || disabled}>
        {busy ? "Aprovando…" : "Aprovar e publicar"}
      </button>
      {disabled ? (
        <p className="muted">A publicação já foi enviada ou está suspensa; consulte a timeline.</p>
      ) : null}
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
