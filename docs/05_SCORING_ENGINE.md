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

### Seller Quality

Composição inicial:
- marketplace reputation 40%;
- rating 25%;
- sales history 20%;
- official/trusted status 15%.

Dados ausentes não viram zero automaticamente. Afetam Confidence.

### Demand

Pode usar:
- sales_count;
- rating_count;
- trend signal;
- affiliate portal signal;
- badges.

Normalização deve evoluir por categoria.

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

## Versionamento

Guardar:
- `DEAL_V*`
- `MONETIZATION_V*`
- `CONFIDENCE_V*`
- feature snapshot;
- breakdown;
- scoring version.

Avaliações antigas nunca são sobrescritas.
