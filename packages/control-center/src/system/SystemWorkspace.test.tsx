import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SystemApiError } from "./api";
import { parseIntegrationsList, parseJobsInbox } from "./contracts";
import { integrationsFixture, jobsFixture } from "./fixtures";
import { SystemWorkspace } from "./SystemWorkspace";
import type { IntegrationsState, JobsState } from "./state";

const readyIntegrations: IntegrationsState = {
  kind: "ready",
  list: parseIntegrationsList(integrationsFixture),
};
const readyJobs: JobsState = { kind: "ready", inbox: parseJobsInbox(jobsFixture) };

function render(overrides: Partial<Parameters<typeof SystemWorkspace>[0]> = {}): string {
  return renderToStaticMarkup(
    <SystemWorkspace
      integrations={readyIntegrations}
      jobs={readyJobs}
      deadOnly={false}
      onToggleDeadOnly={() => undefined}
      onUpdateIntegration={() => undefined}
      submitting={false}
      feedback={null}
      error={null}
      {...overrides}
    />,
  );
}

describe("SystemWorkspace", () => {
  it("mostra integrações com estado textual", () => {
    const html = render();
    expect(html).toContain("telegram");
    expect(html).toContain("ONLINE");
    expect(html).toContain("AUTH_REQUIRED");
    expect(html).toContain("Não");
  });

  it("mostra jobs reais e o filtro de Dead Jobs", () => {
    const html = render();
    expect(html).toContain("NORMALIZE_CAPTURE");
    expect(html).toContain("PENDING");
    expect(html).toContain("Somente Dead Jobs");
  });

  it("filtra somente Dead Jobs quando pedido", () => {
    const html = render({ deadOnly: true });
    expect(html).toContain("PUBLISH_TELEGRAM");
    expect(html).toContain("DEAD");
    expect(html).not.toContain("job_pending");
  });

  it("exige confirmação na mudança de integração", () => {
    const html = render();
    expect(html).toContain("Confirmo a alteração desta integração");
    expect(html).toContain("Alterar integração");
  });

  it("mostra loading/empty/unavailable textuais", () => {
    expect(render({ integrations: { kind: "loading" } })).toContain("Carregando integrações");
    expect(render({ jobs: { kind: "empty" } })).toContain("Nenhum job registrado");
    const unavailable = render({
      jobs: {
        kind: "unavailable",
        error: new SystemApiError("SYSTEM_API_UNREACHABLE", "Control Center API inacessível"),
      },
    });
    expect(unavailable).toContain("Control Center API inacessível");
    expect(unavailable).toContain("alert");
  });
});
