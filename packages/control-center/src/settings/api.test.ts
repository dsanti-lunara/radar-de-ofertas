import { describe, expect, it } from "vitest";

import {
  fetchSettings,
  setGlobalMode,
  SettingsApiError,
  setStopExternalActions,
  type FetchLike,
} from "./api";
import { modeChangeFixture, settingsFixture, stopChangeFixture } from "./fixtures";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("fetchSettings", () => {
  it("consome o read model versionado", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse(settingsFixture);
    const settings = await fetchSettings("/settings", fetchImpl);
    expect(settings.correlation_id).toBe("cid-set");
  });

  it("propaga o erro estruturado", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse(
        { error: { code: "RAD-AI-001", message: "provider indisponível", retryable: true } },
        503,
      );
    const error = (await fetchSettings("/settings", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as SettingsApiError;
    expect(error.code).toBe("RAD-AI-001");
    expect(error.retryable).toBe(true);
  });

  it("rejeita contrato inválido", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse({ ...settingsFixture, schema_version: "9.9" });
    const error = (await fetchSettings("/settings", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as SettingsApiError;
    expect(error.code).toBe("SETTINGS_INVALID");
  });
});

describe("operational controls", () => {
  it("envia o modo pelo POST", async () => {
    let method: string | undefined;
    let body: unknown;
    const fetchImpl: FetchLike = async (_input, init) => {
      method = init?.method;
      body = init?.body === undefined ? undefined : JSON.parse(String(init.body));
      return jsonResponse(modeChangeFixture);
    };
    const result = await setGlobalMode("PAUSED", "manutenção", fetchImpl);
    expect(method).toBe("POST");
    expect(body).toEqual({ schema_version: "1.0", mode: "PAUSED", reason: "manutenção" });
    expect(result.state.global_mode).toBe("PAUSED");
  });

  it("ativa o kill switch com POST e libera com DELETE", async () => {
    const methods: string[] = [];
    const fetchImpl: FetchLike = async (_input, init) => {
      methods.push(init?.method ?? "GET");
      return jsonResponse(stopChangeFixture);
    };
    await setStopExternalActions(true, "incidente", fetchImpl);
    await setStopExternalActions(false, null, fetchImpl);
    expect(methods).toEqual(["POST", "DELETE"]);
  });
});
