# 05, Scoring Engine

## Saídas independentes

```text
Deal Score            0..100
Monetization Score    0..100
Confidence            LOW | MEDIUM | HIGH
```

Comissão nunca entra no Deal Score.

## Deal Score

Pesos macro congelados:

```text
Price Opportunity   40%
Seller Quality      25%
Demand              20%
Brand Fit           15%
```

Fórmula:

`Deal = Price*0.40 + Seller*0.25 + Demand*0.20 + BrandFit*0.15`

Guardar score decimal e breakdown.

### Price Opportunity

Composição inicial:

```text
Historical Position      45%
Recent Price Drop        20%
Marketplace Comparison   20%
Coupon / Final Price     10%
Shipping Impact           5%
```

Prioridade de histórico:
`30d > lifetime > 7d`

Historical Position inicial:
- <=5% acima do mínimo: 100
- <=10%: 90
- <=20%: 75
- <=30%: 55
- <=40%: 35
- >40%: 10
- novo mínimo observado: 100
- histórico insuficiente: neutro, 50, com penalidade de Confidence

Recent Price Drop:
- >=25%: 100
- 20-24.99%: 90
- 15-19.99%: 80
- 10-14.99%: 65
- 5-9.99%: 45
- <5%: 20
- sem referência: 50

Marketplace comparison:
- melhor preço conhecido: 100
- até 3% acima: 90
- até 7%: 75
- até 12%: 55
- até 20%: 30
- >20%: 10

Usar `effective_price = preço + frete - cupom confirmado` quando dados forem confiáveis.

### Coupon

Estados:
- CONFIRMED
- LIKELY
- UNKNOWN
- NOT_APPLICABLE

Somente CONFIRMED entra integralmente em claim/preço final.

Implementação (TKT-06, RDR-023): o cálculo é exposto por
`GET /candidates/{candidate_id}/price-opportunity` (`schema_version=1.0`) e usa
o histórico append-only (RDR-013) mais as condições confirmadas informadas na
avaliação. As faixas de Historical Position, Recent Price Drop e Marketplace
Comparison seguem exatamente a tabela acima; histórico insuficiente e ausência de
referência usam o neutro 50 com warning (`SHORT_PRICE_HISTORY`,
`NO_PRICE_REFERENCE`, `NO_MARKETPLACE_REFERENCE`) para o Confidence Engine
(RDR-029). `effective_price = preço + frete - cupom confirmado` só é calculado
quando o frete é conhecido; cupom LIKELY/UNKNOWN/NOT_APPLICABLE nunca reduz o
preço efetivo nem vira claim. O preço riscado (`original_price`) não é prova de
vantagem e nunca é usado como referência.

O SDD fixa os pesos 45/20/20/10/5 mas **não** calibra faixas de pontuação para
`Coupon / Final Price` e `Shipping Impact`; esses dois componentes são reportados
como lacuna explícita (`score=null`, `calibrated=false`,
`PRICE_OPPORTUNITY_CALIBRATION_REQUIRED`) em vez de valor inventado. O
`price_opportunity` retornado é um score parcial calculado somente sobre os
componentes aprovados (peso coberto 85) e carrega `fully_calibrated=false`; a
calibração completa dos dois componentes exige decisão humana.

### Seller Quality

Composição inicial:
- marketplace reputation 40%;
- rating 25%;
- sales history 20%;
- official/trusted status 15%.

Dados ausentes não viram zero automaticamente. Afetam Confidence.

Implementação (TKT-07, RDR-024): a composição é um cálculo determinístico e
read-only exposto por `GET /candidates/{candidate_id}/seller-quality`
(`schema_version=1.0`). Os pesos 40/25/20/15 são congelados. O SDD **não**
calibra a normalização dos quatro sinais, portanto a normalização é configuração
versionada e hasheada (`config/seller-quality.json`, opcional; baseline aprovado
vazio) que mapeia cada sinal bruto para 0..100; a lacuna é explícita e não recebe
constante inventada. Sinal ausente (`SELLER_QUALITY_MISSING_DATA`), sinal
inválido (`SELLER_QUALITY_INVALID_DATA`), sinal sem normalização definida
(`SELLER_QUALITY_NORMALIZATION_NOT_DEFINED`) e sinal contraditório
(`SELLER_QUALITY_CONTRADICTION`) geram warnings para o Confidence Engine
(RDR-029). O `seller_quality` retornado é parcial sobre os componentes
calibrados (`weight_covered`, `fully_calibrated`) e cada componente carrega a
origem do sinal; o snapshot versionado pertence à Evaluation (RDR-016/TKT-09).

