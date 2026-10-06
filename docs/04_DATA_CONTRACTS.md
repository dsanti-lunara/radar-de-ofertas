# 04, Data Contracts

Todos os contratos externos devem ter `schema_version`.

## Browser Bridge, get job

O exemplo de etiqueta abaixo é sintático; não comprova que exista na conta. A revisão documental mantém `schema_version=1.0` para contratos ainda não implementados; schemas executáveis/versionamento final pertencem aos tickets, sem compatibilidade silenciosa de CHANNEL para GROUP.

Resposta conceitual:

```json
{
  "schema_version": "1.0",
  "job_id": "job_001",
  "type": "GENERATE_ML_AFFILIATE_LINK",
  "marketplace": "MERCADO_LIVRE",
  "payload": {
    "opportunity_id": "opp_001",
    "product_url": "https://...",
    "tracking_label": "rbtgoffer",
    "timeout_seconds": 60
  },
  "created_at": "..."
}
```

## Browser Bridge, job result

Sucesso:

```json
{
  "schema_version": "1.0",
  "status": "SUCCESS",
  "result": {
    "affiliate_url": "https://...",
    "source": "ML_LINK_GENERATOR"
  },
  "observed_at": "..."
}
```

Auth required:

```json
{
  "schema_version": "1.0",
  "status": "AUTH_REQUIRED",
  "error": {
    "code": "MARKETPLACE_SESSION_EXPIRED",
    "message": "Authentication required.",
    "retryable": false
  }
}
```

DOM failure:

```json
{
  "schema_version": "1.0",
  "status": "FAILED",
  "error": {
    "code": "AFFILIATE_UI_NOT_FOUND",
    "retryable": false
  }
}
```

## Manual capture

```json
{
  "schema_version": "1.0",
  "marketplace": "MERCADO_LIVRE",
  "source": "BROWSER_EXTENSION",
  "product": {
    "external_id": "MLB123",
    "title": "Produto",
    "url": "https://...",
    "category": "Perfumes"
  },
  "offer": {
    "current_price": "79.90",
    "original_price": "109.90",
    "sales_count": 2300,
    "seller": {"name": "Loja"}
  },
  "captured_at": "..."
}
```

Backend normaliza valores monetários. Extensão não executa regras de negócio.

### Manual capture, implementação (TKT-03)

Implementado em `POST /captures/manual` (`schema_version=1.0`) sobre a fronteira
pública. O contrato é estrito (`extra=forbid`): campos desconhecidos e nomes
sensíveis (`password`, `token`, `secret`, `cookie`, `authorization`, ...) são
recusados antes de qualquer escrita. Campos de texto são sanitizados (controle/
quebra de linha) e valores monetários exigem string decimal; `float` binário é
recusado. A URL deve ser `http(s)` absoluta e parâmetros de query sensíveis
(token/sessão) são recusados para não persistir credenciais.

`marketplace + external_id` é único: captura repetida reutiliza o
`MarketplaceProduct`/`Product` e acrescenta novo `Offer`, `RawCapture`,
`Evidence`, `DiscoveryEvent`, `Candidate` e `AuditEvent` na mesma transação.
`CapturedOffer` retorna ids distintos de Product, MarketplaceProduct, Offer e
Candidate.

```json
{
  "schema_version": "1.0",
  "status": "CAPTURED",
  "correlation_id": "cid-1",
  "candidate_id": "cand_...",
  "candidate_state": "NEW",
  "offer_id": "off_...",
  "product_id": "prd_...",
  "marketplace_product_id": "mkt_...",
  "raw_capture_id": "raw_...",
  "discovery_event_id": "disc_...",
  "audit_event_id": "aud_...",
  "marketplace": "MERCADO_LIVRE",
  "external_id": "MLB123",
  "source": "BROWSER_EXTENSION",
  "title": "Produto",
  "captured_at": "2026-10-05T12:00:00+00:00",
  "duplicate_identity": false
}
```

`GET /candidates/{candidate_id}` devolve o mesmo contrato (sem
`duplicate_identity`, que é um fato do momento da captura) e preserva o
`correlation_id` original da captura no corpo. Erros retornam
`{schema_version, status:"INVALID", correlation_id, error}` com códigos
`RAD-CAP-001..005` (ver `docs/ERROR_CATALOG.md`). `Evidence.confidence` fica
nula nesta etapa; a calibração pertence ao Confidence Engine (RDR-029). A
captura retorna também `price_observation_id`, a observação append-only criada ou
reutilizada.

## Price history, implementação (TKT-04)

Implementado em `GET /marketplace-products/{marketplace_product_id}/price-history`
(`schema_version=1.0`). Cada captura normalizada acrescenta uma
`PriceObservation` append-only na mesma transação do grafo de captura. A
identidade documentada é `(marketplace_product_id, source, observed_at)`; a
captura repetida com a mesma identidade reutiliza a observação existente, sem
sobrescrever o histórico e sem inventar novo preço. `price`/`original_price`/
`shipping_cost` são strings decimais (nunca float binário) e `observed_at` é
UTC. A série é retornada em ordem cronológica com proveniência.

```json
{
  "schema_version": "1.0",
  "status": "OK",
  "correlation_id": "cid-history",
  "marketplace_product_id": "mkt_...",
  "marketplace": "MERCADO_LIVRE",
  "external_id": "MLB123",
  "observation_count": 2,
  "observations": [
    {
      "price_observation_id": "obs_...",
      "price": "79.90",
      "original_price": "109.90",
      "shipping_cost": null,
      "source": "BROWSER_EXTENSION",
      "observed_at": "2026-10-05T12:00:00+00:00",
      "correlation_id": "cid-1",
      "raw_capture_id": "raw_..."
    }
  ]
}
```

MarketplaceProduct inexistente retorna 404 com `RAD-CAP-005`. `shipping_cost`
permanece `null` até existir captura de frete (ticket próprio); a observação não
calcula frete, desconto nem score.


## Classificação de categoria e Brand Fit, implementação (TKT-05, RDR-022, RDR-026)

A captura manual (`POST /captures/manual`) passou a aceitar `product.category`
opcional (categoria bruta do marketplace), sanitizada e persistida em
`MarketplaceProduct.raw_category` e em `Evidence` (`raw_category`); é um
acréscimo retrocompatível do contrato `schema_version=1.0` (campo opcional).

