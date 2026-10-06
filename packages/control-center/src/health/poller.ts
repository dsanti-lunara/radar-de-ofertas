/**
 * Polling REST do Home health overview (RDR-057, AUT-394).
 *
 * A consulta é isolada da camada React para ser testável sem DOM: o hook usa o
 * mesmo `loadHomeHealth` e aplica o intervalo de polling.
 */

import { fetchHomeHealth, HealthPollError, type FetchLike } from "./api";
import type { HomeHealth } from "../contracts";

export type HomeHealthState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly overview: HomeHealth }
  | { readonly kind: "unavailable"; readonly error: HealthPollError };

export async function loadHomeHealth(
  url: string,
  fetchImpl?: FetchLike,
): Promise<HomeHealthState> {
  try {
    const overview = await fetchHomeHealth(url, fetchImpl);
    return { kind: "ready", overview };
  } catch (error) {
    return { kind: "unavailable", error: toHealthPollError(error) };
  }
}

function toHealthPollError(error: unknown): HealthPollError {
  if (error instanceof HealthPollError) {
    return error;
  }
  return new HealthPollError("CONTROL_CENTER_UNREACHABLE", "Control Center API inacessível");
}
