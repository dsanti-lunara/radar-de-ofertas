import { describe, expect, it } from "vitest";

import {
  fetchIntegrations,
  fetchJobs,
  setIntegrationState,
  SystemApiError,
  type FetchLike,
} from "./api";
import { integrationsFixture, jobsFixture } from "./fixtures";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("fetchIntegrations", () => {
  it("consome a saúde padronizada", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse(integrationsFixture);
    const list = await fetchIntegrations("/integrations", fetchImpl);
    expect(list.integrations.map((item) => item.name)).toEqual(["telegram", "shopee"]);
  });

  it("propaga o erro estruturado", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse(
        { error: { code: "RAD-WF-018", message: "input inválido", retryable: false } },
        422,
      );
    const error = (await fetchIntegrations("/integrations", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as SystemApiError;
    expect(error.code).toBe("RAD-WF-018");
  });
});

describe("fetchJobs", () => {
  it("consome o listing de jobs", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse(jobsFixture);
    const inbox = await fetchJobs("/jobs", fetchImpl);
    expect(inbox.count).toBe(2);
  });

  it("não vaza a causa do transporte", async () => {
    const secret = "RADAR_SECRET";
    const fetchImpl: FetchLike = async () => {
      throw new Error(`boom ${secret}`);
    };
    const error = (await fetchJobs("/jobs", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as SystemApiError;
    expect(error.code).toBe("SYSTEM_API_UNREACHABLE");
    expect(error.message).not.toContain(secret);
  });
});

describe("setIntegrationState", () => {
  it("envia o novo estado pelo PUT", async () => {
    let method: string | undefined;
    let body: unknown;
    const fetchImpl: FetchLike = async (_input, init) => {
      method = init?.method;
      body = init?.body === undefined ? undefined : JSON.parse(String(init.body));
      return jsonResponse({
        schema_version: "1.0",
        status: "OK",
        correlation_id: "cid",
        integration: { ...integrationsFixture.integrations[0], state: "DISABLED", operational: false },
      });
    };
    const result = await setIntegrationState("telegram", "DISABLED", null, fetchImpl);
    expect(method).toBe("PUT");
    expect(body).toEqual({ schema_version: "1.0", state: "DISABLED", summary: null });
    expect(result.integration.state).toBe("DISABLED");
  });
});