A classificação é exposta em
`GET /candidates/{candidate_id}/classification/{brand}?taxonomy_version=...`.
`brand` é `RADAR_BEAUTY` ou `CASA_EM_ORDEM`; `taxonomy_version` é opcional e,
quando informada, precisa coincidir com a taxonomia ativa (senão `RAD-CAP-007`).
O endpoint é read-only e determinístico: recomputa o resultado a partir do
Candidate e da taxonomia versionada, sem side effect comercial.

A taxonomia é configuração versionada e hasheada (AUT-045, AUT-207), carregada
de `config/brand-taxonomy.json` (opcional; `RADAR_TAXONOMY_FILE` força um
arquivo) sobre o baseline aprovado. Radar Beauty usa os valores aprovados do
SDD-05; Casa em Ordem tem prioridades aprovadas, mas Brand Fit sem calibração
aprovada, portanto devolve `brand_fit: null` com warning explícito em vez de
valor inventado. Categoria resolvida fora do escopo da marca produz o Hard Rule
`OUT_OF_SCOPE_CATEGORY` (SDD-05) no campo `hard_rules`, que precede score e IA.

```json
{
  "schema_version": "1.0",
  "status": "CLASSIFIED",
  "correlation_id": "cid-1",
  "candidate_id": "cand_...",
  "brand": "RADAR_BEAUTY",
  "raw_category": "Perfumes",
  "category": "perfume",
  "priority": 1,
  "brand_fit": 100,
  "calibrated": true,
  "calibration_required": false,
  "taxonomy_version": "brand-taxonomy-1.0",
  "taxonomy_hash": "sha256...",
  "warnings": [],
  "hard_rules": []
}
```

Lacunas são explícitas, nunca inventadas:

- `CATEGORY_NOT_PROVIDED`: Candidate sem categoria capturada;
- `CATEGORY_MAPPING_NOT_DEFINED`: categoria bruta sem alias na taxonomia;
- `BRAND_FIT_CALIBRATION_REQUIRED`: categoria em escopo sem Brand Fit aprovado.

Nesses casos `brand_fit`/`category`/`priority` ficam `null` quando aplicável,
`calibrated=false` e `calibration_required=true`. Erros usam o contrato
`{schema_version, status:"INVALID", correlation_id, error}` com `RAD-CAP-004`
(Candidate inexistente), `RAD-CAP-006` (brand desconhecida) e `RAD-CAP-007`
(versão divergente); taxonomia inválida bloqueia a criação da API com
`RAD-CFG-005`.


## Price Opportunity, implementação (TKT-06, RDR-023)

Implementado em `GET /candidates/{candidate_id}/price-opportunity`
(`schema_version=1.0`). O endpoint é read-only e idempotente: recomputa o
breakdown a partir do `Offer` persistido do Candidate e da série append-only de
`PriceObservation`, sem side effect comercial. Condições confirmadas que a
captura manual ainda não persiste podem ser informadas como query params
opcionais e são validadas antes do cálculo: `shipping_cost`, `coupon_state`
(`CONFIRMED`/`LIKELY`/`UNKNOWN`/`NOT_APPLICABLE`), `coupon_amount`, `coupon_code`,
`comparable_price` e `comparable_marketplace`.

```json
{
  "schema_version": "1.0",
  "status": "EVALUATED",
  "correlation_id": "cid-1",
  "candidate_id": "cand_...",
  "price_opportunity": 86,
  "fully_calibrated": false,
  "weight_covered": 85,
  "scoring_version": "price-opportunity-1.0",
  "as_of": "2026-10-05T18:00:00+00:00",
  "current_price": "80.00",
  "original_price": "150.00",
  "effective_price": null,
  "shipping_cost": null,
  "shipping_known": false,
  "coupon": {"code": null, "state": "UNKNOWN", "amount": null, "applied": false, "applied_amount": null},
  "history": {"observation_count": 2, "prior_observation_count": 1, "source": "30d", "window_days": 30},
  "components": [
    {"name": "historical_position", "weight": 45, "score": 100, "calibrated": true},
    {"name": "recent_price_drop", "weight": 20, "score": 90, "calibrated": true},
    {"name": "marketplace_comparison", "weight": 20, "score": 50, "calibrated": true},
    {"name": "coupon_final_price", "weight": 10, "score": null, "calibrated": false},
    {"name": "shipping_impact", "weight": 5, "score": null, "calibrated": false}
  ],
  "warnings": [
    {"code": "NO_MARKETPLACE_REFERENCE", "message": "..."},
    {"code": "UNKNOWN_SHIPPING", "message": "..."},
    {"code": "STRUCK_THROUGH_PRICE_NOT_PROOF", "message": "..."},
    {"code": "PRICE_OPPORTUNITY_CALIBRATION_REQUIRED", "message": "..."}
  ]
}
```

Lacunas são explícitas, nunca inventadas: `SHORT_PRICE_HISTORY` (histórico
insuficiente → neutro 50), `NO_PRICE_REFERENCE` (queda recente sem referência →
50), `NO_MARKETPLACE_REFERENCE` (comparação sem evidência comparável confiável →
50), `UNKNOWN_SHIPPING` (frete desconhecido → `effective_price=null`),
`COUPON_NOT_CONFIRMED` (cupom LIKELY/UNKNOWN/NOT_APPLICABLE não reduz o preço
efetivo), `STRUCK_THROUGH_PRICE_NOT_PROOF` (preço riscado não é prova) e
`PRICE_OPPORTUNITY_CALIBRATION_REQUIRED` (faixas de Coupon/Final Price e
Shipping Impact não calibradas no SDD). Erros usam o contrato
`{schema_version, status:"INVALID", correlation_id, error}` com `RAD-CAP-004`
(Candidate inexistente) e `RAD-CAP-008` (condição de avaliação inválida).

## Seller Quality, implementação (TKT-07, RDR-024)

Implementado em `GET /candidates/{candidate_id}/seller-quality`
(`schema_version=1.0`). O endpoint é read-only e idempotente: recomputa a
composição a partir dos fatos de vendedor do `Offer` persistido do Candidate e da
normalização versionada ativa, sem side effect comercial. Sinais que a captura
manual ainda não persiste (marketplace reputation e official/trusted status) podem
ser informados como query params opcionais e são validados antes do cálculo:
`reputation`, `rating`, `sales_count` e `trusted` (`true`/`false`). A origem de
cada sinal é reportada no componente (`persisted_offer` ou `evaluation_input`).

