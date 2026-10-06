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

## Implementação (TKT-09, RDR-016/027/028/029/030)

A `Evaluation` é imutável, versionada e append-only. Ela compõe os scores
determinísticos das dependências (Price Opportunity, Seller Quality, Demand e
Brand Fit) e aplica as Hard Rules antes de qualquer score, IA, link ou publicação
(AUT-056): dado obrigatório ausente produz a Hard Rule bloqueante
`INSUFFICIENT_REQUIRED_DATA` e categoria fora de escopo propaga
`OUT_OF_SCOPE_CATEGORY`. O Deal usa pesos congelados 40/25/20/15 e nunca recebe
comissão (AUT-051); a Monetization (40/25/20/15) só ordena oportunidades já
aceitáveis; a Confidence (30/25/20/15/10) é independente do Deal (AUT-054). Cada
Evaluation persiste `deal_score`, `monetization_score`, `confidence`, `decision`,
`passed_rules`/`failed_rules`, breakdown, feature snapshot e as scoring versions
(AUT-030, AUT-065), com triggers de banco que rejeitam `UPDATE`/`DELETE` e um
`AuditEvent` `EVALUATION_RECORDED` na mesma transação. A fronteira pública é
`POST /candidates/{candidate_id}/evaluations` e
`GET /candidates/{candidate_id}/evaluations`. Ver
`docs/05_SCORING_ENGINE.md`, `docs/04_DATA_CONTRACTS.md` e
`docs/10_PERSISTENCE_AND_RECOVERY.md`.

## Implementação (TKT-10, RDR-031)

A comparação de fonte de compra é um cálculo determinístico que recebe as ofertas
confiáveis e comparáveis do mesmo Product (equivalência positiva por
`product_equivalence_id` e condições comerciais iguais) e aplica o Purchase Source
Guardrail do SDD-05: quando a fonte afiliada escolhida custa materialmente mais
(`>8%` configurável) que a melhor alternativa confiável, a decisão é `REVIEW` ou
`SUBSTITUTE` conforme a policy versionada e hasheada. O preço efetivo usa apenas
frete conhecido e cupom `CONFIRMED`; oferta não identificada como equivalente,
condições diferentes ou sem preço efetivo confiável é lacuna explícita, nunca
comparação inventada. Comissão não é entrada e nunca favorece a seleção afiliada
(AUT-051, AUT-062). Cada decisão é persistida append-only com `Evidence`, um
`AuditEvent` `PURCHASE_SOURCE_DECIDED` na mesma transação e é consultável pela
`docs/04_DATA_CONTRACTS.md` e `docs/10_PERSISTENCE_AND_RECOVERY.md`.

## Implementação (TKT-11, RDR-032)

Os claims comerciais (`allowed_claims`) são produzidos deterministicamente pelo
backend, sem IA, a partir da `Evaluation` imutável e das evidências persistidas
(`Offer` e histórico append-only de `PriceObservation`), e expostos por
`GET /candidates/{candidate_id}/allowed-claims` com `schema_version` e provenance
por afirmação (`evidence_type`, `reference_id`, `raw_capture_id`,
`correlation_id`). `CURRENT_PRICE` e `SALES_COUNT` vêm do `Offer`;
`PREVIOUS_OBSERVED_PRICE` e `PRICE_DROP_PERCENT` exigem observação anterior
própria; `LOWEST_OBSERVED_30D` só é emitido quando o histórico cobre a janela de
30 dias (senão é omitido em `omitted_claims`, nunca inventado); `CONFIRMED_COUPON`
só existe para cupom `CONFIRMED` e os `forbidden_claims` do SDD-06 são explícitos.
O preço riscado não é prova. O resultado é read-only e determinístico, sem store
próprio: é função da `Evaluation` (RDR-016) e das evidências append-only
(RDR-013). A IA não cria nem altera claim (AUT-063, AUT-076, AUT-077, AUT-292).
Ver `docs/05_SCORING_ENGINE.md` e `docs/04_DATA_CONTRACTS.md`.

## Implementação (TKT-12, RDR-033)

