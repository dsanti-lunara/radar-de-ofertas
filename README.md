# Radar Engine V1, pacote canônico de SDD

Este pacote consolida as 13 rodadas de planejamento aprovadas para a automação de afiliados das marcas **Radar Beauty** e **Casa em Ordem**.

O objetivo da V1 é executar, em um nó local persistente, o fluxo:

`descobrir → normalizar → historizar → pontuar → revisar com IA → aprovar → gerar link afiliado → gerar conteúdo → revalidar → publicar → monitorar`

Marketplaces iniciais:
- Mercado Livre
- Shopee

Destinos iniciais:
- Telegram
- Canais do WhatsApp

## Ordem de leitura para implementação

1. `AGENTS.md`
2. `docs/00_SDD_MASTER.md`
3. `docs/01_SCOPE_AND_PRINCIPLES.md`
4. Documento específico da issue
5. `docs/DECISION_LOG.md`
6. `docs/13_QA_ACCEPTANCE_MATRIX.md`
7. `docs/14_DELIVERY_PLAN.md`
8. `docs/BROWSER_RECONNAISSANCE.md` antes de qualquer adapter real de navegador

## Regra de autoridade

Em caso de divergência:
1. SDD e Decision Log
2. Contratos de domínio e dados
3. Acceptance Criteria e testes
4. Código
5. Comentários

O agente não deve redesenhar silenciosamente uma decisão aprovada. Se encontrar inviabilidade técnica, deve registrar um `ARCHITECTURE_CONFLICT` com evidência, impacto e alternativas.

## Fonte funcional

Este pacote foi consolidado a partir das rodadas SDD-01 a SDD-13 e das premissas do arquivo `Plano_Mestre_Radar_Beauty_Casa_em_Ordem_v1.4.docx`.

O arquivo original não precisa ser usado como contrato de implementação quando houver especificação equivalente neste pacote, mas continua sendo referência de negócio para as duas marcas.

## Desenvolvimento local

Toolchains fixadas: Python 3.13.16 (`.python-version`, gerenciado por `uv`) e Node LTS + pnpm (`packageManager` no `package.json`).

```bash
uv sync                       # cria .venv e instala ruff, pyright, pytest e hypothesis
uv run ruff check .           # lint Python
uv run ruff format --check .  # formatação Python
uv run pyright                # types Python
uv run pytest                 # testes seguros, sem credenciais

pnpm install                  # workspace TypeScript
pnpm lint && pnpm typecheck && pnpm test
```

Operação local da fundação (TKT-01):

```bash
uv run radarctl migrate       # aplica migrations até head (cria o diretório de dados quando necessário)
uv run radarctl status        # saúde por CLI; sai != 0 quando não operacional
uv run radarctl config        # valida e exibe a configuração sanitizada (sem secrets)
uv run radarctl version
uv run radar-api              # API local em 127.0.0.1:8000 (GET /health, GET /version, GET /config)
```

Configuração operacional (TKT-02): `config/radar.json` é opcional e validado por
schema (use `config/radar.example.json` como base); variáveis `RADAR_*` sobrepõem
o arquivo. Secrets ficam fora do arquivo: cada referência lógica é resolvida por
`RADAR_SECRET_<NOME>` ou por variável explícita na seção `secrets`. Config
inválida bloqueia CLI/API com `RAD-CFG-001`/`RAD-CFG-002`; logs são JSON
sanitizado em stderr com Correlation ID.

Captura manual (TKT-03): `POST /captures/manual` recebe o contrato versionado
`ManualCapture` (`schema_version=1.0`), sanitiza/valida o payload, persiste
`RawCapture`/`Evidence` e materializa `Product`, `MarketplaceProduct`, `Offer`,
`DiscoveryEvent`, `Candidate` e `AuditEvent` em uma única transação; `GET
/candidates/{id}` consulta o Candidate resultante. `marketplace + external_id` é
único (captura repetida não duplica identidade), campos sensíveis são recusados
e erros retornam `RAD-CAP-001..004` com Correlation ID. Contrato em
`docs/04_DATA_CONTRACTS.md`.

Histórico de preços (TKT-04): cada captura normalizada acrescenta uma
`PriceObservation` append-only ao `MarketplaceProduct` na mesma transação. A
identidade `(marketplace_product_id, source, observed_at)` é única: captura
repetida reutiliza a observação, sem sobrescrever o histórico nem inventar preço.
`GET /marketplace-products/{id}/price-history` retorna a série cronológica com
proveniência (`source`, `observed_at`, `correlation_id`, `raw_capture_id`),
dinheiro em string decimal e timestamps UTC; MarketplaceProduct inexistente
retorna `RAD-CAP-005`.

Classificação de categoria (TKT-05): a captura aceita `product.category`
opcional (categoria bruta) e
`GET /candidates/{id}/classification/{brand}` classifica o Candidate pela
taxonomia versionada das marcas (`RADAR_BEAUTY`/`CASA_EM_ORDEM`) e resolve Brand
Fit explicável. A taxonomia é configuração versionada/hasheada em
`config/brand-taxonomy.json` (opcional; use `config/brand-taxonomy.example.json`;
`RADAR_TAXONOMY_FILE` força um arquivo) sobre o baseline aprovado. Brand Fit de
Radar Beauty segue os valores aprovados; mapeamento/calibração ausente devolve
`brand_fit=null` com warning explícito e categoria fora de escopo devolve o Hard
Rule `OUT_OF_SCOPE_CATEGORY`. Erros usam `RAD-CAP-004/006/007`; taxonomia
inválida bloqueia a API com `RAD-CFG-005`. Contrato em `docs/04_DATA_CONTRACTS.md`.