Os pesos macro são congelados (reputation 40%, rating 25%, sales 20%, trusted
15%). O SDD **não** calibra a normalização dos sinais, então ela é configuração
versionada e hasheada (`config/seller-quality.json`, opcional; use
`config/seller-quality.example.json`; `RADAR_SELLER_QUALITY_FILE` força um
arquivo). O baseline aprovado é intencionalmente vazio: um sinal sem mapeamento é
lacuna explícita, nunca constante inventada.

```json
{
  "schema_version": "1.0",
  "status": "EVALUATED",
  "correlation_id": "cid-1",
  "candidate_id": "cand_...",
  "seller": {"id": null, "name": "Loja"},
  "seller_quality": 100,
  "fully_calibrated": true,
  "weight_covered": 100,
  "scoring_version": "seller-quality-1.0",
  "normalization_version": "seller-quality-normalization-1.0",
  "normalization_hash": "sha256...",
  "components": [
    {"name": "marketplace_reputation", "weight": 40, "score": 100, "calibrated": true, "raw": "gold", "source": "evaluation_input", "reason": "ok"},
    {"name": "rating", "weight": 25, "score": 100, "calibrated": true, "raw": "4.6", "source": "evaluation_input", "reason": "ok"},
    {"name": "sales_history", "weight": 20, "score": 100, "calibrated": true, "raw": 2300, "source": "persisted_offer", "reason": "ok"},
    {"name": "trusted_status", "weight": 15, "score": 100, "calibrated": true, "raw": true, "source": "evaluation_input", "reason": "ok"}
  ],
  "warnings": []
}
```

Lacunas e dados ruins são explícitos, nunca inventados: `SELLER_QUALITY_MISSING_DATA`
(sinal ausente → `score=null`, não vira zero), `SELLER_QUALITY_INVALID_DATA`
(sinal inválido, ex.: rating/sales negativos → ignorado e reportado, ex. Evidence),
`SELLER_QUALITY_NORMALIZATION_NOT_DEFINED` (sinal sem mapeamento configurado →
`score=null` e calibração humana necessária) e `SELLER_QUALITY_CONTRADICTION`
(sinais sem identidade de vendedor). O `seller_quality` é parcial sobre os
componentes calibrados (`weight_covered`/`fully_calibrated`). Erros usam o
contrato `{schema_version, status:"INVALID", correlation_id, error}` com
`RAD-CAP-004` (Candidate inexistente) e `RAD-CAP-009` (sinal de avaliação
malformado); normalização inválida bloqueia a criação da API com `RAD-CFG-006`.

## Demand, implementação (TKT-08, RDR-025)

Implementado em `GET /candidates/{candidate_id}/demand` (`schema_version=1.0`). O
endpoint é read-only e idempotente: recomputa o breakdown determinístico a partir
da categoria bruta e do `sales_count` persistidos do Candidate e da normalização
versionada ativa, sem side effect comercial. A categoria canônica é resolvida com
a taxonomia versionada (TKT-05); sinais que a captura manual ainda não persiste
(`rating_count`, `trend`, `affiliate_portal`, `badges`) podem ser informados como
query params opcionais e são validados antes do cálculo. A origem de cada sinal é
reportada no componente (`persisted_offer` ou `evaluation_input`).

A normalização de Demand **evolui por categoria** e é configuração versionada e
hasheada (`config/demand.json`, opcional; use `config/demand.example.json`;
`RADAR_DEMAND_FILE` força um arquivo). Cada categoria define os pesos de
composição e o mapeamento de cada sinal para `0..100`; `sales_count`/`rating_count`
usam bandas, `trend`/`affiliate_portal`/`badges` usam mapas de label, e o
componente `badges` assume o score do badge reconhecido mais forte. O baseline
aprovado é intencionalmente vazio: categoria/sinal sem mapeamento é lacuna
explícita, nunca constante inventada. Nenhum passo chama IA.

```json
{
  "schema_version": "1.0",
  "status": "EVALUATED",
  "correlation_id": "cid-1",
  "candidate_id": "cand_...",
  "raw_category": "Perfumes",
  "category": "perfume",
  "demand": 100,
  "fully_calibrated": true,
  "weight_covered": 100,
  "scoring_version": "demand-1.0",
  "normalization_version": "demand-normalization-1.0",
  "normalization_hash": "sha256...",
  "components": [
    {"name": "sales_count", "weight": 40, "score": 100, "calibrated": true, "raw": 2300, "source": "persisted_offer", "reason": "ok"},
    {"name": "rating_count", "weight": 20, "score": 100, "calibrated": true, "raw": 600, "source": "evaluation_input", "reason": "ok"},
    {"name": "trend", "weight": 20, "score": 100, "calibrated": true, "raw": "rising", "source": "evaluation_input", "reason": "ok"},
    {"name": "affiliate_portal", "weight": 10, "score": 100, "calibrated": true, "raw": "featured", "source": "evaluation_input", "reason": "ok"},
    {"name": "badges", "weight": 10, "score": 100, "calibrated": true, "raw": ["best seller"], "source": "evaluation_input", "reason": "ok"}
  ],
  "warnings": []
}
```

Lacunas e dados ruins são explícitos, nunca inventados: `DEMAND_MISSING_DATA`
(sinal ausente → `score=null`, não vira zero, não inventa volume/conversões),
`DEMAND_INVALID_DATA` (sinal inválido, ex.: contagem negativa ou label vazio),
`DEMAND_NORMALIZATION_NOT_DEFINED` (categoria/sinal/badge sem mapeamento
configurado → `score=null` e calibração humana necessária) e
`DEMAND_CATEGORY_NOT_DEFINED` (categoria do Candidate não resolvida pela
taxonomia). O `demand` é parcial sobre os componentes calibrados
(`weight_covered`/`fully_calibrated`); configuração incompleta de categoria
resulta em `fully_calibrated=false`, nunca em resultado apresentado como
validado. Erros usam o contrato `{schema_version, status:"INVALID",
correlation_id, error}` com `RAD-CAP-004` (Candidate inexistente) e `RAD-CAP-010`
(sinal de avaliação malformado); normalização inválida bloqueia a criação da API
com `RAD-CFG-007`.

