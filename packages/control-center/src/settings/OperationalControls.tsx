/**
 * Controles operacionais: modo global e kill switch (RDR-066, AUT-256).
 *
 * Toda mudança é perigosa e exige confirmação explícita; o `radar-api` grava o
 * audit event correspondente (`OPERATIONS_MODE_CHANGED`,
 * `EXTERNAL_ACTIONS_STOPPED`/`RESUMED`).
 */

import { useState } from "react";

import type { OperationalState } from "./contracts";

const MODES = ["RUNNING", "PAUSED", "DRAINING", "MAINTENANCE"] as const;

export interface OperationalControlsProps {
  readonly state: OperationalState;
  readonly submitting: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
  readonly onSetMode: (mode: string, reason: string) => void;
  readonly onSetStop: (engaged: boolean, reason: string) => void;
}

export function OperationalControls({
  state,
  submitting,
  feedback,
  error,
  onSetMode,
  onSetStop,
}: OperationalControlsProps) {
  const [mode, setMode] = useState(state.global_mode);
  const [modeReason, setModeReason] = useState("");
  const [modeConfirmed, setModeConfirmed] = useState(false);
  const [stopReason, setStopReason] = useState("");
  const [stopConfirmed, setStopConfirmed] = useState(false);

  const modeInvalid = mode === state.global_mode || !modeConfirmed;

  return (
    <section aria-label="Controles operacionais">
      <h3>Modo global</h3>
      <form
        className="review-form"
        aria-label="Alterar modo global"
        onSubmit={(event) => {
          event.preventDefault();
          if (modeInvalid || submitting) {
            return;
          }
          onSetMode(mode, modeReason);
        }}
      >
        <p className="muted">
          Estado atual: <strong>{state.global_mode}</strong>. Mudança auditada; novos side
          effects externos são bloqueados em PAUSED/DRAINING/MAINTENANCE.
        </p>
        <label htmlFor="global-mode">Novo modo</label>
        <select
          id="global-mode"
          value={mode}
          onChange={(event) => setMode(event.target.value)}
        >
          {MODES.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <label htmlFor="mode-reason">Motivo (opcional)</label>
        <input
          id="mode-reason"
          value={modeReason}
          maxLength={512}
          onChange={(event) => setModeReason(event.target.value)}
        />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={modeConfirmed}
            onChange={(event) => setModeConfirmed(event.target.checked)}
          />
          Confirmo a mudança de modo.
        </label>
        <button type="submit" disabled={modeInvalid || submitting}>
          {submitting ? "Aplicando…" : "Aplicar modo"}
        </button>
      </form>

      <h3>Kill switch (STOP_EXTERNAL_ACTIONS)</h3>
      <form
        className="review-form"
        aria-label="Alterar kill switch"
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <p className="muted">
          Estado atual:{" "}
          <strong>{state.stop_external_actions ? "ATIVO" : "liberado"}</strong>. Ler,
          diagnosticar e recuperar continuam disponíveis com o kill switch ativo.
        </p>
        <label htmlFor="stop-reason">Motivo (opcional)</label>
        <input
          id="stop-reason"
          value={stopReason}
          maxLength={512}
          onChange={(event) => setStopReason(event.target.value)}
        />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={stopConfirmed}
            onChange={(event) => setStopConfirmed(event.target.checked)}
          />
          Confirmo a alteração do kill switch.
        </label>
        <button
          type="button"
          disabled={!stopConfirmed || submitting}
          onClick={() => onSetStop(true, stopReason)}
        >
          Ativar kill switch
        </button>{" "}
        <button
          type="button"
          disabled={!stopConfirmed || submitting}
          onClick={() => onSetStop(false, stopReason)}
        >
          Liberar kill switch
        </button>
      </form>

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
    </section>
  );
}