Oportunidade de preço (TKT-06): `GET /candidates/{id}/price-opportunity`
recomputa, de forma read-only e determinística, o breakdown de Price Opportunity
a partir do `Offer` e do histórico append-only. Pesos 45/20/20/10/5 e faixas de
histórico/queda/comparação seguem o SDD-05; histórico insuficiente e referência
ausente usam neutro 50 com warning para o Confidence Engine; só cupom
`CONFIRMED` reduz o `effective_price` (que exige frete conhecido) e o preço
riscado nunca é prova de vantagem. Condições confirmadas (`shipping_cost`,
`coupon_state`/`coupon_amount`/`coupon_code`, `comparable_price`/
`comparable_marketplace`) podem ser informadas como query params validados.
`Coupon / Final Price` e `Shipping Impact` não têm faixas calibradas no SDD e são
reportados como lacuna (`score=null`, `fully_calibrated=false`), sem valor
inventado. Erros usam `RAD-CAP-004/008`. Contrato em `docs/04_DATA_CONTRACTS.md`.

Qualidade do vendedor (TKT-07): `GET /candidates/{id}/seller-quality` compõe, de
forma read-only e determinística, reputation 40% / rating 25% / sales 20% /
trusted 15% a partir dos fatos de vendedor do `Offer` e de sinais validados
informados na avaliação. Cada componente carrega a origem do sinal. O SDD não
calibra a normalização, então ela é configuração versionada/hasheada
(`config/seller-quality.json`, opcional; use `config/seller-quality.example.json`)
com baseline aprovado vazio: sinal sem mapeamento é lacuna explícita
(`SELLER_QUALITY_NORMALIZATION_NOT_DEFINED`), dado ausente não vira zero
(`SELLER_QUALITY_MISSING_DATA`) e dado inválido/contraditório gera warning. O
resultado é parcial sobre os componentes calibrados (`weight_covered`); o
snapshot pertence à Evaluation. Erros usam `RAD-CAP-004/009` e normalização
inválida bloqueia a API com `RAD-CFG-006`. Contrato em `docs/04_DATA_CONTRACTS.md`.

Demanda por categoria (TKT-08): `GET /candidates/{id}/demand` calcula, de forma
read-only e determinística, o breakdown de Demand a partir da categoria bruta e do
`sales_count` persistidos e de sinais validados informados na avaliação
(`rating_count`, `trend`, `affiliate_portal`, `badges`). A categoria canônica é
resolvida pela taxonomia versionada e cada componente carrega a origem do sinal
(`persisted_offer`/`evaluation_input`). A normalização **evolui por categoria** e
é configuração versionada/hasheada (`config/demand.json`, opcional; use
`config/demand.example.json`) com baseline aprovado vazio: sinal/categoria sem
mapeamento ou peso é lacuna explícita (`DEMAND_NORMALIZATION_NOT_DEFINED`), dado
ausente não vira zero (`DEMAND_MISSING_DATA`) e categoria não resolvida é
explícita (`DEMAND_CATEGORY_NOT_DEFINED`). Configuração incompleta resulta em
`fully_calibrated=false` e nunca é apresentada como validada; nenhum passo usa
IA. Erros usam `RAD-CAP-004/010` e normalização inválida bloqueia a API com
`RAD-CFG-007`. Contrato em `docs/04_DATA_CONTRACTS.md`.

Decisão do Candidate (TKT-09): `POST /candidates/{id}/evaluations` compõe e
persiste uma **Evaluation imutável** com Deal, Monetization e Confidence e a
Decision Matrix; `GET /candidates/{id}/evaluations` consulta as versões
armazenadas. O Deal usa os pesos congelados 40/25/20/15 e nunca recebe comissão
(AUT-051); a Monetization (40/25/20/15) só ordena oportunidades aceitáveis; a
Confidence (30/25/20/15/10) é independente. Hard Rules precedem score, IA, link e
publicação (AUT-056): dado obrigatório ausente é bloqueante
(`INSUFFICIENT_REQUIRED_DATA`) e categoria fora de escopo propaga
`OUT_OF_SCOPE_CATEGORY`, ambos forçando `REJECT`. Cada Evaluation guarda
breakdown, feature snapshot, `passed_rules`/`failed_rules`, scoring versions e
`taxonomy_version`/`hash` (AUT-030, AUT-065); a tabela é append-only com triggers
que rejeitam `UPDATE`/`DELETE` e um `AuditEvent` `EVALUATION_RECORDED` é gravado na
mesma transação. `auto_eligible=true` é apenas elegibilidade, nunca promoção para
AUTO. Erros usam `RAD-CAP-004/011`. Contrato em `docs/04_DATA_CONTRACTS.md`.

Testes live (browser/IA/Telegram/WhatsApp) são opt-in e ficam fora da suíte padrão.