## Evaluation, implementação (TKT-09, RDR-016/027/028/029/030)

`POST /candidates/{candidate_id}/evaluations` (`schema_version=1.0`) compõe e
persiste uma Evaluation imutável a partir dos componentes normalizados das
dependências e da taxonomia ativa; `GET /candidates/{candidate_id}/evaluations`
retorna as evaluations armazenadas em ordem cronológica. Brand Fit é resolvido
pela taxonomia (TKT-05), não é informado pelo cliente; `price_opportunity`,
`seller_quality` e `demand` são as saídas dos TKT-06/07/08. A Monetization
(40/25/20/15) e a Confidence (30/25/20/15/10) são informadas como componentes.
Hard Rules declaradas (`hard_rules`) são validadas contra a lista do SDD-05.

```json
{
  "schema_version": "1.0",
  "brand": "RADAR_BEAUTY",
  "deal": {"price_opportunity": 100, "seller_quality": 100, "demand": 100},
  "monetization": {
    "estimated_commission": 97,
    "effective_commission_percent": 97,
    "conversion_evidence": 97,
    "extra_commission": 97
  },
  "confidence": {
    "source_reliability": 100,
    "freshness": 100,
    "completeness": 100,
    "price_history_depth": 100,
    "cross_validation": 100
  },
  "hard_rules": []
}
```

Resposta (`201`):

```json
{
  "schema_version": "1.0",
  "status": "EVALUATED",
  "correlation_id": "cid-1",
  "evaluation_id": "eval_...",
  "candidate_id": "cand_...",
  "brand": "RADAR_BEAUTY",
  "deal_score": "100.00",
  "monetization_score": 97,
  "confidence": "HIGH",
  "decision": "APPROVE",
  "auto_eligible": true,
  "passed_rules": ["INSUFFICIENT_REQUIRED_DATA", "OUT_OF_SCOPE_CATEGORY"],
  "failed_rules": [],
  "warnings": [],
  "breakdown": {"deal": {"scoring_version": "deal-1.0", "score": "100.00", "components": []}, "monetization": {}, "confidence": {}},
  "feature_snapshot": {"brand": "RADAR_BEAUTY", "deal": {"price_opportunity": 100, "seller_quality": 100, "demand": 100, "brand_fit": 100}},
  "scoring_version": "evaluation-1.0",
  "deal_scoring_version": "deal-1.0",
  "monetization_scoring_version": "monetization-1.0",
  "confidence_scoring_version": "confidence-1.0",
  "taxonomy_version": "brand-taxonomy-1.0",
  "taxonomy_hash": "sha256...",
  "audit_event_id": "aud_...",
  "created_at": "2026-10-05T12:00:00+00:00"
}
```

Hard Rules precedem score, IA, link e publicação (AUT-056): categoria fora de
escopo propaga `OUT_OF_SCOPE_CATEGORY` e componente obrigatório do Deal ausente
produz `INSUFFICIENT_REQUIRED_DATA`, ambos forçando `REJECT`. `deal_score` fica
`null` quando falta dado obrigatório, nunca `0`. A matriz Deal x Confidence segue
`docs/05_SCORING_ENGINE.md`; Monetization nunca eleva um Deal rejeitado.
`auto_eligible=true` só indica elegibilidade (Deal `>=80` + Confidence `HIGH` sem
Hard Rule) e **não** promove nenhuma capability para AUTO. A Evaluation é
append-only (triggers no banco) e cada versão preserva breakdown, feature
snapshot e scoring versions; reavaliar cria nova versão. Erros usam
`{schema_version, status:"INVALID", correlation_id, error}` com `RAD-CAP-004`
(Candidate inexistente) e `RAD-CAP-011` (componente fora de `0..100` ou Hard Rule
desconhecida).

## Purchase Source comparison, implementação (TKT-10, RDR-031)

`POST /candidates/{candidate_id}/purchase-source` (`schema_version=1.0`) compara a
oferta afiliada persistida do Candidate com as alternativas confiáveis informadas
e persiste uma decisão append-only com `Evidence`; `GET
/candidates/{candidate_id}/purchase-source` retorna as decisões em ordem
cronológica. A entrada carrega a equivalência de Product
(`product_equivalence_id`), as condições comparáveis (`conditions`), o frete/cupom
que a captura manual ainda não persiste (override validado) e as `alternatives`. A
comissão afiliada pode ser informada, mas é registrada como ignorada
(`commission_considered=false`) e nunca altera a decisão.

```json
{
  "schema_version": "1.0",
  "product_equivalence_id": "product-1",
  "conditions": {"variant": "100ml"},
  "shipping_cost": "0",
  "coupon_state": "CONFIRMED",
  "coupon_amount": "5",
  "affiliate_commission": "50",
  "alternatives": [
    {
      "source_id": "shopee:1",
      "marketplace": "SHOPEE",
      "price": "90",
      "shipping_cost": "0",
      "product_equivalence_id": "product-1",
      "conditions": {"variant": "100ml"}
    }
  ]
}
```

Resposta (`201`):

```json
{
  "schema_version": "1.0",
  "status": "DECIDED",
  "scoring_version": "purchase-source-1.0",
  "candidate_id": "cand_...",
  "decision": "REVIEW",
  "chosen_source_id": "candidate:cand_...",
  "best_alternative_source_id": "shopee:1",
  "substituted_source_id": null,
  "chosen_effective_price": "95",
  "alternative_effective_price": "90",
  "difference_percent": "5.5556",
  "material": false,
  "reference_difference_percent": "8",
  "commission_considered": false,
  "policy": {
    "policy_version": "purchase-source-policy-1.0",
    "policy_hash": "sha256...",
    "reference_difference_percent": "8",
    "on_material_difference": "REVIEW"
  },
  "sources": [
    {"source_id": "candidate:cand_...", "role": "chosen", "effective_price": "95", "product_equivalent": true, "conditions_comparable": true, "eligible": true, "reason": "chosen"},
    {"source_id": "shopee:1", "role": "alternative", "effective_price": "90", "product_equivalent": true, "conditions_comparable": true, "eligible": true, "reason": "ok"}
  ],
  "warnings": [],
  "as_of": "2026-10-05T12:00:00+00:00",
  "decision_id": "psd_...",
  "correlation_id": "cid-1",
  "audit_event_id": "aud_...",
  "created_at": "2026-10-05T12:00:00+00:00",
  "evidence": [
    {"evidence_id": "evd_...", "field": "chosen_effective_price", "value": "95", "source_type": "purchase_source_comparison"}
  ]
}
```

