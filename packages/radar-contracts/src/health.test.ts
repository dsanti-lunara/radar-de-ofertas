import { describe, expect, it } from "vitest";

import { HEALTH_SCHEMA_VERSION, isOperational, parseSystemHealth } from "./health.js";

const healthyReport = {
  schema_version: HEALTH_SCHEMA_VERSION,
  status: "HEALTHY",
  app_version: "0.1.0",
  correlation_id: "cid-1",
  observed_at: "2026-10-05T12:00:00+00:00",
  checks: [
    { name: "database", state: "HEALTHY", summary: "ok" },
    { name: "schema", state: "HEALTHY", summary: "ok" },
  ],
};

describe("parseSystemHealth", () => {
  it("aceita o contrato emitido pela CLI/API", () => {
    const report = parseSystemHealth(healthyReport);
    expect(report.status).toBe("HEALTHY");
    expect(report.checks).toHaveLength(2);
    expect(isOperational(report)).toBe(true);
  });

  it("aceita erro estruturado retryable", () => {
    const report = parseSystemHealth({
      ...healthyReport,
      status: "UNHEALTHY",
      checks: [
        {
          name: "database",
          state: "UNHEALTHY",
          summary: "Banco indisponível",
          error: {
            code: "RAD-DB-003",
            message: "unable to open database file",
            retryable: true,
            action: "Verificar caminho/permissão",
          },
        },
      ],
    });
    expect(isOperational(report)).toBe(false);
    expect(report.checks[0]?.error?.code).toBe("RAD-DB-003");
  });

  it("rejeita schema_version ausente", () => {
    const withoutSchemaVersion: Record<string, unknown> = { ...healthyReport };
    delete withoutSchemaVersion.schema_version;
    expect(() => parseSystemHealth(withoutSchemaVersion)).toThrow();
  });

  it("rejeita schema_version não suportado", () => {
    expect(() => parseSystemHealth({ ...healthyReport, schema_version: "9.9" })).toThrow();
  });

  it("rejeita estado de saúde desconhecido", () => {
    expect(() => parseSystemHealth({ ...healthyReport, status: "BROKEN" })).toThrow();
  });

  it("rejeita check sem nome", () => {
    expect(() =>
      parseSystemHealth({ ...healthyReport, checks: [{ state: "HEALTHY", summary: "x" }] }),
    ).toThrow();
  });
});
