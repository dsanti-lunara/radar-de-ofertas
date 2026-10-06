import { useCallback, useEffect, useState } from "react";

import { HealthStrip } from "./components/HealthStrip";
import { loadHomeHealth, type HomeHealthState } from "./health/poller";
import { describeHealthState, unknownStrip } from "./health/strip";
import type { ReviewSubmission } from "./review/HumanReviewForm";
import { ReviewApiError, submitHumanReview } from "./review/api";
import { ReviewWorkspace } from "./review/ReviewWorkspace";
import { loadDetail, loadInbox, type DetailState, type InboxState } from "./review/state";

const OVERVIEW_URL = "/health/overview";
const INBOX_URL = "/review/inbox";
const POLL_INTERVAL_MS = 10_000;

type View = "home" | "review";

export function App() {
  const [view, setView] = useState<View>("home");
  const [health, setHealth] = useState<HomeHealthState>({ kind: "loading" });
  const [inbox, setInbox] = useState<InboxState>({ kind: "loading" });
  const [detail, setDetail] = useState<DetailState>({ kind: "loading" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshHealth = useCallback(async () => {
    setHealth(await loadHomeHealth(OVERVIEW_URL));
  }, []);

  useEffect(() => {
    if (view !== "home") {
      return undefined;
    }
    void refreshHealth();
    const handle = window.setInterval(() => void refreshHealth(), POLL_INTERVAL_MS);
    return () => window.clearInterval(handle);
  }, [view, refreshHealth]);

  const refreshInbox = useCallback(async () => {
    setInbox(await loadInbox(INBOX_URL));
  }, []);

  useEffect(() => {
    if (view !== "review") {
      return undefined;
    }
    void refreshInbox();
    return undefined;
  }, [view, refreshInbox]);

  const selectCandidate = useCallback(async (candidateId: string) => {
    setSelectedId(candidateId);
    setDetail({ kind: "loading" });
    setFeedback(null);
    setError(null);
    setDetail(await loadDetail(candidateId));
  }, []);

  const submit = useCallback(
    async (input: ReviewSubmission) => {
      if (selectedId === null) {
        return;
      }
      setSubmitting(true);
      setFeedback(null);
      setError(null);
      try {
        const result = await submitHumanReview(
          `/candidates/${selectedId}/human-reviews`,
          input,
        );
        setFeedback(
          `Review registrada (${result.human_review.human_decision}). Envio comercial: ` +
            `${result.publication_authorized ? "autorizado" : "não autorizado"}.`,
        );
        setDetail(await loadDetail(selectedId));
        void refreshInbox();
      } catch (caught) {
        const apiError = caught instanceof ReviewApiError ? caught : null;
        setError(
          apiError === null
            ? "Falha ao registrar a review."
            : `${apiError.message}. ${apiError.action}`,
        );
      } finally {
        setSubmitting(false);
      }
    },
    [selectedId, refreshInbox],
  );

  const items = health.kind === "ready" ? health.overview.items : unknownStrip();
  const aggregate = health.kind === "ready" ? describeHealthState(health.overview.status) : undefined;

  return (
    <main className="control-center">
      <header className="control-center__header">
        <h1>Control Center</h1>
        <nav aria-label="Navegação principal">
          <button type="button" onClick={() => setView("home")} aria-current={view === "home"}>
            Visão geral
          </button>
          <button type="button" onClick={() => setView("review")} aria-current={view === "review"}>
            Oportunidades
          </button>
        </nav>
      </header>

      {view === "home" ? (
        <>
          <p>Visão geral da saúde do Radar (REST local, polling).</p>
          {aggregate === undefined ? null : (
            <p className={`aggregate aggregate--${aggregate.tone}`}>
              Estado geral: <strong>{aggregate.label}</strong>
            </p>
          )}

          {health.kind === "unavailable" ? (
            <p className="alert" role="alert">
              {health.error.message}. {health.error.action}
            </p>
          ) : null}

          <section aria-label="Health strip">
            <h2>Saúde</h2>
            <HealthStrip items={items} />
          </section>
        </>
      ) : (
        <ReviewWorkspace
          inbox={inbox}
          detail={detail}
          selectedId={selectedId}
          onSelect={(candidateId) => void selectCandidate(candidateId)}
          onSubmitReview={(input) => void submit(input)}
          submitting={submitting}
          feedback={feedback}
          error={error}
        />
      )}
    </main>
  );
}