O guardrail de dedupe/repost avalia se um Candidate pode voltar ao fluxo conforme
mudança material e histórico de publicação, sem IA. A entrada é o `Offer`
persistido do Candidate, a `Evaluation` imutável mais recente (Deal) e um
histórico de publicação **fornecido pelo chamador** — um histórico *fake* enquanto
o publisher real não existe (ticket de publicação). A policy versionada e
hasheada (`config/repost.json`, opcional) traz o cooldown de referência (72h), a
queda de preço (>=10%) e o piso de Deal forte (>=80). Mudança irrelevante com
cooldown ativo é bloqueada (`DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE`); queda >=10%,
novo cupom material ou nova condição material com `Evidence` liberam o repost; e
cooldown vencido sem mudança material ainda exige Deal forte, senão bloqueia com
`DEAL_NOT_STRONG`. Cupom/condição material sem `Evidence` é warning explícito e
não vira mudança material. Cada decisão é persistida append-only com `Evidence`,
um `AuditEvent` `REPOST_DECIDED` na mesma transação e é consultável por
`POST`/`GET /candidates/{candidate_id}/repost`. Ver
`docs/05_SCORING_ENGINE.md`, `docs/04_DATA_CONTRACTS.md` e
`docs/10_PERSISTENCE_AND_RECOVERY.md`.

## Implementação (TKT-13, RDR-034/035/036)

O `Job` é a unidade durável de trabalho do Workflow Engine, com `type`,
entidade, `priority`, `status`, `attempts`/`max_attempts`, `available_at`,
`correlation_id`, `payload` e lease (`locked_by`/`locked_at`/
`lease_expires_at`). O estado de Job (`JobStatus`) é um conceito próprio e
**independente** do estado de domínio (AUT-118): um Candidate `NEW` nunca é um
Job `NEW`. A fronteira pública (`POST /jobs`, `POST /jobs/claim`,
`POST /jobs/{id}/start`/`complete`, `GET /jobs/{id}`) persiste, reivindica com um
único lease expirável e confirma execução apenas pelo dono do lease; `Lock` é o
lock lógico separado com expiração (RDR-036). Cada transição grava um
`AuditEvent` com o Correlation ID do pipeline. Retry/backoff, Dead Jobs,
Scheduler e recuperação pós-crash pertencem a RDR-037/038/039/042 e são tickets
próprios (TKT-14, TKT-15 e TKT-18). Ver `docs/08_WORKFLOW_ENGINE.md` e
`docs/04_DATA_CONTRACTS.md`.

## Implementação (TKT-14, RDR-037/038/040)

A falha de um job é classificada em `TRANSIENT`, `PERMANENT` ou `HUMAN_REQUIRED`
(AUT-129) a partir do `error_code` estruturado; um código desconhecido falha
fechado como `PERMANENT`. `TRANSIENT` agenda `RETRY_WAIT` com o backoff
configurado (AUT-130) enquanto há orçamento de tentativas, depois vira `DEAD`;
`PERMANENT` vira `FAILED` sem retry; `HUMAN_REQUIRED`/`AUTH_REQUIRED` vira `DEAD`
imediatamente, sem loop (AUT-125). `DEAD`/exaustão materializa uma `HumanAction`
formal (AUT-126, AUT-244) que referencia a entidade existente sem recriá-la e
carrega motivo, impacto e próximos passos. A fronteira pública
(`POST /jobs/{id}/fail`, `GET /human-actions`, `GET /human-actions/{id}`)
demonstra o fluxo e mantém a ação auditável; a resolução da ação pertence a
RDR-063. Ver `docs/08_WORKFLOW_ENGINE.md`, `docs/04_DATA_CONTRACTS.md` e
`docs/10_PERSISTENCE_AND_RECOVERY.md`.

## Implementação (TKT-15, RDR-039)

O `Schedule` é a definição durável que o Scheduler usa para criar Jobs e é
separado do `Job`: ele guarda a cadência (`INTERVAL` com `interval_seconds`,
`CRON` com expressão de 5 campos ou `ON_DEMAND`), o `job_type`, a prioridade, o
`timezone` operacional, as quiet windows (AUT-143), o `lock_name` equivalente e o
cursor `last_tick_at`. O Scheduler **apenas cria Jobs** `PENDING` (AUT-117): um
tick nunca executa lógica de negócio e nunca confirma execução. Ticks perdidos são
coalescidos em um único Job (AUT-134) e um lock equivalente ativo ou uma quiet
window adiam o tick sem avançar o cursor. A fronteira pública (`POST /schedules`,
`GET /schedules`, `GET /schedules/{id}`, `POST /schedules/{id}/enable|disable`,
`POST /schedules/tick`, `POST /schedules/{id}/tick`) demonstra o comportamento e
cada tick grava `AuditEvent` com o Correlation ID do pipeline. A execução/renovação
do lock pelo worker e a recuperação pós-crash (RDR-042) são tickets próprios. Ver
`docs/08_WORKFLOW_ENGINE.md` e `docs/04_DATA_CONTRACTS.md`.
