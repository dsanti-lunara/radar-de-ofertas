/**
 * Opportunity Inbox (RDR-058): lista real de Candidates/Opportunities.
 *
 * Cada linha mostra produto, marketplace, preço, Deal, Monetization, Confidence,
 * brand, motivo principal e status, com a decisão da IA e a decisão humana
 * separadas (docs/11_OPERATIONS_AND_UI.md).
 */

import type { InboxItem, ReviewInbox } from "./contracts";

interface OpportunityInboxProps {
  readonly inbox: ReviewInbox;
  readonly selectedId: string | null;
  readonly onSelect: (candidateId: string) => void;
}

function decisionLabel(item: InboxItem): string {
  if (item.human_decision !== null) {
    return `Humano: ${item.human_decision}`;
  }
  if (item.ai_decision !== null) {
    return `IA: ${item.ai_decision}`;
  }
  if (item.decision !== null) {
    return `Sistema: ${item.decision}`;
  }
  return "Aguardando avaliação";
}

export function OpportunityInbox({ inbox, selectedId, onSelect }: OpportunityInboxProps) {
  return (
    <section aria-label="Opportunity Inbox">
      <h2>Oportunidades</h2>
      <p className="muted">
        {inbox.count} Candidate(s) reais consultados pela API (correlation {inbox.correlation_id}).
      </p>
      <table className="inbox">
        <caption className="sr-only">Candidates e oportunidades para revisão</caption>
        <thead>
          <tr>
            <th scope="col">Produto</th>
            <th scope="col">Marketplace</th>
            <th scope="col">Preço</th>
            <th scope="col">Deal</th>
            <th scope="col">Monetization</th>
            <th scope="col">Confidence</th>
            <th scope="col">Brand</th>
            <th scope="col">Motivo principal</th>
            <th scope="col">Status</th>
            <th scope="col">Ação</th>
          </tr>
        </thead>
        <tbody>
          {inbox.items.map((item) => (
            <tr key={item.candidate_id} data-state={item.candidate_state}>
              <th scope="row">{item.title ?? item.external_id}</th>
              <td>{item.marketplace}</td>
              <td>{item.current_price ?? "—"}</td>
              <td>{item.deal_score ?? "—"}</td>
              <td>{item.monetization_score ?? "—"}</td>
              <td>{item.confidence ?? "—"}</td>
              <td>{item.brand ?? "—"}</td>
              <td>{item.main_reason ?? "—"}</td>
              <td>
                <span data-state={item.opportunity_state ?? item.candidate_state}>
                  {item.opportunity_state ?? item.candidate_state}
                </span>
                <span className="muted"> {decisionLabel(item)}</span>
              </td>
              <td>
                <button type="button" onClick={() => onSelect(item.candidate_id)}>
                  {selectedId === item.candidate_id ? "Selecionado" : "Revisar"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