O preço efetivo é `preço + frete - cupom CONFIRMED` e só existe com frete
conhecido; cupom `LIKELY`/`UNKNOWN`/`NOT_APPLICABLE` nunca reduz o preço efetivo.
A diferença é o quanto a fonte afiliada está acima da melhor alternativa
equivalente; quando `> reference_difference_percent`, a decisão é a
`on_material_difference` da policy (`REVIEW` no baseline, `SUBSTITUTE` quando
configurado, com `substituted_source_id`). Lacunas explícitas:
`PURCHASE_SOURCE_PRODUCT_NOT_IDENTIFIED`, `PURCHASE_SOURCE_NOT_EQUIVALENT`,
`PURCHASE_SOURCE_CONDITIONS_NOT_COMPARABLE`, `PURCHASE_SOURCE_UNRELIABLE_PRICE`,
`PURCHASE_SOURCE_NO_RELIABLE_COMPARISON`,
`PURCHASE_SOURCE_MATERIAL_DIFFERENCE` e `PURCHASE_SOURCE_COMMISSION_IGNORED`.
Comissão não é entrada, então a decisão nunca favorece a fonte afiliada. A decisão
é append-only (triggers no banco) e cada gravação cria `Evidence` e um
`AuditEvent` `PURCHASE_SOURCE_DECIDED` na mesma transação. Erros usam
`{schema_version, status:"INVALID", correlation_id, error}` com `RAD-CAP-004`
(Candidate inexistente) e `RAD-CAP-012` (oferta/fonte inválida).

## Allowed Claims, implementação (TKT-11, RDR-032)

`GET /candidates/{candidate_id}/allowed-claims` (`schema_version=1.0`) produz,
de forma read-only e determinística, os claims comerciais sustentados por
`Evidence` para uma Evaluation imutável (`evaluation_id` opcional; sem ele vale a
Evaluation mais recente). O motor é `radar.domain.allowed_claims`, não usa IA e
nunca cria um claim sem suporte (AUT-063, AUT-076, AUT-077, AUT-292). O cupom
confirmado que a captura manual ainda não persiste pode ser informado como
condição validada (`coupon_state`/`coupon_amount`/`coupon_code`).

```json
{
  "schema_version": "1.0",
  "status": "OK",
  "engine_version": "allowed-claims-1.0",
  "candidate_id": "cand_...",
  "evaluation_id": "eval_...",
  "evaluation_decision": "APPROVE",
  "as_of": "2026-09-20T12:00:00+00:00",
  "claim_count": 4,
  "claims": [
    {
      "claim_type": "CURRENT_PRICE",
      "value": "80.00",
      "unit": "money",
      "evidence": [
        {
          "evidence_type": "offer",
          "reference_id": "off_...",
          "field": "current_price",
          "value": "80.00",
          "observed_at": "2026-09-20T12:00:00+00:00",
          "source": "BROWSER_EXTENSION",
          "correlation_id": "cid-1",
          "raw_capture_id": "raw_..."
        }
      ]
    },
    {
      "claim_type": "PREVIOUS_OBSERVED_PRICE",
      "value": "100.00",
      "unit": "money",
      "evidence": [
        {
          "evidence_type": "price_observation",
          "reference_id": "po_...",
          "field": "price",
          "value": "100.00",
          "observed_at": "2026-09-01T12:00:00+00:00",
          "source": "BROWSER_EXTENSION",
          "correlation_id": "cid-0",
          "raw_capture_id": "raw_0"
        }
      ]
    },
    {
      "claim_type": "PRICE_DROP_PERCENT",
      "value": "20.00",
      "unit": "percent",
      "evidence": [
        {"evidence_type": "offer", "reference_id": "off_...", "field": "current_price"},
        {"evidence_type": "price_observation", "reference_id": "po_...", "field": "price"}
      ]
    }
  ],
  "omitted_claims": [
    {"claim_type": "LOWEST_OBSERVED_30D", "reason_code": "HISTORY_INSUFFICIENT"}
  ],
  "forbidden_claims": [
    "BEST_PRICE_ON_THE_INTERNET",
    "LAST_UNITS",
    "WILL_SELL_OUT",
    "GUARANTEED_ORIGINAL",
    "PERSONAL_EXPERIENCE",
    "UNVERIFIED_COUPON"
  ],
  "warnings": [
    {"code": "LOWEST_OBSERVED_30D_HISTORY_INSUFFICIENT", "message": "...", "context": {}}
  ],
  "correlation_id": "cid-1"
}
```

Cada claim carrega a provenance da afirmação (`evidence_type`, `reference_id`,
`field`, `value`, `observed_at`, `source`, `correlation_id`, `raw_capture_id`).
`CURRENT_PRICE` e `SALES_COUNT` vêm do `Offer`; `PREVIOUS_OBSERVED_PRICE` e
`PRICE_DROP_PERCENT` exigem observação anterior própria; `LOWEST_OBSERVED_30D` só
é emitido quando o histórico cobre a janela de 30 dias e aparece em
`omitted_claims` com `HISTORY_INSUFFICIENT` quando não cobre;
`CONFIRMED_COUPON` só existe para cupom `CONFIRMED` (LIKELY/UNKNOWN/
NOT_APPLICABLE são omitidos com `COUPON_NOT_CONFIRMED`). O preço riscado
(`original_price`) nunca é referência nem claim (warning
`STRUCK_THROUGH_PRICE_NOT_PROOF`). Erros usam
`{schema_version, status:"INVALID", correlation_id, error}` com `RAD-CAP-004`
(Candidate inexistente), `RAD-CAP-013` (Evaluation inexistente) e `RAD-CAP-014`
(condição de cupom inválida). O resultado não tem store próprio: é função da
Evaluation imutável (RDR-016) e das evidências append-only (RDR-013).

## Repost/dedupe, implementação (TKT-12, RDR-033)

