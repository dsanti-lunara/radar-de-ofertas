import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SettingsApiError } from "./api";
import { parseSettings } from "./contracts";
import { settingsFixture } from "./fixtures";
import { SettingsWorkspace } from "./SettingsWorkspace";
import type { SettingsState } from "./state";

const readyState: SettingsState = { kind: "ready", settings: parseSettings(settingsFixture) };

function render(overrides: Partial<Parameters<typeof SettingsWorkspace>[0]> = {}): string {
  return renderToStaticMarkup(
    <SettingsWorkspace
      state={readyState}
      submitting={false}
      feedback={null}
      error={null}
      onSetMode={() => undefined}
      onSetStop={() => undefined}
      {...overrides}
    />,
  );
}

describe("SettingsWorkspace", () => {
  it("mostra as políticas versionadas/hasheadas", () => {
    const html = render();
    expect(html).toContain("automation-policy-1.0");
    expect(html).toContain("compliance-policy-1.0");
    expect(html).toContain("publication-policy-1.0");
    expect(html).toContain("cap 12/dia");
  });

  it("mostra elegibilidade AUTO sem promover sozinha", () => {
    const html = render();
    expect(html).toContain("Elegibilidade AUTO");
    expect(html).toContain("Promoção automática");
    expect(html).toContain("nunca");
    expect(html).toContain("Decisão humana obrigatória");
    expect(html).toContain("UNAVAILABLE");
  });

  it("exige confirmação nos controles perigosos", () => {
    const html = render();
    expect(html).toContain("Confirmo a mudança de modo");
    expect(html).toContain("Confirmo a alteração do kill switch");
    expect(html).toContain("STOP_EXTERNAL_ACTIONS");
  });

  it("mostra loading e erro acionável", () => {
    expect(render({ state: { kind: "loading" } })).toContain("Carregando configurações");
    const html = render({
      state: {
        kind: "unavailable",
        error: new SettingsApiError("SETTINGS_API_UNREACHABLE", "Control Center API inacessível"),
      },
    });
    expect(html).toContain("Control Center API inacessível");
    expect(html).toContain("alert");
  });
});
