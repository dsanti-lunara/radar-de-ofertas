import { useCallback, useEffect, useState } from "react";

import { HealthStrip } from "./components/HealthStrip";
import { loadHomeHealth, type HomeHealthState } from "./health/poller";
import { describeHealthState, unknownStrip } from "./health/strip";

const OVERVIEW_URL = "/health/overview";
const POLL_INTERVAL_MS = 10_000;

export function App() {
  const [state, setState] = useState<HomeHealthState>({ kind: "loading" });

  const refresh = useCallback(async () => {
    const next = await loadHomeHealth(OVERVIEW_URL);
    setState(next);
  }, []);

  useEffect(() => {
    void refresh();
    const handle = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => window.clearInterval(handle);
  }, [refresh]);

  const items = state.kind === "ready" ? state.overview.items : unknownStrip();
  const aggregate = state.kind === "ready" ? describeHealthState(state.overview.status) : undefined;

  return (
    <main className="control-center">
      <header className="control-center__header">
        <h1>Control Center</h1>
        <p>Visão geral da saúde do Radar (REST local, polling).</p>
        {aggregate === undefined ? null : (
          <p className={`aggregate aggregate--${aggregate.tone}`}>
            Estado geral: <strong>{aggregate.label}</strong>
          </p>
        )}
      </header>

      {state.kind === "unavailable" ? (
        <p className="alert" role="alert">
          {state.error.message}. {state.error.action}
        </p>
      ) : null}

      <section aria-label="Health strip">
        <h2>Saúde</h2>
        <HealthStrip items={items} />
      </section>
    </main>
  );
}
