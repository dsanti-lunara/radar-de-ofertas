/**
 * Publication detail (RDR-062): preview, link/tracking, revision, external ID,
 * última validação, timeline, versões e as ações auditadas.
 *
 * O painel de HumanAction explica impacto e próximos passos quando um resultado
 * desconhecido suspende a publicação; nenhuma ação desta tela reenvia sozinha.
 */

import { useState, type ReactNode } from "react";

import type { PublicationAction, PublicationDetailEnvelope } from "./contracts";

interface PublicationDetailProps {
  readonly detail: PublicationDetailEnvelope;
  readonly onAction: (action: PublicationAction, reason: string) => void;
  readonly busy: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
  readonly approvalForm?: ReactNode;
}

function PublicationActions({
  publicationId,
  onAction,
  busy,
  feedback,
  error,
}: {
  readonly publicationId: string;
  readonly onAction: (action: PublicationAction, reason: string) => void;
  readonly busy: boolean;
  readonly feedback: string | null;
  readonly error: string | null;
}) {
  const [reason, setReason] = useState("");
  return (
    <section aria-label="Ações da publicação">
      <h3>Ações</h3>
      <label>
        Motivo
        <input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={512} />
      </label>
      <div className="publication-actions">
        <button type="button" disabled={busy} onClick={() => onAction("revalidate", reason)}>
          Revalidar
        </button>
        <button type="button" disabled={busy} onClick={() => onAction("expire", reason)}>
          Expirar
        </button>
        <button type="button" disabled={busy} onClick={() => onAction("cancel", reason)}>
          Cancelar
        </button>
      </div>
      <p className="muted">
        Publicação {publicationId}: as ações são auditadas e nunca reenviam automaticamente.
      </p>
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

export function PublicationDetail({
  detail,
  onAction,
  busy,
  feedback,
  error,
  approvalForm,
}: PublicationDetailProps) {
  const view = detail.detail;
  const publicationId = view.publication?.publication_id ?? detail.entry_id;

  return (
    <section aria-label="Publication detail" className="detail">
      <h2>{view.product.title ?? view.product.external_id ?? detail.entry_id}</h2>
      <p className="muted">
        {view.kind} · {view.product.marketplace ?? "—"} · {view.product.external_id ?? "—"}
        {view.publication === null ? "" : ` · ${view.publication.destination_id}`}
      </p>
      <ul>
        <li>Revision: {view.revision ?? "—"}</li>
        <li>External message ID: {view.external_message_id ?? "—"}</li>
        <li>
          Última validação:{" "}
          {view.last_validation === null
            ? "—"
            : `${view.last_validation.validated_at} (${view.last_validation.source}, ${
                view.last_validation.allowed === false ? "bloqueada" : "ok"
              })`}
        </li>
      </ul>

      <section aria-label="Preview">
        <h3>Preview</h3>
        {view.preview === null ? (
          <p className="muted">Sem preview preparada.</p>
        ) : (
          <>
            <p className="muted">
              {view.preview.channel} · {view.preview.status} · renderer{" "}
              {view.preview.renderer_version}
              {view.preview.stale ? " · STALE (revalidar antes do envio)" : ""}
            </p>
            <pre className="publication-preview">{view.preview.text}</pre>
            <p>
              Preço: <strong>{view.preview.price ?? "—"}</strong>
            </p>
            <p className="muted">{view.preview.disclosure}</p>
          </>
        )}
      </section>

      <section aria-label="Affiliate link e tracking">
        <h3>Link e tracking</h3>
        {view.link === null ? (
          <p className="muted">Sem AffiliateLink associado.</p>
        ) : (
          <ul>
            <li>Link literal: {view.link.affiliate_url}</li>
            <li>Método: {view.link.generation_method}</li>
            <li>Produtivo: {view.link.productive ? "sim" : "não (Fake)"}</li>
            <li>Tracking interno: {view.link.tracking_internal_reference}</li>
            <li>Etiqueta externa: {view.link.tracking_label}</li>
            <li>Mapping: {view.link.tracking_mapping_version}</li>
          </ul>
        )}
      </section>

      <section aria-label="Timeline">
        <h3>Timeline</h3>
        {view.timeline.length === 0 ? (
          <p className="muted">Sem eventos.</p>
        ) : (
          <ol>
            {view.timeline.map((entry, index) => (
              <li key={`${entry.event_type}-${entry.occurred_at}-${index}`}>
                {entry.occurred_at} · {entry.event_type} ({entry.source})
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-label="Human actions">
        <h3>HumanAction</h3>
        {view.human_actions.length === 0 ? (
          <p className="muted">Nenhuma intervenção humana pendente.</p>
        ) : (
          <ul>
            {view.human_actions.map((action, index) => (
              <li key={action.human_action_id ?? index}>
                <strong>{action.action_type ?? "REVIEW_PUBLICATION"}</strong> ({action.reason ?? "—"}) ·{" "}
                {action.status ?? "OPEN"}
                {action.impact === undefined ? null : <p className="muted">{action.impact}</p>}
                {action.next_steps === undefined ? null : (
                  <p className="muted">Próximos passos: {action.next_steps}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {approvalForm}

      {view.kind === "PUBLICATION" ? (
        <PublicationActions
          publicationId={publicationId}
          onAction={onAction}
          busy={busy}
          feedback={feedback}
          error={error}
        />
      ) : null}
    </section>
  );
}