### Demand

Pode usar:
- sales_count;
- rating_count;
- trend signal;
- affiliate portal signal;
- badges.

Normalização deve evoluir por categoria.

Implementação (TKT-08, RDR-025): a avaliação é um cálculo determinístico e
read-only exposto por `GET /candidates/{candidate_id}/demand`
(`schema_version=1.0`). A categoria canônica do Candidate é resolvida pela
taxonomia versionada (RDR-022) a partir da categoria bruta capturada e a
normalização é configuração versionada e hasheada por categoria
(`config/demand.json`, opcional; baseline aprovado vazio), sem IA em nenhum
passo (AUT-031). Cada componente (`sales_count`, `rating_count`, `trend`,
`affiliate_portal`, `badges`) registra a origem do sinal (`persisted_offer` ou
`evaluation_input`) e o `raw` lido. O SDD **não** calibra nem o mapeamento nem os
pesos de composição, portanto eles vêm da configuração: sinal sem
mapeamento/peso na categoria é lacuna explícita (`score=null`,
`DEMAND_NORMALIZATION_NOT_DEFINED`) e o `demand` retornado é parcial sobre os
componentes calibrados (`weight_covered`, `fully_calibrated`). Ausência de dado
não vira zero: sinal ausente (`DEMAND_MISSING_DATA`), inválido
(`DEMAND_INVALID_DATA`) ou categoria não resolvida (`DEMAND_CATEGORY_NOT_DEFINED`)
geram warnings para o Confidence Engine (RDR-029), sem inventar volume ou
conversões. Configuração de categoria incompleta resulta em
`fully_calibrated=false` e nunca é apresentada como validada. O snapshot
versionado pertence à Evaluation (RDR-016/TKT-09).

### Brand Fit

Radar Beauty, base inicial:
- perfume: 100
- body_splash: 100
- hair: 85
- skincare: 85
- makeup: 65
- accessories: 60

Casa em Ordem deve refletir suas prioridades de organização/cozinha/utilidades primeiro.

Implementação (TKT-05, RDR-022, RDR-026): a taxonomia de marcas é configuração
versionada e hasheada (`config/brand-taxonomy.json`, opcional) sobre um baseline
aprovado. O baseline usa exatamente os valores de Radar Beauty acima; as
prioridades de Casa em Ordem vêm do SDD-01, mas o Brand Fit de Casa em Ordem
**não** está calibrado nos SDDs. A classificação reporta a lacuna
(`BRAND_FIT_CALIBRATION_REQUIRED`, `brand_fit=null`, `calibrated=false`) em vez
de inventar valor. Categoria resolvida fora do escopo da marca produz o Hard Rule
`OUT_OF_SCOPE_CATEGORY` no contrato de avaliação, antes de score e IA.

## Threshold inicial

```text
0..59    REJECT
60..79   REVIEW
80..100  STRONG_CANDIDATE
```

Decision Matrix:

| Deal | Confidence | Resultado |
|---|---|---|
| <60 | qualquer | REJECT |
| 60-79 | LOW | REJECT |
| 60-79 | MEDIUM/HIGH | REVIEW |
| >=80 | LOW | REVIEW |
| >=80 | MEDIUM | APPROVE |
| >=80 | HIGH | APPROVE, AUTO elegível conforme policy |

Hard Rules sempre prevalecem.

## Monetization Score

Pesos:
- comissão estimada R$: 40%
- comissão efetiva %: 25%
- evidência de clique/conversão: 20%
- comissão extra/campanha: 15%

Conversion Evidence começa neutro, 50, até haver dados próprios.

Monetization Score:
- nunca aprova oferta rejeitada;
- pode ordenar oportunidades já aceitáveis.

## Confidence

Componentes:
- Source Reliability 30%
- Freshness 25%
- Completeness 20%
- Price History Depth 15%
- Cross Validation 10%

Faixas iniciais:
- 0..49 LOW
- 50..79 MEDIUM
- 80..100 HIGH

Source Reliability inicial:
- official marketplace API: 100
- official affiliate API: 100
- authenticated affiliate portal: 95
- public marketplace page: 90
- browser extraction: 85
- manual input: 70
- unknown third party: 30