`POST /candidates/{candidate_id}/repost` (`schema_version=1.0`) aplica o guardrail
determinístico de dedupe/repost (`radar.domain.repost`, sem IA) ao `Offer`
persistido do Candidate, à Evaluation mais recente (Deal) e ao **histórico de
publicação fornecido pelo chamador** — um histórico *fake* enquanto o publisher
real não existe. `GET /candidates/{candidate_id}/repost` consulta as decisões
append-only. A policy versionada/hasheada (`config/repost.json`, opcional; use
`config/repost.example.json`; `RADAR_REPOST_FILE` força um arquivo) congela o
cooldown de referência (`72h`), a queda de preço (`>=10%`) e o piso de Deal forte
(`>=80`). O cupom/condição atual que a captura manual ainda não persiste pode ser
informado como condição validada; uma mudança material de cupom/condição só é
aceita com `Evidence`.

```json
{
  "schema_version": "1.0",
  "status": "DECIDED",
  "engine_version": "repost-1.0",
  "candidate_id": "cand_...",
  "decision": "BLOCKED",
  "reason": "DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE",
  "allowed": false,
  "current_price": "100.00",
  "material_changes": [],
  "publication": {
    "publication_id": "pub-1",
    "published_at": "2026-09-20T12:00:00+00:00",
    "price": "100.00",
    "coupon_state": "NOT_APPLICABLE",
    "coupon_amount": null,
    "coupon_code": null,
    "conditions": {}
  },
  "observed_price_drop_percent": "0.00",
  "cooldown_hours": 72,
  "cooldown_expires_at": "2026-09-23T12:00:00+00:00",
  "cooldown_expired": false,
  "deal_score": "91.00",
  "strong_deal_threshold": "80",
  "price_drop_threshold_percent": "10",
  "policy": {
    "policy_version": "repost-policy-1.0",
    "policy_hash": "...",
    "cooldown_hours": 72,
    "price_drop_percent": "10",
    "strong_deal_threshold": "80"
  },
  "warnings": [
    {"code": "REPOST_COOLDOWN_ACTIVE", "message": "...", "context": {}},
    {"code": "DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE", "message": "...", "context": {}}
  ],
  "as_of": "2026-09-21T12:00:00+00:00",
  "decision_id": "rpd_...",
  "correlation_id": "cid-1",
  "audit_event_id": "aud_...",
  "created_at": "2026-09-21T12:00:00+00:00",
  "evidence": [
    {"evidence_id": "evd_...", "field": "decision", "value": "BLOCKED", "source_type": "repost_review"}
  ]
}
```

Mudança irrelevante com cooldown ativo é bloqueada
(`DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE`); queda `>=10%`, novo cupom material ou
nova condição material **com** `Evidence` liberam o repost; cooldown vencido sem
mudança material ainda exige Deal forte, senão bloqueia com `DEAL_NOT_STRONG`.
Cupom/condição material sem `Evidence` gera `REPOST_COUPON_WITHOUT_EVIDENCE`/
`REPOST_CONDITION_WITHOUT_EVIDENCE` e não é tratado como material. Cada decisão
persiste `Evidence` e um `AuditEvent` `REPOST_DECIDED` na mesma transação. Erros
usam `RAD-CAP-004` (Candidate inexistente) e `RAD-CAP-015` (preço/publicação
inválidos); policy inválida bloqueia a API com `RAD-CFG-009`.

## Job persistente, claim/lease e locks, implementação (TKT-13, RDR-034/035/036)

O Workflow Engine enfileira trabalho pela fronteira pública
(`schema_version=1.0`). `POST /jobs` persiste um Job `PENDING` com `priority`,
`available_at`, `attempts`/`max_attempts` e o `correlation_id` do pipeline
(AUT-040, AUT-121); o Job é a unidade de trabalho e o seu estado (`JobStatus`) é
independente do estado de domínio (AUT-118) — um estado como `NEW` de Candidate é
recusado com `RAD-WF-006`, nunca convertido em estado de Job.

```json
{
  "schema_version": "1.0",
  "status": "PENDING",
  "job_id": "job_...",
  "type": "NORMALIZE_CAPTURE",
  "entity_type": "candidate",
  "entity_id": "cand_...",
  "priority": 9,
  "attempts": 0,
  "max_attempts": 3,
  "available_at": "2026-10-05T12:00:00+00:00",
  "locked_by": null,
  "locked_at": null,
  "lease_expires_at": null,
  "correlation_id": "cid-1",
  "payload": {"offer_id": "off_..."},
  "created_at": "2026-10-05T12:00:00+00:00",
  "updated_at": "2026-10-05T12:00:00+00:00"
}
```

`POST /jobs/claim` (`worker_id`, `lease_seconds` opcional) concede um **único**
lease ao worker: o claim é um `UPDATE` atômico com subquery e `RETURNING`, então
duas tentativas concorrentes nunca recebem o mesmo lease (o perdedor recebe
`RAD-WF-008` retryable). O claim incrementa `attempts` e grava
`locked_by`/`locked_at`/`lease_expires_at`; um Job `PENDING` só é claimável a
partir de `available_at` e um Job `CLAIMED`/`RUNNING` com lease expirado é
recuperável por outro worker (AUT-133, AUT-140). `POST /jobs/{id}/start` move
`CLAIMED → RUNNING` e `POST /jobs/{id}/complete` move `CLAIMED/RUNNING → SUCCESS`;
ambos exigem o lease do próprio worker e falham fechado com `RAD-WF-009` para
worker inválido ou lease expirado, de modo que um worker nunca confirma a
execução de outro. O `type` aceita apenas os Jobs V1 de `docs/08_WORKFLOW_ENGINE.md`.
`GET /jobs/{job_id}` consulta o resultado persistido (`RAD-WF-007` quando
inexistente).

```json
{
  "schema_version": "1.0",
  "status": "CLAIMED",
  "job_id": "job_...",
  "attempts": 1,
  "locked_by": "worker-a",
  "locked_at": "2026-10-05T12:00:00+00:00",
  "lease_expires_at": "2026-10-05T12:01:00+00:00",
  "correlation_id": "cid-1"
}
```

`POST /locks` / `DELETE /locks/{name}` implementam o lock lógico com expiração
(RDR-036). Um lock ativo de outro `owner` retorna `RAD-WF-004` (retryable); o
mesmo `owner` renova o TTL; um lock expirado pode ser retomado; só o owner
libera. Cada transição de Job e cada aquisição/liberação de lock grava um
`AuditEvent` (`JOB_ENQUEUED`, `JOB_CLAIMED`, `JOB_STARTED`, `JOB_SUCCEEDED`,
`LOCK_ACQUIRED`, `LOCK_RELEASED`) na mesma transação, sempre com o
`correlation_id` do pipeline. Retry/backoff, Dead Jobs, Scheduler e recuperação
pós-crash são tickets próprios e permanecem fora deste contrato.

