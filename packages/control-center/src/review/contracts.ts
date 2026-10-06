/**
 * Contratos do Opportunity Inbox/detail e da Human Review (RDR-058..RDR-060).
 *
 * Espelha os payloads versionados de `GET /review/inbox`,
 * `GET /review/candidates/{id}`, `GET /candidates/{id}/human-reviews` e
 * `POST /candidates/{id}/human-reviews`. A geração automática a partir do
 * OpenAPI substitui este espelho no ticket de contratos compartilhados.
 */

export const REVIEW_SCHEMA_VERSION = "1.0";

export type CandidateDecision = "APPROVE" | "REVIEW" | "REJECT";
export type HumanDecision = "APPROVE" | "REJECT" | "EDIT_CONTENT";

export interface AutomationView {
  readonly automation_mode: string;
  readonly global_mode: string;
  readonly stop_external_actions: boolean;
  readonly compliance_status: string;
  readonly publish_allowed: boolean;
  readonly publish_reason_code: string;
  readonly publish_message: string;
}

export interface InboxItem {
  readonly candidate_id: string;
  readonly candidate_state: string;
  readonly marketplace: string;
  readonly external_id: string;
  readonly title: string | null;
  readonly current_price: string | null;
  readonly original_price: string | null;
  readonly brand: string | null;
  readonly deal_score: string | null;
  readonly monetization_score: number | null;
  readonly confidence: string | null;
  readonly decision: string | null;
  readonly main_reason: string | null;
  readonly opportunity_id: string | null;
  readonly opportunity_state: string | null;
  readonly ai_decision: string | null;
  readonly human_decision: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ReviewInbox {
  readonly schema_version: string;
  readonly status: string;
  readonly correlation_id: string;
  readonly count: number;
  readonly items: readonly InboxItem[];
}

export interface EditedContent {
  readonly headline: string;
  readonly body: string;
  readonly cta: string;
}

export interface HumanReview {
  readonly human_review_id: string;
  readonly candidate_id: string;
  readonly ai_review_id: string | null;
  readonly ai_decision: string | null;
  readonly human_decision: HumanDecision;
  readonly reason: string;
  readonly note: string | null;
  readonly edited_content: EditedContent | null;
  readonly decision_matches_ai: boolean | null;
  readonly publication_authorized: boolean;
  readonly reviewed_at: string;
  readonly correlation_id: string;
}

export interface ReviewResult {
  readonly schema_version: string;
  readonly status: string;
  readonly human_review: HumanReview;
  readonly publication_authorized: boolean;
  readonly note: string;
  readonly automation: AutomationView;
  readonly correlation_id: string;
}

export interface TimelineEntry {
  readonly event_type: string;
  readonly entity_type: string;
  readonly entity_id: string;
  readonly source: string;
  readonly correlation_id: string;
  readonly recorded_at: string;
}

export interface PricePoint {
  readonly price: string;
  readonly observed_at: string;
  readonly source: string;
}

export interface EvidenceEntry {
  readonly field_name: string;
  readonly value: string;
  readonly source_type: string;
}

export interface EvaluationView {
  readonly decision: CandidateDecision | null;
  readonly deal_score: string | null;
  readonly monetization_score: number | null;
  readonly confidence: string | null;
  readonly warnings: readonly string[];
  readonly failed_rules: readonly string[];
}

export interface AiReviewView {
  readonly ai_review_id: string;
  readonly decision: string;
  readonly editorial_angle: string | null;
  readonly reason_codes: readonly string[];
  readonly knowledge_version: string;
  readonly prompt_version: string;
}

export interface DetailCandidate {
  readonly candidate_id: string;
  readonly state: string;
  readonly marketplace: string;
  readonly external_id: string;
  readonly title: string | null;
  readonly current_price: string | null;
  readonly seller_name: string | null;
}

export interface ReviewVersions {
  readonly scoring_version: string | null;
  readonly deal_scoring_version: string | null;
  readonly monetization_scoring_version: string | null;
  readonly confidence_scoring_version: string | null;
  readonly taxonomy_version: string | null;
  readonly ai_knowledge_version: string | null;
  readonly ai_prompt_version: string | null;
}

export interface ReviewDetail {
  readonly candidate: DetailCandidate;
  readonly evaluation: EvaluationView | null;
  readonly price_history: readonly PricePoint[];
  readonly evidence: readonly EvidenceEntry[];
  readonly ai_reviews: readonly AiReviewView[];
  readonly human_reviews: readonly HumanReview[];
  readonly opportunity: { readonly opportunity_id: string; readonly state: string } | null;
  readonly timeline: readonly TimelineEntry[];
  readonly versions: ReviewVersions;
  readonly automation: AutomationView | null;
}

export interface DetailEnvelope {
  readonly schema_version: string;
  readonly status: string;
  readonly candidate_id: string;
  readonly correlation_id: string;
  readonly detail: ReviewDetail;
}

export interface HumanReviewList {
  readonly schema_version: string;
  readonly status: string;
  readonly candidate_id: string;
  readonly count: number;
  readonly human_reviews: readonly HumanReview[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, field: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new Error(`campo deve ser um objeto: ${field}`);
  }
  return value;
}

function requireString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`campo obrigatório inválido: ${key}`);
  }
  return value;
}

