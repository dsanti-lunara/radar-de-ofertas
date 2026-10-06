import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ReviewApiError } from "./api";
import { parseReviewDetail, parseReviewInbox } from "./contracts";
import { detailFixture, inboxFixture } from "./fixtures";
import { ReviewWorkspace } from "./ReviewWorkspace";
import type { DetailState, InboxState } from "./state";

const readyInbox: InboxState = { kind: "ready", inbox: parseReviewInbox(inboxFixture) };
const readyDetail: DetailState = { kind: "ready", detail: parseReviewDetail(detailFixture) };

function render(overrides: Partial<Parameters<typeof ReviewWorkspace>[0]> = {}): string {
  return renderToStaticMarkup(
    <ReviewWorkspace
      inbox={readyInbox}
      detail={readyDetail}
      selectedId="cand_1"
      onSelect={() => undefined}
      onSubmitReview={() => undefined}
      submitting={false}
      feedback={null}
      error={null}
      {...overrides}
    />,
  );
}

describe("ReviewWorkspace", () => {
  it("mostra o estado de loading do Inbox", () => {
    const html = render({ inbox: { kind: "loading" } });
    expect(html).toContain("Carregando Inbox");
  });

  it("mostra o estado vazio como feedback real", () => {
    const html = render({ inbox: { kind: "empty" } });
    expect(html).toContain("Nenhum Candidate no Inbox");
  });

  it("mostra erro acionável quando a API está indisponível", () => {
    const error = new ReviewApiError("REVIEW_API_UNREACHABLE", "Control Center API inacessível");
    const html = render({ inbox: { kind: "unavailable", error } });
    expect(html).toContain("Control Center API inacessível");
    expect(html).toContain(error.action);
  });

  it("renderiza os dados reais do Inbox com Deal, Monetization e status", () => {
    const html = render();
    expect(html).toContain("Perfume");
    expect(html).toContain("MERCADO_LIVRE");
    expect(html).toContain("80.00");
    expect(html).toContain("100.00");
    expect(html).toContain("IA: APPROVE");
  });

  it("renderiza o detalhe com timeline, Evidence e versões", () => {
    const html = render();
    expect(html).toContain("CAPTURE_RECEIVED");
    expect(html).toContain("AI_REVIEW_RECORDED");
    expect(html).toContain("current_price");
    expect(html).toContain("knowledge-1.0");
  });

  it("mostra o portão operacional bloqueando o envio em SHADOW", () => {
    const html = render();
    expect(html).toContain("SHADOW");
    expect(html).toContain("bloqueado");
    expect(html).toContain("SHADOW_NO_COMMERCIAL_SEND");
  });

  it("oferece Approve, Reject e Edit content no formulário de review", () => {
    const html = render();
    expect(html).toContain("Aprovar Candidate");
    expect(html).toContain("Rejeitar");
    expect(html).toContain("Editar conteúdo");
    expect(html).toContain("Registrar review");
  });

  it("mostra detalhe indisponível sem perder o Inbox", () => {
    const error = new ReviewApiError("RAD-UI-003", "Candidate da review não encontrado");
    const html = render({ detail: { kind: "unavailable", error } });
    expect(html).toContain("Candidate da review não encontrado");
    expect(html).toContain("Perfume");
  });

  it("mostra feedback após registrar uma review", () => {
    const html = render({ feedback: "Review registrada (APPROVE)." });
    expect(html).toContain("Review registrada (APPROVE).");
  });
});
