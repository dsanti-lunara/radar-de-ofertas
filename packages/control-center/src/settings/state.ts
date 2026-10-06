/**
 * Estado assíncrono de Configurações (RDR-067).
 *
 * O loader devolve `loading`/`ready`/`unavailable` e nunca lança.
 */

import { fetchSettings, SettingsApiError, type FetchLike } from "./api";
import type { SettingsSnapshot } from "./contracts";

export type SettingsState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly settings: SettingsSnapshot }
  | { readonly kind: "unavailable"; readonly error: SettingsApiError };

function toApiError(error: unknown): SettingsApiError {
  if (error instanceof SettingsApiError) {
    return error;
  }
  return new SettingsApiError("SETTINGS_API_UNREACHABLE", "Control Center API inacessível");
}

export async function loadSettings(
  url: string,
  fetchImpl?: FetchLike,
): Promise<SettingsState> {
  try {
    const settings = await fetchSettings(url, fetchImpl);
    return { kind: "ready", settings };
  } catch (error) {
    return { kind: "unavailable", error: toApiError(error) };
  }
}
