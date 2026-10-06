/**
 * Controle audado de integração (RDR-064, RDR-067).
 *
 * Habilitar/desabilitar uma integração é uma mudança perigosa: exige confirmação
 * explícita. A operação chama `PUT /integrations/{name}` e o `radar-api` grava o
 * audit event `INTEGRATION_HEALTH_CHANGED` (AUT-256, AUT-263).
 */

import { useState } from "react";

import type { Integration } from "./contracts";

export interface IntegrationControlProps {
  readonly integrations: readonly Integration[];
  readonly submitting: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
  readonly onSubmit: (name: string, state: string) => void;
}

export function IntegrationControl({
  integrations,
  submitting,
  feedback,
  error,
  onSubmit,
}: IntegrationControlProps) {
  const [name, setName] = useState(integrations[0]?.name ?? "");
  const [state, setState] = useState("ONLINE");
  const [confirmed, setConfirmed] = useState(false);
  const invalid = name === "" || !confirmed;

  return (
    <form
      className="review-form"
      aria-label="Alterar integração"
      onSubmit={(event) => {
        event.preventDefault();
        if (invalid || submitting) {
          return;
        }
        onSubmit(name, state);
      }}
    >
      <h3>Alterar integração</h3>
      <p className="muted">
        Mudança auditada. Desabilitar isola apenas a capability desta integração; nenhum
        envio é disparado por esta tela.
      </p>
      <label htmlFor="integration-name">Integração</label>
      <select
        id="integration-name"
        value={name}
        onChange={(event) => setName(event.target.value)}
      >
        {integrations.map((integration) => (
          <option key={integration.name} value={integration.name}>
            {integration.name} ({integration.state})
          </option>
        ))}
      </select>

      <label htmlFor="integration-state">Novo estado</label>
      <select
        id="integration-state"
        value={state}
        onChange={(event) => setState(event.target.value)}
      >
        <option value="ONLINE">ONLINE (habilitar)</option>
        <option value="DISABLED">DISABLED (desabilitar)</option>
        <option value="PAUSED">PAUSED (pausar)</option>
      </select>

      <label className="checkbox">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
        />
        Confirmo a alteração desta integração.
      </label>

      <button type="submit" disabled={invalid || submitting}>
        {submitting ? "Aplicando…" : "Aplicar estado"}
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