Freshness, preço/estoque/cupom:
- <=5min 100
- <=15min 95
- <=30min 85
- <=1h 70
- <=3h 45
- <=6h 25
- >6h 10

Price History Depth considera número de observações e janela temporal.

## Hard Rules

Exemplos:
- OUT_OF_SCOPE_CATEGORY
- OUT_OF_STOCK
- INVALID_PRICE
- INVALID_URL
- BLACKLISTED_SELLER
- INVALID_AFFILIATE_DESTINATION
- INSUFFICIENT_REQUIRED_DATA
- DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE
- COMPLIANCE_BLOCK

## Soft Rules

Exemplos:
- SHORT_PRICE_HISTORY
- UNKNOWN_SHIPPING
- LOW_RATING_COUNT
- NEW_PRODUCT
- COUPON_NOT_CONFIRMED

## Purchase Source Guardrail

Se uma opção afiliada escolhida custar materialmente mais que outra opção confiável para o mesmo Product, deve ir para REVIEW ou ser substituída.

Threshold inicial de referência: diferença >8%, configurável.

Implementação (TKT-10, RDR-031): a comparação é exposta por
`POST /candidates/{candidate_id}/purchase-source` (`schema_version=1.0`) e
`GET /candidates/{candidate_id}/purchase-source`. O domínio é determinístico e
livre de framework (`radar.domain.purchase_source`) e a policy é configuração
versionada e hasheada (`config/purchase-source.json`, opcional; use
`config/purchase-source.example.json`; `RADAR_PURCHASE_SOURCE_FILE` força um
arquivo) com o threshold congelado (`8`, diferença estritamente `>`) e a ação
`REVIEW`/`SUBSTITUTE`. O baseline aprovado usa `REVIEW`; `SUBSTITUTE` é uma
configuração explícita do operador e nenhuma capability é promovida para AUTO
(AUT-257).

A comparação só usa fontes **confiáveis e comparáveis**: equivalência de Product
positivamente identificada (`PURCHASE_SOURCE_NOT_EQUIVALENT`,
`PURCHASE_SOURCE_PRODUCT_NOT_IDENTIFIED`), condições comerciais iguais
(`PURCHASE_SOURCE_CONDITIONS_NOT_COMPARABLE`) e preço efetivo
`preço + frete - cupom CONFIRMED` (`PURCHASE_SOURCE_UNRELIABLE_PRICE` quando o
frete é desconhecido). Ausência de referência confiável é lacuna explícita
(`PURCHASE_SOURCE_NO_RELIABLE_COMPARISON`), nunca comparação inventada.
**Comissão nunca é entrada**: a decisão é idêntica para qualquer comissão da fonte
afiliada (`commission_considered=false`, `PURCHASE_SOURCE_COMMISSION_IGNORED`),
garantindo que a monetização não contorne o guardrail (AUT-051, AUT-062). Cada
decisão é persistida append-only com `Evidence` e um `AuditEvent`
`PURCHASE_SOURCE_DECIDED` na mesma transação. Ver
`docs/04_DATA_CONTRACTS.md` e `docs/10_PERSISTENCE_AND_RECOVERY.md`.

## Opportunity Priority

Somente ordenação operacional:

```text
Deal * 0.55
+ Monetization * 0.25
+ Freshness * 0.15
+ Strategic Bonus * 0.05
```

Não altera Deal Score.

## Repost

Padrão:
- cooldown inicial 72h;
- não repostar mudança irrelevante;
- liberar quando queda desde publicação >=10%, novo cupom material, condição material nova ou cooldown vencido e Deal continuar forte.

## Allowed Claims

Claims comerciais são produzidos pelo backend.

Exemplos:
- CURRENT_PRICE
- PREVIOUS_OBSERVED_PRICE
- PRICE_DROP_PERCENT
- LOWEST_OBSERVED_30D
- SALES_COUNT

A IA pode usar somente claims permitidos.

