import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ActionsWorkspace } from "./ActionsWorkspace";
import { HumanActionsApiError } from "./api";
import { parseHumanAction, parseHumanActionList } from "./contracts";
import { delegatedHumanActionFixture, humanActionFixture, humanActionListFixture } from "./fixtures";
import type { DetailState, InboxState } from "./state";

const readyInbox: InboxState = {
  kind: "ready",
  inbox: parseHumanActionList(humanActionListFixture),
};
const openDetail: DetailState = {
  kind: "ready",
  action: parseHumanAction(humanActionFixture),
};
const delegatedDetail: DetailState = {
  kind: "ready",
  action: parseHumanAction(delegatedHumanActionFixture),
};

function render(overrides: Partial<Parameters<typeof ActionsWorkspace>[0]> = {}): string {
  return renderToStaticMarkup(
    <ActionsWorkspace
      inbox={readyInbox}
      detail={openDetail}
      selectedId="ha_1"
      onSelect={() => undefined}
      onResolve={() => undefined}
      submitting={false}
      feedback={null}
      error={null}
      {...overrides}
    />,
  );
}

describe("ActionsWorkspace", () => {
  it("mostra feedback textual de loading", () => {
    expect(render({ inbox: { kind: "loading" } })).toContain("Carregando ações humanas");
  });

  it("mostra estado vazio real", () => {
    expect(render({ inbox: { kind: "empty" } })).toContain("Nenhuma ação humana");
  });

  it("mostra erro acionável", () => {
    const html = render({
      inbox: {
        kind: "unavailable",
        error: new HumanActionsApiError("HUMAN_ACTIONS_API_UNREACHABLE", "Control Center API inacessível"),
      },
    });
    expect(html).toContain("Control Center API inacessível");
    expect(html).toContain("alert");
  });

  it("lista ações reais com status e impacto", () => {
    const html = render();
    expect(html).toContain("DEAD_JOB_REVIEW");
    expect(html).toContain("OPEN");
    expect(html).toContain("Dead Job Queue");
  });

  it("oferece resolução apenas para ação OPERATOR_ACK aberta", () => {
    const html = render();
    expect(html).toContain("Resolver ação");
    expect(html).toContain("Confirmo que a intervenção foi executada");
  });

  it("não oferece resolução para ação delegada", () => {
    const html = render({ detail: delegatedDetail, selectedId: "ha_pub" });
    expect(html).not.toContain("Resolver ação");
    expect(html).toContain("Resolução indisponível nesta central");
    expect(html).toContain("exige evidência");
  });
});
