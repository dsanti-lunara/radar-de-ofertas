/**
 * Publication Inbox (RDR-061): lista real de Publications e previews prontos.
 *
 * Cada linha mostra brand, channel, produto, preço, status, revision e external
 * ID; entradas `PREVIEW` ainda não têm envio e aguardam aprovação explícita.
 */

import type { PublicationInbox, PublicationInboxItem } from "./contracts";

interface PublicationInboxProps {
  readonly inbox: PublicationInbox;
  readonly selectedId: string | null;
  readonly onSelect: (item: PublicationInboxItem) => void;
}

function kindLabel(item: PublicationInboxItem): string {
  if (item.kind === "PREVIEW") {
    return "Pronta para aprovar";
  }
  return "Publicação";
}

export function PublicationInbox({ inbox, selectedId, onSelect }: PublicationInboxProps) {
  return (
    <section aria-label="Publication Inbox">
      <h2>Publicações</h2>
      <p className="muted">
        {inbox.count} entrada(s) reais consultadas pela API (correlation {inbox.correlation_id}).
      </p>
      <table className="inbox">
        <caption className="sr-only">Publicações e previews prontos para aprovar</caption>
        <thead>
          <tr>
            <th scope="col">Produto</th>
            <th scope="col">Brand</th>
            <th scope="col">Canal</th>
            <th scope="col">Preço</th>
            <th scope="col">Revision</th>
            <th scope="col">External ID</th>
            <th scope="col">Status</th>
            <th scope="col">Ação</th>
          </tr>
        </thead>
        <tbody>
          {inbox.items.map((item) => (
            <tr key={item.entry_id} data-kind={item.kind} data-status={item.status}>
              <th scope="row">{item.product.title ?? item.product.external_id ?? item.entry_id}</th>
              <td>{item.brand ?? "—"}</td>
              <td>{item.channel ?? "—"}</td>
              <td>{item.published_price ?? item.product.current_price ?? "—"}</td>
              <td>{item.revision ?? "—"}</td>
              <td>{item.external_message_id ?? "—"}</td>
              <td>
                <span data-state={item.status}>{item.status}</span>
                <span className="muted"> {kindLabel(item)}</span>
              </td>
              <td>
                <button type="button" onClick={() => onSelect(item)}>
                  {selectedId === item.entry_id ? "Selecionado" : "Consultar"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
