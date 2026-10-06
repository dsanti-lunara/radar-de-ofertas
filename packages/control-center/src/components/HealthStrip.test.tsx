import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CapabilityHealth } from "../contracts";
import { HealthStrip } from "./HealthStrip";

const items: readonly CapabilityHealth[] = [
  { capability: "core", state: "HEALTHY", summary: "API respondendo", source: "api" },
  {
    capability: "database",
    state: "UNHEALTHY",
    summary: "Banco indisponível",
    source: "health",
    error: { code: "RAD-DB-003", message: "down", retryable: true },
  },
  { capability: "shopee", state: "UNKNOWN", summary: "Integração não registrada", source: "unregistered" },
];

describe("HealthStrip", () => {
  it("renderiza cada capability com rótulo textual de estado", () => {
    const html = renderToStaticMarkup(<HealthStrip items={items} />);
    expect(html).toContain("Core");
    expect(html).toContain("Banco");
    expect(html).toContain("Shopee");
    expect(html).toContain("Saudável");
    expect(html).toContain("Indisponível");
    expect(html).toContain("Desconhecido");
  });

  it("expõe o estado no atributo data para leitura não visual", () => {
    const html = renderToStaticMarkup(<HealthStrip items={items} />);
    expect(html).toContain('data-state="HEALTHY"');
    expect(html).toContain('data-state="UNHEALTHY"');
    expect(html).toContain('data-state="UNKNOWN"');
  });
});