function requireSchemaVersion(record: Record<string, unknown>): string {
  const value = requireString(record, "schema_version");
  if (value !== REVIEW_SCHEMA_VERSION) {
    throw new Error(`schema_version não suportado: ${value}`);
  }
  return value;
}

function optionalString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function optionalNumber(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function requireArray(record: Record<string, unknown>, key: string): readonly unknown[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw new Error(`campo deve ser uma lista: ${key}`);
  }
  return value;
}

function parseInboxItem(input: unknown, index: number): InboxItem {
  const record = requireRecord(input, `items[${index}]`);
  return {
    candidate_id: requireString(record, "candidate_id"),
    candidate_state: requireString(record, "candidate_state"),
    marketplace: requireString(record, "marketplace"),
    external_id: requireString(record, "external_id"),
    title: optionalString(record, "title"),
    current_price: optionalString(record, "current_price"),
    original_price: optionalString(record, "original_price"),
    brand: optionalString(record, "brand"),
    deal_score: optionalString(record, "deal_score"),
    monetization_score: optionalNumber(record, "monetization_score"),
    confidence: optionalString(record, "confidence"),
    decision: optionalString(record, "decision"),
    main_reason: optionalString(record, "main_reason"),
    opportunity_id: optionalString(record, "opportunity_id"),
    opportunity_state: optionalString(record, "opportunity_state"),
    ai_decision: optionalString(record, "ai_decision"),
    human_decision: optionalString(record, "human_decision"),
    created_at: requireString(record, "created_at"),
    updated_at: requireString(record, "updated_at"),
  };
}

export function parseReviewInbox(input: unknown): ReviewInbox {
  const record = requireRecord(input, "inbox");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    correlation_id: requireString(record, "correlation_id"),
    count: optionalNumber(record, "count") ?? 0,
    items: requireArray(record, "items").map((entry, index) => parseInboxItem(entry, index)),
  };
}

function parseEditedContent(input: unknown): EditedContent | null {
  if (input === null || input === undefined) {
    return null;
  }
  const record = requireRecord(input, "edited_content");
  return {
    headline: requireString(record, "headline"),
    body: requireString(record, "body"),
    cta: requireString(record, "cta"),
  };
}

function parseHumanReview(input: unknown): HumanReview {
  const record = requireRecord(input, "human_review");
  const decision = requireString(record, "human_decision");
  if (decision !== "APPROVE" && decision !== "REJECT" && decision !== "EDIT_CONTENT") {
    throw new Error(`human_decision inválida: ${decision}`);
  }
  return {
    human_review_id: requireString(record, "human_review_id"),
    candidate_id: requireString(record, "candidate_id"),
    ai_review_id: optionalString(record, "ai_review_id"),
    ai_decision: optionalString(record, "ai_decision"),
    human_decision: decision,
    reason: requireString(record, "reason"),
    note: optionalString(record, "note"),
    edited_content: parseEditedContent(record["edited_content"]),
    decision_matches_ai:
      typeof record["decision_matches_ai"] === "boolean"
        ? (record["decision_matches_ai"] as boolean)
        : null,
    publication_authorized: record["publication_authorized"] === true,
    reviewed_at: requireString(record, "reviewed_at"),
    correlation_id: requireString(record, "correlation_id"),
  };
}

function parseAutomation(input: unknown): AutomationView {
  const record = requireRecord(input, "automation");
  return {
    automation_mode: requireString(record, "automation_mode"),
    global_mode: requireString(record, "global_mode"),
    stop_external_actions: record["stop_external_actions"] === true,
    compliance_status: requireString(record, "compliance_status"),
    publish_allowed: record["publish_allowed"] === true,
    publish_reason_code: requireString(record, "publish_reason_code"),
    publish_message: requireString(record, "publish_message"),
  };
}

export function parseReviewResult(input: unknown): ReviewResult {
  const record = requireRecord(input, "review");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    human_review: parseHumanReview(record["human_review"]),
    publication_authorized: record["publication_authorized"] === true,
    note: optionalString(record, "note") ?? "",
    automation: parseAutomation(record["automation"]),
    correlation_id: requireString(record, "correlation_id"),
  };
}

