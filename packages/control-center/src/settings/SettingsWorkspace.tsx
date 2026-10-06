/**
 * Workspace de Configurações (RDR-067).
 *
 * Mostra as políticas efetivas versionadas/hasheadas, os controles operacionais
 * e a elegibilidade AUTO. A elegibilidade é read-only: a UI mostra readiness e
 * nunca promove uma capability sozinha (AUT-257, AUT-258).
 */

import { OperationalControls } from "./OperationalControls";
import type { SettingsSnapshot } from "./contracts";
import type { SettingsState } from "./state";

export interface SettingsWorkspaceProps {
  readonly state: SettingsState;
  readonly submitting: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
  readonly onSetMode: (mode: string, reason: string) => void;
  readonly onSetStop: (engaged: boolean, reason: string) => void;
}

function Eligibility({ settings }: { readonly settings: SettingsSnapshot }) {
  const eligibility = settings.auto_eligibility;
  return (
    <section aria-label="Elegibilidade AUTO">
      <h3>Elegibilidade AUTO</h3>
      <p className="muted">
        Elegível: <strong>{eligibility.eligible ? "sim" : "não"}</strong>. Promoção automática:{" "}
        <strong>{eligibility.promotes_automatically ? "sim" : "nunca"}</strong>. Decisão humana
        obrigatória: <strong>{eligibility.requires_human_decision ? "sim" : "não"}</strong>.
      </p>
      <table className="inbox">
        <caption className="sr-only">Critérios de elegibilidade AUTO</caption>
        <thead>
          <tr>
            <th scope="col">Critério</th>
            <th scope="col">Estado</th>
            <th scope="col">Detalhe</th>
          </tr>
        </thead>
        <tbody>
          {eligibility.criteria.map((criterion) => (
            <tr key={criterion.criterion} data-state={criterion.state}>
              <th scope="row">{criterion.criterion}</th>
              <td>{criterion.state}</td>
              <td>{criterion.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Policies({ settings }: { readonly settings: SettingsSnapshot }) {
  return (
    <section aria-label="Políticas efetivas">
      <h3>Políticas efetivas</h3>
      <dl>
        <dt>Automation policy</dt>
        <dd>
          {settings.automation_policy.policy_version} · hash{" "}
          {settings.automation_policy.policy_hash.slice(0, 12)}… · default{" "}
          {settings.automation_policy.default_mode}
        </dd>
        <dt>Compliance policy</dt>
        <dd>
          {settings.compliance_policy.policy_version} · hash{" "}
          {settings.compliance_policy.policy_hash.slice(0, 12)}… · status{" "}
          {settings.compliance_policy.status}
        </dd>
        <dt>Publication policy</dt>
        <dd>
          {settings.publication_policy.policy_version} · cap{" "}
          {settings.publication_policy.hard_cap_per_day}/dia · burst{" "}
          {settings.publication_policy.burst_limit} · quiet windows{" "}
          {settings.publication_policy.quiet_windows}
        </dd>
        <dt>Integrações</dt>
        <dd>
          {settings.integrations.length === 0
            ? "nenhuma registrada"
            : settings.integrations
                .map((integration) => `${integration.name}:${integration.state}`)
                .join(", ")}
        </dd>
      </dl>
    </section>
  );
}

export function SettingsWorkspace({
  state,
  submitting,
  feedback,
  error,
  onSetMode,
  onSetStop,
}: SettingsWorkspaceProps) {
  if (state.kind === "loading") {
    return <p role="status">Carregando configurações…</p>;
  }
  if (state.kind === "unavailable") {
    return (
      <p className="alert" role="alert">
        {state.error.message}. {state.error.action}
      </p>
    );
  }
  const settings = state.settings;
  return (
    <section className="settings-workspace" aria-label="Configurações">
      <h2>Configurações</h2>
      <p className="muted">
        Observado em {settings.observed_at} · Correlation ID: {settings.correlation_id}
      </p>
      <Policies settings={settings} />
      <OperationalControls
        state={settings.operations}
        submitting={submitting}
        feedback={feedback}
        error={error}
        onSetMode={onSetMode}
        onSetStop={onSetStop}
      />
      <Eligibility settings={settings} />
    </section>
  );
}
