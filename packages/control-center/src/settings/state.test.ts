import { describe, expect, it } from "vitest";

import { SettingsApiError, type FetchLike } from "./api";
import { settingsFixture } from "./fixtures";
import { loadSettings } from "./state";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("loadSettings", () => {
  it("retorna ready com o snapshot", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse(settingsFixture);
    const state = await loadSettings("/settings", fetchImpl);
    expect(state.kind).toBe("ready");
  });

  it("retorna unavailable sem lançar", async () => {
    const fetchImpl: FetchLike = async () => {
      throw new Error("offline");
    };
    const state = await loadSettings("/settings", fetchImpl);
    expect(state.kind).toBe("unavailable");
    if (state.kind === "unavailable") {
      expect(state.error).toBeInstanceOf(SettingsApiError);
    }
  });
});
