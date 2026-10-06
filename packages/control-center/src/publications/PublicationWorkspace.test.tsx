import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PublicationsApiError } from "./api";
import { parsePublicationDetail, parsePublicationInbox } from "./contracts";
import {
  inboxFixture,
  previewDetailFixture,
  publicationDetailFixture,
  unknownDetailFixture,
} from "./fixtures";
import { PublicationWorkspace } from "./PublicationWorkspace";
import type { DetailState, InboxState } from "./state";

const readyInbox: InboxState = { kind: "ready", inbox: parsePublicationInbox(inboxFixture) };
const publicationDetail: DetailState = {
  kind: "ready",
  detail: parsePublicationDetail(publicationDetailFixture, "pub_1"),
};
const previewDetail: DetailState = {
  kind: "ready",
  detail: parsePublicationDetail(previewDetailFixture, "preview:opp_2"),
};
const unknownDetail: DetailState = {
  kind: "ready",
  detail: parsePublicationDetail(unknownDetailFixture, "pub_1"),
};

function render(overrides: Partial<Parameters<typeof PublicationWorkspace>[0]> = {}): string {
  return renderToStaticMarkup(
    <PublicationWorkspace
      inbox={readyInbox}
      detail={publicationDetail}
      selectedId="pub_1"
      onSelect={() => undefined}
      onApprove={() => undefined}
      onAction={() => undefined}
      submitting={false}
      approvalDisabled={false}
      feedback={null}
      error={null}
      {...overrides}
    />,
  );
}

describe("PublicationWorkspace", () => {
  it("mostra o estado de loading do Inbox", () => {
    expect(render({ inbox: { kind: "loading" } })).toContain("Carregando publicações");
  });

  it("mostra o estado vazio como feedback real", () => {
    expect(render({ inbox: { kind: "empty" } })).toContain("Nenhuma publicação");
  });

  it("mostra erro acionável quando a API está indisponível", () => {
    const error = new PublicationsApiError(
      "PUBLICATIONS_API_UNREACHABLE",
      "Control Center API inacessível",
    );
    const html = render({ inbox: { kind: "unavailable", error } });
    expect(html).toContain("Control Center API inacessível");
    expect(html).toContain(error.action);
  });

  it("renderiza o Inbox com brand, canal, preço, status e external ID", () => {
    const html = render();
    expect(html).toContain("Perfume");
    expect(html).toContain("fake-telegram-dest-tg-sandbox-pub_1");
    expect(html).toContain("Pronta para aprovar");
    expect(html).toContain("Aspirador");
  });

  it("renderiza preview, link/tracking, revision e timeline", () => {
    const html = render();
    expect(html).toContain("Perfume em oferta");
    expect(html).toContain("https://afiliado.example/lnk_1");
    expect(html).toContain("rbtgoffer");
    expect(html).toContain("CREATED");
    expect(html).toContain("PUBLISHED");
    expect(html).toContain("fake-telegram-dest-tg-sandbox-pub_1");
  });

  it("oferece as ações auditadas para uma publicação", () => {
    const html = render();
    expect(html).toContain("Revalidar");
    expect(html).toContain("Expirar");
    expect(html).toContain("Cancelar");
  });

  it("mostra o formulário de aprovação explícita no preview e não as ações", () => {
    const html = render({
      detail: previewDetail,
      selectedId: "preview:opp_2",
    });
    expect(html).toContain("Aprovar publicação");
    expect(html).toContain("Aprovar e publicar");
    expect(html).toContain("Aprovar um Candidate não autoriza envio");
    expect(html).not.toContain("Revalidar");
  });

  it("encaminha resultado desconhecido para a HumanAction", () => {
    const html = render({ detail: unknownDetail });
    expect(html).toContain("REVIEW_PUBLICATION");
    expect(html).toContain(
      "Uma publicação pode ter sido enviada sem confirmação local.",
    );
    expect(html).toContain("Reunir evidência suficiente");
  });

  it("mostra detalhe indisponível sem perder o Inbox", () => {
    const error = new PublicationsApiError("RAD-PUB-002", "Publication não encontrada");
    const html = render({ detail: { kind: "unavailable", error } });
    expect(html).toContain("Publication não encontrada");
    expect(html).toContain("Perfume");
  });

  it("mostra feedback após aprovar", () => {
    const html = render({ feedback: "Publicação aprovada (PUBLISHED)." });
    expect(html).toContain("Publicação aprovada (PUBLISHED).");
  });
});
