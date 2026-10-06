import { describe, expect, it } from "vitest";

import {
  HOME_HEALTH_SCHEMA_VERSION,
  isOperational,
  parseHomeHealth,
  type HomeHealth,
} from "./contracts";

const overview: Record<string, unknown> = {
  schema_version: HOME_HEALTH_SCHEMA_VERSION,
  status: "DEGRADED",
  engine_version: "home-health-1.0",
  app_version: "0.1.0",
  correlation_id: "cid-1",
  observed_at: "2026-10-06T12:00:00+00:00",
  items: [
    {
      capability: "core",
      state: "HEALTHY",
      summary: "Control Center API respondendo",
      source: "api",
      reason_code: "API_RESPONDING",
    },
    {
      capability: "scheduler",
      state: "UNKNOWN",
      summary: "Integração não registrada",
      source: "unregistered",
      reason_code: "INTEGRATION_NOT_REGISTERED",
      integration: "scheduler",
    },
  ],
};

function parsed(): HomeHealth {
  return parseHomeHealth(overview);
}

describe("parseHomeHealth", () => {
  it("aceita o contrato versionado do read model", () => {
    const result = parsed();
    expect(result.status).toBe("DEGRADED");
    expect(result.items).toHaveLength(2);
    expect(result.items[1]?.reason_code).toBe("INTEGRATION_NOT_REGISTERED");
    expect(isOperational(result)).toBe(true);
  });

  it("aceita erro estruturado com ação", () => {
    const result = parseHomeHealth({
      ...overview,
      status: "UNHEALTHY",
      items: [
        {
          capability: "database",
          state: "UNHEALTHY",
          summary: "Banco indisponível",
          source: "health",
          error: {
            code: "RAD-DB-003",
            message: "unable to open database file",
            retryable: true,
            action: "Verificar caminho/permissão do banco",
          },
        },
      ],
    });
    expect(isOperational(result)).toBe(false);
    expect(result.items[0]?.error?.code).toBe("RAD-DB-003");
  });

  it("rejeita schema_version ausente", () => {
    const withoutSchemaVersion: Record<string, unknown> = { ...overview };
    delete withoutSchemaVersion["schema_version"];
    expect(() => parseHomeHealth(withoutSchemaVersion)).toThrow();
  });

  it("rejeita schema_version não suportado", () => {
    expect(() => parseHomeHealth({ ...overview, schema_version: "9.9" })).toThrow();
  });

  it("rejeita estado de saúde desconhecido", () => {
    expect(() => parseHomeHealth({ ...overview, status: "BROKEN" })).toThrow();
  });

  it("rejeita item sem capacidade", () => {
    expect(() =>
      parseHomeHealth({ ...overview, items: [{ state: "HEALTHY", summary: "x", source: "api" }] }),
    ).toThrow();
  });
});
