/**
 * Workspace do Sistema: integrações e Jobs/Dead Jobs (RDR-064, RDR-065).
 *
 * Apresentacional: usa somente dados reais persistidos/consultáveis e mostra
 * texto de estado (nunca só cor). A visão de Dead Jobs usa o status real.
 */

import { IntegrationControl } from "./IntegrationControl";
import type { JobsState, IntegrationsState } from "./state";

export interface SystemWorkspaceProps {
  readonly integrations: IntegrationsState;
  readonly jobs: JobsState;
  readonly deadOnly: boolean;
  readonly onToggleDeadOnly: (deadOnly: boolean) => void;
  readonly onUpdateIntegration: (name: string, state: string) => void;
  readonly submitting: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
}

function IntegrationsSection({ state }: { readonly state: IntegrationsState }) {
  if (state.kind === "loading") {
    return <p role="status">Carregando integrações…</p>;
  }
  if (state.kind === "empty") {
    return <p role="status">Nenhuma integração registrada.</p>;
  }
  if (state.kind === "unavailable") {
    return (
      <p className="alert" role="alert">
        {state.error.message}. {state.error.action}
      </p>
    );
  }
  return (
    <>
      <p className="muted">Correlation ID: {state.list.correlation_id}</p>
      <table className="inbox">
        <caption className="sr-only">Integrações</caption>
        <thead>
          <tr>
            <th scope="col">Integração</th>
            <th scope="col">Estado</th>
            <th scope="col">Operacional</th>
            <th scope="col">Resumo</th>
          </tr>
        </thead>
        <tbody>
          {state.list.integrations.map((integration) => (
            <tr key={integration.name} data-state={integration.state}>
              <th scope="row">{integration.name}</th>
              <td>{integration.state}</td>
              <td>{integration.operational ? "Sim" : "Não"}</td>
              <td>{integration.summary}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function JobsSection({
  state,
  deadOnly,
}: {
  readonly state: JobsState;
  readonly deadOnly: boolean;
}) {
  if (state.kind === "loading") {
    return <p role="status">Carregando jobs…</p>;
  }
  if (state.kind === "empty") {
    return <p role="status">Nenhum job registrado.</p>;
  }
  if (state.kind === "unavailable") {
    return (
      <p className="alert" role="alert">
        {state.error.message}. {state.error.action}
      </p>
    );
  }
  const jobs = state.inbox.jobs.filter((job) => !deadOnly || job.status === "DEAD");
  return (
    <>
      <p className="muted">
        Correlation ID: {state.inbox.correlation_id} · {jobs.length} de {state.inbox.count} job(s)
      </p>
      {jobs.length === 0 ? (
        <p role="status">Nenhum dead job.</p>
      ) : (
        <table className="inbox">
          <caption className="sr-only">Jobs</caption>
          <thead>
            <tr>
              <th scope="col">Job</th>
              <th scope="col">Tipo</th>
              <th scope="col">Status</th>
              <th scope="col">Tentativas</th>
              <th scope="col">Disponível em</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.job_id} data-state={job.status}>
                <th scope="row">{job.job_id}</th>
                <td>{job.type}</td>
                <td>{job.status}</td>
                <td>
                  {job.attempts}/{job.max_attempts}
                </td>
                <td>{job.available_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

export function SystemWorkspace({
  integrations,
  jobs,
  deadOnly,
  onToggleDeadOnly,
  onUpdateIntegration,
  submitting,
  feedback,
  error,
}: SystemWorkspaceProps) {
  const canControl = integrations.kind === "ready";
  return (
    <section className="system-workspace" aria-label="Sistema">
      <section aria-label="Integrações">
        <h2>Integrações</h2>
        <IntegrationsSection state={integrations} />
      </section>

      <section aria-label="Controle de integração">
        {canControl ? (
          <IntegrationControl
            integrations={integrations.list.integrations}
            submitting={submitting}
            feedback={feedback}
            error={error}
            onSubmit={onUpdateIntegration}
          />
        ) : (
          <p className="muted">Controle de integração indisponível até carregar a lista.</p>
        )}
      </section>

      <section aria-label="Jobs e Dead Jobs">
        <h2>Jobs</h2>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={deadOnly}
            onChange={(event) => onToggleDeadOnly(event.target.checked)}
          />
          Somente Dead Jobs
        </label>
        <JobsSection state={jobs} deadOnly={deadOnly} />
      </section>
    </section>
  );
}