Implementação (TKT-11, RDR-032): os claims são produzidos deterministicamente
pelo backend (`radar.domain.allowed_claims`, sem IA) e expostos por
`GET /candidates/{candidate_id}/allowed-claims` (`schema_version=1.0`), sempre
ligados a uma Evaluation imutável (por `evaluation_id`, ou à mais recente). Cada
claim carrega provenance rastreável (`offer`/`price_observation`, `raw_capture_id`
e `correlation_id`). `CURRENT_PRICE` e `SALES_COUNT` vêm do `Offer` persistido;
`PREVIOUS_OBSERVED_PRICE` e `PRICE_DROP_PERCENT` exigem observação anterior
própria; `LOWEST_OBSERVED_30D` só é emitido quando o histórico cobre a janela de
30 dias (caso contrário é omitido com `LOWEST_OBSERVED_30D_HISTORY_INSUFFICIENT`,
nunca um mínimo "desde que começamos"); `CONFIRMED_COUPON` só existe para cupom
`CONFIRMED` (LIKELY/UNKNOWN/NOT_APPLICABLE são omitidos). O preço riscado
(`original_price`) nunca vira referência nem claim. Claims sem suporte aparecem
em `omitted_claims` com motivo explícito e os `forbidden_claims` do SDD-06 são
declarados no contrato; a IA não cria nem altera claim (AUT-063, AUT-076, AUT-077,
AUT-292). O resultado é read-only e determinístico, sem store próprio: é função da
Evaluation imutável e das evidências append-only já persistidas. Erros usam
`RAD-CAP-004/013/014`; cupom confirmado ainda não persistido pela captura pode ser
informado como condição validada. Ver `docs/04_DATA_CONTRACTS.md`.

## Versionamento

Guardar:
- `DEAL_V*`
- `MONETIZATION_V*`
- `CONFIDENCE_V*`
- feature snapshot;
- breakdown;
- scoring version.

Avaliações antigas nunca são sobrescritas.

## Implementação (TKT-09, RDR-016/027/028/029/030)

A Evaluation é imutável, versionada e append-only (`evaluation`; migration
`0004_evaluation`), exposta por `POST /candidates/{candidate_id}/evaluations` e
`GET /candidates/{candidate_id}/evaluations` (`schema_version=1.0`). O domínio
`radar.domain.evaluation` é determinístico e livre de framework; a IA nunca
calcula score, decide compliance ou cria link (AUT-031, AUT-084).

- **Deal Score**: `Deal = Price*0.40 + Seller*0.25 + Demand*0.20 + BrandFit*0.15`
  com pesos congelados 40/25/20/15 e escala `0..100`. Brand Fit é resolvido pela
  taxonomia ativa (TKT-05); Price/Seller/Demand são as saídas normalizadas dos
  TKT-06/07/08. Componente obrigatório ausente mantém `deal_score=null` e produz a
  Hard Rule bloqueante `INSUFFICIENT_REQUIRED_DATA` (nunca zero inventado).
  **Comissão não entra no Deal**: `DealFacts` não tem campo de comissão.
- **Monetization Score**: pesos 40/25/20/15 (comissão estimada, comissão efetiva
  %, conversion evidence, comissão extra). Conversion Evidence começa neutro 50
  até haver histórico próprio (AUT-053) com warning explícito; componentes
  ausentes são excluídos do agregado parcial. Monetization nunca aprova oferta
  rejeitada nem contorna guardrail — a matriz de decisão não o consome.
- **Confidence**: pesos 30/25/20/15/10 (source, freshness, completeness, price
  history depth, cross validation) e faixas `0..49 LOW`, `50..79 MEDIUM`,
  `80..100 HIGH`, calculada independentemente do Deal (AUT-054).
- **Decision Matrix**: Hard Rules sempre vencem (AUT-056). `<60` → `REJECT`;
  `60..<80` com `LOW`/sem Confidence → `REJECT`, senão `REVIEW`; `>=80` com
  `LOW`/sem Confidence → `REVIEW`, `MEDIUM`/`HIGH` → `APPROVE`. `>=80 HIGH` sem
  Hard Rule é `auto_eligible=true`, mas **nenhuma capability é promovida para
  AUTO** por esta avaliação (AUT-258, AUT-452).

Cada Evaluation persiste `passed_rules`, `failed_rules`, `warnings`, breakdown,
feature snapshot, `scoring_version`, `deal_scoring_version`,
`monetization_scoring_version`, `confidence_scoring_version`, `taxonomy_version`
e `taxonomy_hash` (AUT-030, AUT-065). Triggers do SQLite rejeitam `UPDATE`/`DELETE`
na tabela `evaluation`; reavaliar cria uma nova versão e nunca sobrescreve a
anterior. Um `AuditEvent` `EVALUATION_RECORDED` é gravado na mesma transação.
Ver `docs/04_DATA_CONTRACTS.md`.
