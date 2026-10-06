import { describe, expect, it } from "vitest";

import { HOME_HEALTH_CAPABILITIES, type HealthState } from "../contracts";
import { capabilityLabel, describeHealthState, unknownStrip } from "./strip";

describe("describeHealthState", () => {
  it("diferencia saudável, degradado, indisponível e desconhecido por texto", () => {
    const states: HealthState[] = ["HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"];
    const labels = states.map((state) => describeHealthState(state).label);
    expect(new Set(labels).size).toBe(4);
    expect(describeHealthState("HEALTHY").label).toBe("Saudável");
    expect(describeHealthState("UNHEALTHY").label).toBe("Indisponível");
    expect(describeHealthState("UNKNOWN").label).toBe("Desconhecido");
  });

  it("associa um tom distinto por estado (não depende só de cor)", () => {
    expect(describeHealthState("HEALTHY").tone).toBe("ok");
    expect(describeHealthState("DEGRADED").tone).toBe("warn");
    expect(describeHealthState("UNHEALTHY").tone).toBe("down");
    expect(describeHealthState("UNKNOWN").tone).toBe("unknown");
  });
});

describe("capabilityLabel", () => {
  it("traduz as capabilities canônicas", () => {
    expect(capabilityLabel("core")).toBe("Core");
    expect(capabilityLabel("mercado_livre")).toBe("Mercado Livre");
    expect(capabilityLabel("telegram")).toBe("Telegram");
  });

  it("preserva um slug desconhecido em vez de inventar rótulo", () => {
    expect(capabilityLabel("integração_nova")).toBe("integração_nova");
  });
});

describe("unknownStrip", () => {
  it("nunca apresenta uma capacidade sem dados como saudável", () => {
    const items = unknownStrip();
    expect(items.map((item) => item.capability)).toEqual([...HOME_HEALTH_CAPABILITIES]);
    expect(items.every((item) => item.state === "UNKNOWN")).toBe(true);
  });
});