## Retry, Dead Job e HumanAction, implementação (TKT-14, RDR-037/038/040)

`POST /jobs/{id}/fail` (`worker_id`, `error_code`) é reportado pelo worker que
detém o lease do job `CLAIMED`/`RUNNING`. O domínio classifica o `error_code`
(`TRANSIENT`, `PERMANENT`, `HUMAN_REQUIRED`; AUT-129) e o `error_code`
desconhecido falha fechado como `PERMANENT`. Worker inválido/lease expirado
retorna `RAD-WF-009`, estado inválido `RAD-WF-010` e `error_code`
ausente/inválido `RAD-WF-006`. O resultado é o contrato do job mais `failure` e
`human_action`:

```json
{
  "schema_version": "1.0",
  "status": "RETRY_WAIT",
  "job_id": "job_...",
  "attempts": 1,
  "max_attempts": 3,
  "available_at": "2026-10-05T12:00:30+00:00",
  "correlation_id": "cid-1",
  "failure": {
    "error_code": "RAD-WF-001",
    "failure_class": "TRANSIENT",
    "action": "RETRY_WAIT",
    "retryable": true,
    "reason": "RETRY_SCHEDULED",
    "delay_seconds": 30,
    "available_at": "2026-10-05T12:00:30+00:00",
    "human_action_type": null,
    "resolution_code": null
  },
  "human_action": null
}
```

`TRANSIENT` usa o backoff configurado (`config/retry-policy.json`, opcional; use
`config/retry-policy.example.json`; `RADAR_RETRY_FILE` força um arquivo; baseline
aprovado 30s/2m/10m/30m) enquanto `attempts < max_attempts`; ao esgotar, o job
vira `DEAD` e `failure.resolution_code` é `RAD-WF-003`. `PERMANENT` vira `FAILED`
sem retry. `HUMAN_REQUIRED` — incluindo `AUTH_REQUIRED` (`RAD-AI-001`,
`RAD-WA-001`, `RAD-SP-002`) — vira `DEAD` **sem** `RETRY_WAIT`, então não entra
em loop. `DEAD`/exaustão cria uma `HumanAction` auditável que referencia a
entidade existente sem recriá-la; o `attempts` não avança nessa transição.

```json
{
  "schema_version": "1.0",
  "human_action_id": "ha_...",
  "action_type": "DEAD_JOB_REVIEW",
  "status": "OPEN",
  "entity_type": "job",
  "entity_id": "job_...",
  "reason": "RETRIES_EXHAUSTED",
  "error_code": "RAD-WF-001",
  "impact": "...",
  "next_steps": "...",
  "correlation_id": "cid-1",
  "created_at": "2026-10-05T12:00:00+00:00",
  "updated_at": "2026-10-05T12:00:00+00:00"
}
```

`GET /human-actions` (filtro opcional `status=OPEN|RESOLVED`) e
`GET /human-actions/{id}` consultam as ações; inexistente retorna `RAD-WF-011`.
A resolução/mutação da ação pertence ao Human Actions center (RDR-063). Cada
transição grava `JOB_RETRY_SCHEDULED`/`JOB_FAILED`/`JOB_DEAD` e
`HUMAN_ACTION_CREATED` na mesma transação, sempre com o `correlation_id` do
pipeline. Policy de retry inválida bloqueia a API com `RAD-CFG-010`.

## AI Editorial Review input

```json
{
  "schema_version": "1.0",
  "task": "EDITORIAL_REVIEW",
  "brand": "RADAR_BEAUTY",
  "product": {},
  "offer": {},
  "evaluation": {
    "deal_score": 91,
    "monetization_score": 68,
    "confidence": "HIGH"
  },
  "allowed_claims": [],
  "warnings": []
}
```

## AI Editorial Review output

```json
{
  "decision": "APPROVE",
  "editorial_angle": "PRICE_OPPORTUNITY",
  "reason_codes": [
    "STRONG_BRAND_FIT",
    "GOOD_PRICE_CONTEXT"
  ],
  "warnings": []
}
```

Decisões permitidas:
- APPROVE
- REVIEW
- REJECT

A IA nunca retorna `AUTO_PUBLISH`.

## Content Generation output

```json
{
  "headline": "string",
  "body": "string",
  "cta": "string",
  "warnings": []
}
```

Affiliate URL, preço formatado e disclosure são adicionados pelo renderer determinístico.

## Error Contract

```json
{
  "error": {
    "code": "MARKETPLACE_SESSION_EXPIRED",
    "message": "Authentication required.",
    "retryable": false,
    "context": {
      "marketplace": "MERCADO_LIVRE"
    }
  }
}
```

## Enums principais

`Channel` identifica a plataforma; o destino WA V1 tem `destination_type=GROUP` e capability `PUBLISH_WHATSAPP_GROUP`. Não usar PUBLISH_WHATSAPP_CHANNEL como alias. Registro de destino/vínculo e receipt seguem o contrato abaixo; campos adicionais/migrations serão formalizados antes da implementação.

Marketplace:
- MERCADO_LIVRE
- SHOPEE

Brand:
- RADAR_BEAUTY
- CASA_EM_ORDEM

CanonicalCategory (taxonomia versionada, TKT-05):
- perfume, body_splash, hair, skincare, makeup, accessories (Radar Beauty);
- organization, kitchen, utilities, cleaning, laundry, bathroom, decor, smart_home (Casa em Ordem).

Channel:
- TELEGRAM
- WHATSAPP

Confidence:
- LOW
- MEDIUM
- HIGH

Decision:
- REJECT
- REVIEW
- APPROVE

AutomationMode:
- MANUAL
- SHADOW
- ASSISTED
- AUTO

## Configuration contract

Config operacional é JSON (`config/radar.json`, opcional; precedência `defaults < arquivo < env RADAR_*`) e validado por schema com `extra=forbid`. `radarctl config` e `GET /config` expõem o contrato sanitizado abaixo; secret *values* nunca aparecem, apenas referências por nome lógico (RDR-004, RDR-005). `config_hash` é SHA-256 do JSON canônico da configuração efetiva.

