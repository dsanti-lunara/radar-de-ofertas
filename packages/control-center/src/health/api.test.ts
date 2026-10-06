import { describe, expect, it } from "vitest";

import { HOME_HEALTH_SCHEMA_VERSION } from "../contracts";
import { fetchHomeHealth, HealthPollError, type FetchLike } from "./api";
import { loadHomeHealth } from "./poller";

const body = {
  schema_version: HOME_HEALTH_SCHEMA_VERSION,
  status: "HEALTHY",
  engine_version: "home-health-1.0",
  app_version: "0.1.0",
  correlation_id: "cid-1",
  observed_at: "2026-10-06T12:00:00+00:00",
  items: [{ capability: "core", state: "HEALTHY", summary: "ok", source: "api" }],
};

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("fetchHomeHealth", () => {
  it("consome o read model pela fronteira REST local", async () => {
    const calls: string[] = [];
    const fetchImpl: FetchLike = async (input) => {
      calls.push(input);
      return jsonResponse(body);
    };
    const overview = await fetchHomeHealth("/health/overview", fetchImpl);
    expect(calls).toEqual(["/health/overview"]);
    expect(overview.status).toBe("HEALTHY");
    expect(overview.items[0]?.capability).toBe("core");
  });

  it("não vaza a causa do transporte em falha de rede", async () => {
    const secret = "RADAR_SUPER_SECRET_TOKEN";
    const fetchImpl: FetchLike = async () => {
      throw new Error(`connect failed with ${secret}`);
    };
    const error = await fetchHomeHealth("/health/overview", fetchImpl).catch(
      (caught: unknown) => caught,
    );
    expect(error).toBeInstanceOf(HealthPollError);
    const pollError = error as HealthPollError;
    expect(pollError.code).toBe("CONTROL_CENTER_UNREACHABLE");
    expect(pollError.message).not.toContain(secret);
    expect(pollError.action).not.toContain(secret);
    expect(pollError.action.length).toBeGreaterThan(0);
  });

  it("reporta HTTP não-ok com mensagem acionável e sem corpo bruto", async () => {
    const fetchImpl: FetchLike = async () =>
      new Response("credencial=segredo", { status: 503, statusText: "Service Unavailable" });
    const error = (await fetchHomeHealth("/health/overview", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as HealthPollError;
    expect(error.code).toBe("CONTROL_CENTER_HTTP_ERROR");
    expect(error.message).toContain("503");
    expect(error.message).not.toContain("segredo");
  });

  it("rejeita corpo não-JSON", async () => {
    const fetchImpl: FetchLike = async () => new Response("<html>404</html>", { status: 200 });
    const error = (await fetchHomeHealth("/health/overview", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as HealthPollError;
    expect(error.code).toBe("HEALTH_OVERVIEW_INVALID");
  });

  it("rejeita schema_version não suportado", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse({ ...body, schema_version: "9.9" });
    const error = (await fetchHomeHealth("/health/overview", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as HealthPollError;
    expect(error.code).toBe("HEALTH_OVERVIEW_INVALID");
  });
});

describe("loadHomeHealth", () => {
  it("devolve ready quando a fronteira responde", async () => {
    const state = await loadHomeHealth("/health/overview", async () => jsonResponse(body));
    expect(state.kind).toBe("ready");
  });

  it("devolve unavailable (não lança) quando a API cai", async () => {
    const state = await loadHomeHealth("/health/overview", async () => {
      throw new Error("offline");
    });
    expect(state.kind).toBe("unavailable");
    if (state.kind === "unavailable") {
      expect(state.error.code).toBe("CONTROL_CENTER_UNREACHABLE");
    }
  });
});
