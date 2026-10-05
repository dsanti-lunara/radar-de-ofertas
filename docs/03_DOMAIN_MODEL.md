# 03, Domain Model

## Regra principal

Não usar `Product` como entidade universal para todo o pipeline.

```text
Product
→ MarketplaceProduct
→ Offer
→ Candidate
→ Evaluation
→ Opportunity
→ AffiliateLink
→ ContentGeneration
→ Publication
```

## Entidades

### Product

Representa o produto conceitual.

Campos mínimos:
- id;
- canonical_name;
- brand;
- model;
- category;
- subcategory;
- attributes;
- timestamps.

### MarketplaceProduct

Representa o mesmo produto dentro de um marketplace.

- product_id opcional no início;
- marketplace;
- external_id;
- URL;
- title;
- seller_id;
- raw_category;
- first_seen_at;
- last_seen_at.

Constraint importante:
`marketplace + external_id` deve ser único.

### Offer

Condição comercial capturada naquele momento.

Inclui:
- current/original price;
- discount;
- seller;
- rating;
- sales;
- stock;
- shipping;
- coupon;
- affiliate commission;
- captured_at.

### PriceObservation

Append-only.

- marketplace_product_id;
- price;
- original_price;
- shipping_cost;
- source;
- observed_at.

### Evidence

Proveniência de um fato.

- entity_type/entity_id;
- field;
- value;
- source_type;
- source_url;
- captured_at;
- confidence;
- raw_reference.

### RawCapture

Payload estruturado recebido antes da normalização.

Não guardar HTML completo por padrão.

### DiscoveryEvent

Registra origem da descoberta:
- ML_TRENDS;
- ML_SEARCH;
- ML_AFFILIATE_PORTAL;
- SHOPEE_AFFILIATE_PRODUCT;
- SHOPEE_CAMPAIGN;
- BROWSER_EXTENSION;
- MANUAL_URL.

### Candidate

Significa que uma Offer entrou no pipeline de avaliação.

Estados conceituais:
- NEW
- NORMALIZED
- FILTERED
- SCORING
- AI_REVIEW
- APPROVED
- REJECTED
- EXPIRED
- ERROR

### Evaluation

Imutável/versionada.

- deal_score;
- monetization_score;
- confidence;
- decision;
- passed/failed rules;
- feature snapshot;
- score breakdown;
- scoring_version.

### AIReview

Separada de Evaluation.

- provider;
- model;
- knowledge_version;
- prompt_version;
- decision;
- editorial_angle;
- reason_codes;
- warnings.

### HumanReview

Usada em Shadow/Assisted.

Guarda:
- ai_decision;
- human_decision;
- reason;
- reviewed_at.

### Opportunity

Só nasce depois de aprovação.

Estados:
- READY
- LINK_PENDING
- LINK_READY
- CONTENT_PENDING
- READY_TO_PUBLISH
- PUBLISHED
- EXPIRED
- CANCELLED

### AffiliateLink

Entidade própria e auditável.

- opportunity_id;
- marketplace;
- original_url;
- affiliate_url;
- generation_method;
- tracking;
- status;
- timestamps.

### ContentGeneration

Separada de Publication.

- opportunity_id;
- brand;
- channel;
- headline/body/cta;
- generation_version;
- knowledge_version;
- status.

### Publication

Representa side effect de envio.

- opportunity_id;
- content_generation_id;
- affiliate_link_id;
- channel;
- destination_id;
- external_message_id;
- published_price;
- status;
- published_at.

### PublicationEvent

Append-only:
- CREATED
- PUBLISHED
- PRICE_CHANGED
- EXPIRED
- MESSAGE_EDITED
- LINK_INVALID
- ERROR

### ExtensionJob / BrowserJob

Unidade operacional do Browser Bridge.

Estados:
- PENDING
- CLAIMED
- RUNNING
- SUCCESS
- FAILED
- AUTH_REQUIRED
- CANCELLED

### HumanAction

Toda intervenção necessária converge aqui:
- AUTHENTICATE_MARKETPLACE
- REVIEW_CANDIDATE
- REVIEW_PUBLICATION
- RESOLVE_DATA_CONFLICT
- BROWSER_DOM_CHANGED
- RESTORE_AI_AUTH
- BACKUP_FAILURE
- DEAD_JOB_REVIEW

### AutomationPolicy

Configura autonomia por:
`brand × marketplace × channel × capability`

Modos:
- MANUAL
- SHADOW
- ASSISTED
- AUTO

### KnowledgePack

Versiona contexto editorial/runtime da IA.

### ChannelCompliancePolicy

Versiona permissão por:
`marketplace × channel`

Estados:
- ACTIVE
- REVIEW_REQUIRED
- BLOCKED
- UNKNOWN

## Implementação (TKT-03, RDR-011/012/014/015/021)

Uma captura manual materializa, em uma única transação: `Product` e
`MarketplaceProduct` (identidade única por `marketplace + external_id`; captura
repetida reutiliza ambos), um novo `Offer` (condição comercial do momento),
`RawCapture` sanitizado (payload estruturado, sem HTML), `Evidence` por fato
observado, `DiscoveryEvent` (origem) e `Candidate` (`state=NEW`), além de
`AuditEvent` append-only com fonte e Correlation ID. `Evidence.confidence` fica
nula até o Confidence Engine (RDR-029). Implementação pública em
`POST /captures/manual` e `GET /candidates/{id}`; ver `docs/04_DATA_CONTRACTS.md`.
