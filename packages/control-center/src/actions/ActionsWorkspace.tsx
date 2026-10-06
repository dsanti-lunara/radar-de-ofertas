/**
 * Workspace da central de HumanActions (RDR-063).
 *
 * Apresentacional: recebe o estado resolvido e os callbacks. Toda ação mostra
 * impacto e próximos passos; uma ação cuja resolução pertence a outro fluxo
 * guardado não aparece como executável aqui (acceptance #5).
 */

import { HumanActionResolveForm } from "./HumanActionResolveForm";
import type { HumanAction } from "./contracts";
import type { DetailState, InboxState } from "./state";

export interface ActionsWorkspaceProps {
  readonly inbox: InboxState;
  readonly detail: DetailState;
  readonly selectedId: string | null;
  readonly onSelect: (humanActionId: string) => void;
  readonly onResolve: (reason: string) => void;
  readonly submitting: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
}

function Detail({
  state,
  selectedId,
  onResolve,
  submitting,
  feedback,
  error,
}: {
  readonly state: DetailState;
  readonly selectedId: string | null;
  readonly onResolve: (reason: string) => void;
  readonly submitting: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
}) {
  if (selectedId === null) {
    return <p className="muted">Selecione uma ação para ver impacto e próximos passos.</p>;
  }
  if (state.kind === "loading") {
    return <p role="status">Carregando ação…</p>;
  }
  if (state.kind === "unavailable") {
    return (
      <p className="alert" role="alert">
        {state.error.message}. {state.error.action}
      </p>
    );
  }
  const action: HumanAction = state.action;
  return (
    <section className="detail" aria-label="Detalhe da ação">
      <h2>{action.action_type}</h2>
      <p className="muted">Correlation ID: {action.correlation_id}</p>
      <dl>
        <dt>Status</dt>
        <dd data-state={action.status}>{action.status}</dd>
        <dt>Entidade</dt>
        <dd>
          {action.entity_type}:{action.entity_id}
        </dd>
        <dt>Motivo</dt>
        <dd>
          {action.reason} ({action.error_code})
        </dd>
        <dt>Impacto</dt>
        <dd>{action.impact}</dd>
        <dt>Próximos passos</dt>
        <dd>{action.next_steps}</dd>
      </dl>

      {action.resolution.resolvable_via_center && action.status === "OPEN" ? (
        <HumanActionResolveForm
          humanActionId={action.human_action_id}
          disabled={false}
          submitting={submitting}
          feedback={feedback}
          error={error}
          onResolve={onResolve}
        />
      ) : action.status === "RESOLVED" ? (
        <p className="alert alert--ok" role="status">
          Ação resolvida.
        </p>
      ) : (
        <p className="muted">
          Resolução indisponível nesta central ({action.resolution.mode}). {action.resolution.guidance}
        </p>
      )}
    </section>
  );
}

export function ActionsWorkspace({
  inbox,
  detail,
  selectedId,
  onSelect,
  onResolve,
  submitting,
  feedback,
  error,
}: ActionsWorkspaceProps) {
  return (
    <section className="actions-workspace" aria-label="Ações humanas">
      <h2>Ações humanas</h2>
      {inbox.kind === "loading" ? (
        <p role="status">Carregando ações humanas…</p>
      ) : inbox.kind === "empty" ? (
        <p role="status">Nenhuma ação humana pendente ou registrada.</p>
      ) : inbox.kind === "unavailable" ? (
        <p className="alert" role="alert">
          {inbox.error.message}. {inbox.error.action}
        </p>
      ) : (
        <>
          <p className="muted">Correlation ID: {inbox.inbox.correlation_id}</p>
          <table className="inbox">
            <caption className="sr-only">Ações humanas</caption>
            <thead>
              <tr>
                <th scope="col">Tipo</th>
                <th scope="col">Status</th>
                <th scope="col">Entidade</th>
                <th scope="col">Motivo</th>
                <th scope="col">Impacto</th>
              </tr>
            </thead>
            <tbody>
              {inbox.inbox.human_actions.map((action) => (
                <tr key={action.human_action_id} data-state={action.status}>
                  <th scope="row">
                    <button type="button" onClick={() => onSelect(action.human_action_id)}>
                      {action.action_type}
                    </button>
                  </th>
                  <td>{action.status}</td>
                  <td>
                    {action.entity_type}:{action.entity_id}
                  </td>
                  <td>
                    {action.reason} ({action.error_code})
                  </td>
                  <td>{action.impact}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <Detail
        state={detail}
        selectedId={selectedId}
        onResolve={onResolve}
        submitting={submitting}
        feedback={feedback}
        error={error}
      />
    </section>
  );
}