```json
{
  "schema_version": "1.0",
  "status": "VALID",
  "correlation_id": "...",
  "config": {
    "schema_version": "1.0",
    "environment": "development",
    "timezone": "America/Maceio",
    "log_level": "INFO",
    "automation_mode": "SHADOW",
    "data_dir": "/.../data",
    "database_url": "sqlite+pysqlite:////.../data/radar.db",
    "config_hash": "...",
    "source": "defaults",
    "secret_refs": ["telegram_bot_token"]
  },
  "secrets": {
    "declared": ["telegram_bot_token"],
    "status": {"telegram_bot_token": "present"}
  }
}
```

Config inválida bloqueia CLI/API com `RAD-CFG-001`/`RAD-CFG-002`. Secret ausente (`status=missing`) é reportado por nome e bloqueia somente a capability que o requer (`RAD-CFG-003`), sem persistir ou logar o valor.

## Idempotency

WhatsApp V1 usa grupos explicitamente cadastrados (`destination_type=GROUP`), pela capability `PUBLISH_WHATSAPP_GROUP`; `Channel.WHATSAPP` continua a plataforma. Channels não são a capability V1 deste fluxo. Nome de grupo e message-id não comprovam identidade persistente de destino.

Cada destino mantém identidade interna, marca, sandbox/produção e vínculo verificado ao grupo. O vínculo registra método/evidência, versão e revisão humana; somente pode habilitar envio após prova de identificação e reverificação segura. ID externo só é persistido se obtido por superfície permitida e validado; nunca inferido de storage/cookies/tokens. Sem essa prova, manter envio bloqueado e HumanAction/CAPABILITY_CONFLICT apenas para WA. Mudança de contexto, vínculo inválido ou grupo homônimo bloqueia antes do clique.

Serializer canônico define blocos e separadores de linha, aplica renderer determinístico e compara hash do conteúdo efetivamente preparado com o aprovado. Não usar `innerText`/`textContent` sem normalização especificada. Preview não autoriza envio. Preflight revalida destino, marca, conteúdo, oferta, compliance, nonce e aprovação da Publication imediatamente antes de um único Send.

`Enviada`/bubble/message marker são evidência de envio observado, não promessa de entrega/leitura. Receipt registra destino interno/vínculo, publication/revision, hash, correlation_id, observed_at e marcador externo quando disponível. Ausência de confirmação suficiente, timeout ou crash na janela de envio gera resultado desconhecido persistido, publicação suspensa e HumanAction, sem reenvio automático. Dedupe não depende de bubble: mensagens temporárias/reload/restore não apagam a proteção persistente (GRILL-002/003).

TrackingContext interno é separado da etiqueta externa ML. `tracking_label` aceita somente `[a-z0-9]{1,30}`; mapear por configuração explícita e auditável, com unicidade e validação de associação. Não transformar silenciosamente maiúsculas, separadores ou truncar para caber; criação/configuração de etiqueta continua humana. `rbtgoffer` é exemplo sintático, não etiqueta já existente/autorizada.

Gerar link/ID ML adiciona o produto a Minhas recomendações e é side effect: somente após Opportunity aprovada, autorização/gates e auditoria. Correlacionar input, etiqueta, tentativa e resultado; erro atual invalida seção de resultado anterior ainda visível. Preservar link literal retornado. Aceitar formato social legítimo somente quando produto destacado, catálogo/anúncio e contexto esperado coincidirem; outra recomendação no perfil não comprova o link. Short redirect, variante/vendedor, ausência da barra e recuperação permanecem aceites distintos.

Shopee tem três superfícies: API oficial para operações recorrentes documentadas; `affiliate.shopee.com.br` manual/diagnóstico; `shopee.com.br` captura pública assistida candidata. Proteção/indisponibilidade não autoriza alternar para browser como contorno. Sem geração operacional recorrente de links por extensão no portal.

Documentação Brasil confirmou POST GraphQL `https://open-api.affiliate.shopee.com.br/graphql`, `productOfferV2`, `shopeeOfferV2`, `shopOfferV2` e mutation `generateShortLink(originUrl, subIds)`; feeds/relatórios também foram documentados, mas sua existência não amplia analytics V1. AppID/Secret só no SecretsProvider. Assinar SHA256 de AppID + Timestamp + bytes JSON exatos + Secret, hex minúsculo; tolerância documentada de 10 minutos. Inconsistência Credential/Credentials precisa de validação oficial no SPIKE-02 antes de runtime.

HTTP 200 com errors/data parcial não é sucesso do contrato. Int64 cruza TypeScript/JSON sem perda (IDs como strings decimais); dinheiro/comissão usa Decimal a partir de strings. priceMin/Max é range de oferta, não preço de SKU escolhido/checkout. Paginação depende da operação; respeitar orçamento/backoff e classificar 10020 por reason sanitizado, 10030 como rate limit e 10035 como entitlement. Acesso da conta/API live permanece pendente; documentação não equivale a API_SUPPORTED nem ausência de acesso a NOT_SUPPORTED global.

Sub IDs preservam até cinco posições (brand, channel, content_type, category, referência interna), sem PII. Mapear/serializar valores explicitamente; comprimento por campo não foi comprovado e é gate para runtime correspondente. Retorno shortLink é literal, não sintetizado/editado. Mutation com resultado desconhecido não recebe retry cego; Core mantém idempotência/auditoria/reconciliação sem presumir chave de idempotência remota.

Captura pública registra source_url/observed_at, shop/item, campanha/categoria e contexto de variante/preço. Descobrir campanha vigente: IDs históricos de promoção não são configuração fixa. Loading difere de EMPTY; CHALLENGE após DOM inicial suspende parte afetada, exige intervenção humana e revalidação na retomada. E-SP-PUB-08 confirmou preço somente da opção 12L; opção preta/checkout/recorrência não foram validados. Cache/TTL/dedupe reduzem consultas, mas sem dado atual verificável por fonte permitida a revalidação pré-envio bloqueia publicação.

Operações de side effect recebem `idempotency_key`.

Exemplo:
`publish:{brand}:{channel}:{opportunity}:{revision}`

## Correlation ID

Toda execução originada de uma descoberta deve manter o mesmo `correlation_id` até Publication e post-publication events.