function parseTimeline(input: readonly unknown[]): readonly TimelineEntry[] {
  return input.map((entry, index) => {
    const record = requireRecord(entry, `timeline[${index}]`);
    return {
      event_type: requireString(record, "event_type"),
      entity_type: requireString(record, "entity_type"),
      entity_id: requireString(record, "entity_id"),
      source: requireString(record, "source"),
      correlation_id: requireString(record, "correlation_id"),
      recorded_at: requireString(record, "recorded_at"),
    };
  });
}

function parseEvaluation(input: unknown): EvaluationView | null {
  if (input === null || input === undefined) {
    return null;
  }
  const record = requireRecord(input, "evaluation");
  return {
    decision: optionalString(record, "decision") as CandidateDecision | null,
    deal_score: optionalString(record, "deal_score"),
    monetization_score: optionalNumber(record, "monetization_score"),
    confidence: optionalString(record, "confidence"),
    warnings: requireArray(record, "warnings").map((warning) => {
      const item = requireRecord(warning, "warning");
      return requireString(item, "code");
    }),
    failed_rules: requireArray(record, "failed_rules").map((rule) => {
      const item = requireRecord(rule, "failed_rule");
      return requireString(item, "rule");
    }),
  };
}

function parseVersions(input: unknown): ReviewVersions {
  const record = requireRecord(input, "versions");
  return {
    scoring_version: optionalString(record, "scoring_version"),
    deal_scoring_version: optionalString(record, "deal_scoring_version"),
    monetization_scoring_version: optionalString(record, "monetization_scoring_version"),
    confidence_scoring_version: optionalString(record, "confidence_scoring_version"),
    taxonomy_version: optionalString(record, "taxonomy_version"),
    ai_knowledge_version: optionalString(record, "ai_knowledge_version"),
    ai_prompt_version: optionalString(record, "ai_prompt_version"),
  };
}

export function parseReviewDetail(input: unknown): DetailEnvelope {
  const record = requireRecord(input, "detail-envelope");
  const detail = requireRecord(record["detail"], "detail");
  const candidate = requireRecord(detail["candidate"], "candidate");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    candidate_id: requireString(record, "candidate_id"),
    correlation_id: requireString(record, "correlation_id"),
    detail: {
      candidate: {
        candidate_id: requireString(candidate, "candidate_id"),
        state: requireString(candidate, "state"),
        marketplace: requireString(candidate, "marketplace"),
        external_id: requireString(candidate, "external_id"),
        title: optionalString(candidate, "title"),
        current_price: optionalString(candidate, "current_price"),
        seller_name: optionalString(candidate, "seller_name"),
      },
      evaluation: parseEvaluation(detail["evaluation"]),
      price_history: requireArray(detail, "price_history").map((entry, index) => {
        const point = requireRecord(entry, `price_history[${index}]`);
        return {
          price: requireString(point, "price"),
          observed_at: requireString(point, "observed_at"),
          source: requireString(point, "source"),
        };
      }),
      evidence: requireArray(detail, "evidence").map((entry, index) => {
        const item = requireRecord(entry, `evidence[${index}]`);
        return {
          field_name: requireString(item, "field_name"),
          value: requireString(item, "value"),
          source_type: requireString(item, "source_type"),
        };
      }),
      ai_reviews: requireArray(detail, "ai_reviews").map((entry, index) => {
        const item = requireRecord(entry, `ai_reviews[${index}]`);
        return {
          ai_review_id: requireString(item, "ai_review_id"),
          decision: requireString(item, "decision"),
          editorial_angle: optionalString(item, "editorial_angle"),
          reason_codes: requireArray(item, "reason_codes").map((code) => String(code)),
          knowledge_version: requireString(item, "knowledge_version"),
          prompt_version: requireString(item, "prompt_version"),
        };
      }),
      human_reviews: requireArray(detail, "human_reviews").map((entry) =>
        parseHumanReview(entry),
      ),
      opportunity: parseOpportunity(detail["opportunity"]),
      timeline: parseTimeline(requireArray(detail, "timeline")),
      versions: parseVersions(detail["versions"]),
      automation:
        detail["automation"] === null || detail["automation"] === undefined
          ? null
          : parseAutomation(detail["automation"]),
    },
  };
}

function parseOpportunity(
  input: unknown,
): { readonly opportunity_id: string; readonly state: string } | null {
  if (input === null || input === undefined) {
    return null;
  }
  const record = requireRecord(input, "opportunity");
  return {
    opportunity_id: requireString(record, "opportunity_id"),
    state: requireString(record, "state"),
  };
}

export function parseHumanReviewList(input: unknown): HumanReviewList {
  const record = requireRecord(input, "human-review-list");
  return {
    schema_version: requireSchemaVersion(record),
    status: requireString(record, "status"),
    candidate_id: requireString(record, "candidate_id"),
    count: optionalNumber(record, "count") ?? 0,
    human_reviews: requireArray(record, "human_reviews").map((entry) =>
      parseHumanReview(entry),
    ),
  };
}
