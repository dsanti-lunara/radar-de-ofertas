/**
 * Container polling de Configurações (RDR-067).
 *
 * Consulta `GET /settings` periodicamente e envia mudanças auditadas de modo
 * global e kill switch. As mudanças exigem confirmação no formulário.
 */

import { useCallback, useEffect, useState } from "react";

import { SettingsApiError, setGlobalMode, setStopExternalActions } from "./api";
import { SettingsWorkspace } from "./SettingsWorkspace";
import { loadSettings, type SettingsState } from "./state";

const SETTINGS_URL = "/settings";
const POLL_INTERVAL_MS = 15_000;

export function SettingsScreen() {
  const [state, setState] = useState<SettingsState>({ kind: "loading" });
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setState(await loadSettings(SETTINGS_URL));
  }, []);

  useEffect(() => {
    void refresh();
    const handle = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => window.clearInterval(handle);
  }, [refresh]);

  const change = useCallback(
    async (run: () => Promise<string>) => {
      setSubmitting(true);
      setFeedback(null);
      setError(null);
      try {
        setFeedback(await run());
        await refresh();
      } catch (caught) {
        const apiError = caught instanceof SettingsApiError ? caught : null;
        setError(
          apiError === null
            ? "Falha ao alterar a configuração."
            : `${apiError.message}. ${apiError.action}`,
        );
      } finally {
        setSubmitting(false);
      }
    },
    [refresh],
  );

  const applyMode = useCallback(
    (mode: string, reason: string) => {
      void change(async () => {
        const result = await setGlobalMode(mode, reason);
        return `Modo global agora é ${result.state.global_mode}.`;
      });
    },
    [change],
  );

  const applyStop = useCallback(
    (engaged: boolean, reason: string) => {
      void change(async () => {
        const result = await setStopExternalActions(engaged, reason);
        return engaged
          ? "STOP_EXTERNAL_ACTIONS ativo: side effects externos bloqueados."
          : `STOP_EXTERNAL_ACTIONS liberado (modo ${result.state.global_mode}).`;
      });
    },
    [change],
  );

  return (
    <SettingsWorkspace
      state={state}
      submitting={submitting}
      feedback={feedback}
      error={error}
      onSetMode={applyMode}
      onSetStop={applyStop}
    />
  );
}
