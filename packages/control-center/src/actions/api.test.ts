import { describe, expect, it } from "vitest";

import {
  fetchHumanAction,
  fetchHumanActions,
  HumanActionsApiError,
  resolveHumanAction,
  type FetchLike,
} from "./api";
import {
  humanActionFixture,
  humanActionListFixture,
  humanActionResolveResultFixture,
} from "./fixtures";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("fetchHumanActions", () => {
  it("consome o read model pela fronteira REST local", async () => {
    const calls: string[] = [];
    const fetchImpl: FetchLike = async (input) => {
      calls.push(input);
      return jsonResponse(humanActionListFixture);
    };
    const inbox = await fetchHumanActions("/human-actions", fetchImpl);
    expect(calls).toEqual(["/human-actions"]);
    expect(inbox.human_actions[0]?.impact).toBeTruthy();
  });

  it("propaga o erro estruturado do radar-api", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse(
        { error: { code: "RAD-WF-011", message: "HumanAction não encontrada", retryable: false } },
        404,
      );
    const error = (await fetchHumanActions("/human-actions", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as HumanActionsApiError;
    expect(error.code).toBe("RAD-WF-011");
    expect(error.retryable).toBe(false);
  });

  it("não vaza a causa do transporte em falha de rede", async () => {
    const secret = "RADAR_SUPER_SECRET_TOKEN";
    const fetchImpl: FetchLike = async () => {
      throw new Error(`connect failed with ${secret}`);
    };
    const error = (await fetchHumanActions("/human-actions", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as HumanActionsApiError;
    expect(error.code).toBe("HUMAN_ACTIONS_API_UNREACHABLE");
    expect(error.message).not.toContain(secret);
  });

  it("rejeita contrato inválido", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse({ ...humanActionListFixture, schema_version: "9.9" });
    const error = (await fetchHumanActions("/human-actions", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as HumanActionsApiError;
    expect(error.code).toBe("HUMAN_ACTIONS_INBOX_INVALID");
  });
});

describe("fetchHumanAction", () => {
  it("consome o detail versionado", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse(humanActionFixture);
    const action = await fetchHumanAction("/human-actions/ha_1", fetchImpl);
    expect(action.human_action_id).toBe("ha_1");
    expect(action.resolution.resolvable_via_center).toBe(true);
  });
});

describe("resolveHumanAction", () => {
  it("envia o motivo e o schema_version pelo POST", async () => {
    let method: string | undefined;
    let body: unknown;
    const fetchImpl: FetchLike = async (_input, init) => {
      method = init?.method;
      body = init?.body === undefined ? undefined : JSON.parse(String(init.body));
      return jsonResponse(humanActionResolveResultFixture);
    };
    const result = await resolveHumanAction("ha_1", "Job reprocessado", fetchImpl);
    expect(method).toBe("POST");
    expect(body).toEqual({ schema_version: "1.0", reason: "Job reprocessado" });
    expect(result.status).toBe("RESOLVED");
  });

  it("propaga RAD-WF-020 ao tentar resolver ação delegada", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse(
        {
          error: {
            code: "RAD-WF-020",
            message: "Resolução desta HumanAction pertence a outro fluxo guardado",
            retryable: false,
          },
        },
        409,
      );
    const error = (await resolveHumanAction("ha_pub", "Enviado", fetchImpl).catch(
      (caught: unknown) => caught,
    )) as HumanActionsApiError;
    expect(error.code).toBe("RAD-WF-020");
  });
});
