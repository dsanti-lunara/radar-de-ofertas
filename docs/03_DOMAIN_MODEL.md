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

Append-only e nunca sobrescrita.

- id;
- marketplace_product_id;
- price;
- original_price;
- shipping_cost;
- source;
- observed_at;
- correlation_id;
- raw_capture_id.

Identidade documentada: `(marketplace_product_id, source, observed_at)`. Captura
repetida com a mesma identidade reutiliza a observação; não cria duplicata nem
inventa novo preço. Timestamps em UTC e dinheiro em `Decimal`.

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

## Implementação (TKT-04, RDR-013)

Cada captura manual acrescenta uma `PriceObservation` append-only ao
`MarketplaceProduct` na mesma transação do grafo de captura (nunca em transação
separada). A identidade `(marketplace_product_id, source, observed_at)` é única
no banco: captura repetida com a mesma identidade reutiliza a linha existente,
sem sobrescrever a anterior e sem inventar preço novo. O histórico é consultável
por `GET /marketplace-products/{id}/price-history` com proveniência (`source`,
`observed_at`, `correlation_id`, `raw_capture_id`). `shipping_cost` permanece
nulo até existir captura de frete (ticket próprio). Ver
`docs/04_DATA_CONTRACTS.md` e `docs/10_PERSISTENCE_AND_RECOVERY.md`.

## Implementação (TKT-05, RDR-022/026)

A categoria bruta do marketplace é opcionalmente capturada em
`product.category` e persistida em `MarketplaceProduct.raw_category` (campo já
previsto no modelo). A taxonomia de marcas é configuração versionada e hasheada
(`Brand` × categoria canônica → prioridade e Brand Fit aprovado); a classificação
é exposta por
`GET /candidates/{candidate_id}/classification/{brand}?taxonomy_version=...`.
O resultado é read-only e determinístico (sem persistência própria): a Evaluation
versionada (RDR-016) é quem guarda o snapshot. Categoria resolvida fora do escopo
da marca gera o Hard Rule `OUT_OF_SCOPE_CATEGORY`; mapeamento ou calibração
ausente gera warning explícito e `brand_fit=null`, nunca valor inventado. Ver
`docs/05_SCORING_ENGINE.md` e `docs/04_DATA_CONTRACTS.md`.

## Implementação (TKT-06, RDR-023)

Price Opportunity é um cálculo determinístico e read-only sobre o `Offer`
persistido do Candidate, sua `PriceObservation` append-only (RDR-013) e as
condições confirmadas informadas na avaliação. O resultado é exposto por
`GET /candidates/{candidate_id}/price-opportunity` com breakdown versionado
(pesos 45/20/20/10/5), `effective_price` (somente com frete conhecido e cupom
CONFIRMED) e warnings para o Confidence Engine. O preço riscado não é prova de
vantagem. Histórico insuficiente e referência ausente usam neutro 50 com warning.
`Coupon / Final Price` e `Shipping Impact` permanecem lacunas explícitas de
calibração (`score=null`, `calibrated=false`) até decisão humana; o score
retornado é parcial sobre os componentes aprovados. A persistência própria do
snapshot pertence à Evaluation (RDR-016/TKT-09). Comparação entre marketplaces
usa evidência comparável verificada; a equivalência de Product é de RDR-031
(TKT-10), portanto sem referência o componente fica explícito e neutro. Ver
`docs/05_SCORING_ENGINE.md` e `docs/04_DATA_CONTRACTS.md`.

## Implementação (TKT-07, RDR-024)

Seller Quality é uma composição determinística e read-only sobre os fatos de
vendedor persistidos no `Offer`/`MarketplaceProduct` do Candidate e sobre os
sinais informados na avaliação. Os pesos macro são congelados (reputation 40%,
rating 25%, sales 20%, trusted 15%) e cada componente carrega a origem do sinal.
A normalização dos quatro sinais não está calibrada nos SDDs, então ela é
configuração versionada e hasheada (`config/seller-quality.json`, opcional;
`RADAR_SELLER_QUALITY_FILE` força um arquivo) com baseline aprovado vazio: sinal
sem mapeamento é lacuna explícita, nunca constante inventada. Dados ausentes não
viram zero; inválidos e contraditórios geram warnings/Evidence. O resultado é
exposto por `GET /candidates/{candidate_id}/seller-quality`; o snapshot
versionado pertence à Evaluation (RDR-016/TKT-09). Ver
`docs/05_SCORING_ENGINE.md` e `docs/04_DATA_CONTRACTS.md`.
