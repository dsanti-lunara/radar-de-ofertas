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
uv run radarctl recover       # executa o Recovery Manager na inicialização
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

Comparação de fonte de compra (TKT-10): `POST /candidates/{id}/purchase-source`
compara a oferta afiliada persistida com alternativas confiáveis e
`GET /candidates/{id}/purchase-source` consulta as decisões append-only. O
Purchase Source Guardrail usa o threshold congelado `>8%` (configurável em
`config/purchase-source.json`, opcional; use `config/purchase-source.example.json`)
e a ação `REVIEW`/`SUBSTITUTE` da policy versionada/hasheada. Só entram fontes
confiáveis e comparáveis: equivalência de Product identificada e condições iguais;
o preço efetivo é `preço + frete - cupom CONFIRMED` e exige frete conhecido.
Produto não equivalente, condições diferentes e frete desconhecido são lacunas
explícitas. **Comissão não é entrada** (`commission_considered=false`), então a
monetização nunca favorece a fonte afiliada (AUT-051, AUT-062). Cada decisão
persiste `Evidence` e um `AuditEvent` `PURCHASE_SOURCE_DECIDED` na mesma transação.
Erros usam `RAD-CAP-004/012` e policy inválida bloqueia a API com `RAD-CFG-008`.
Contrato em `docs/04_DATA_CONTRACTS.md`.

Claims comerciais (TKT-11): `GET /candidates/{candidate_id}/allowed-claims`
consulta os `allowed_claims` versionados de uma Evaluation imutável com a
`Evidence`/provenance de cada afirmação. O motor é determinístico, read-only e
não usa IA (AUT-063, AUT-076): `CURRENT_PRICE` sempre tem suporte do `Offer`;
`PREVIOUS_OBSERVED_PRICE` e `PRICE_DROP_PERCENT` só existem com observação
anterior própria; `LOWEST_OBSERVED_30D` exige histórico que cubra a janela de 30
dias (sem cobertura é omitido com warning, nunca inventado); `SALES_COUNT` vem do
`Offer`; `CONFIRMED_COUPON` só é produzido para cupom `CONFIRMED` (provável/
desconhecido é omitido). Preço riscado isolado nunca é prova. Claims sem suporte
aparecem em `omitted_claims` e os `forbidden_claims` do SDD-06 são explícitos.
Erros usam `RAD-CAP-004/013/014`. Contrato em `docs/04_DATA_CONTRACTS.md`.

Dedupe e repost (TKT-12): `POST /candidates/{candidate_id}/repost` aplica o
guardrail determinístico de dedupe/repost ao `Offer` persistido, à Evaluation mais
recente (Deal) e a um **histórico de publicação fornecido pelo chamador** — um
histórico *fake* enquanto o publisher real não existe; `GET
/candidates/{candidate_id}/repost` consulta as decisões append-only. A policy
versionada/hasheada (`config/repost.json`, opcional; use
`config/repost.example.json`; `RADAR_REPOST_FILE` força um arquivo) congela o
cooldown de referência (72h), a queda de preço (`>=10%`) e o piso de Deal forte
(`>=80`). Mudança irrelevante com cooldown ativo bloqueia com
`DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE`; queda `>=10%`, novo cupom material ou nova
condição material **com** `Evidence` liberam o repost; cooldown vencido sem
mudança material ainda exige Deal forte, senão bloqueia com `DEAL_NOT_STRONG`.
Cupom/condição material sem `Evidence` é warning explícito e não vira material.
Cada decisão persiste `Evidence` e um `AuditEvent` `REPOST_DECIDED` na mesma
transação. Erros usam `RAD-CAP-004/015` e policy inválida bloqueia a API com
`RAD-CFG-009`. Contrato em `docs/04_DATA_CONTRACTS.md`.

Fila de jobs com claim e lease (TKT-13): `POST /jobs` persiste um Job `PENDING`
com `priority`, `available_at`, `attempts`/`max_attempts` e `correlation_id`;
`POST /jobs/claim` concede um **único** lease expirável (claim atômico), então
workers concorrentes nunca compartilham o mesmo lease. `POST /jobs/{id}/start` e
`POST /jobs/{id}/complete` exigem o lease do próprio worker: um worker inválido
não inicia/confirma execução alheia (`RAD-WF-009`) e um lease expirado permite
que outro worker recupere o job (AUT-133, AUT-140). O estado de Job é
independente do estado de domínio (AUT-118): `type="NEW"` é rejeitado com
`RAD-WF-006`. `POST`/`DELETE /locks` cobrem o lock lógico com expiração
(`RAD-WF-004`). Cada transição grava `AuditEvent`; retry/backoff, Dead Jobs,
Scheduler e recovery são tickets próprios. Erros em `docs/ERROR_CATALOG.md`;
contrato em `docs/04_DATA_CONTRACTS.md`.

Retry, Dead Job e HumanAction (TKT-14): `POST /jobs/{id}/fail` reporta a falha
pelo worker que detém o lease e o domínio classifica o `error_code` em
`TRANSIENT` (retry com o backoff configurado em `config/retry-policy.json`,
opcional; use `config/retry-policy.example.json`; baseline aprovado
30s/2m/10m/30m), `PERMANENT` (`FAILED`, sem retry) ou `HUMAN_REQUIRED`/
`AUTH_REQUIRED` (`DEAD`, **sem** loop). Ao esgotar as tentativas o job vira
`DEAD` e uma `HumanAction` auditável (`DEAD_JOB_REVIEW`/`AUTHENTICATE_MARKETPLACE`/
`RESTORE_AI_AUTH`) é criada na mesma transação, referenciando a entidade existente
sem recriá-la; `GET /human-actions` e `GET /human-actions/{id}` consultam as ações
(a resolução pertence ao Human Actions center, RDR-063). Erros usam
`RAD-WF-009/010/011` e `RAD-CFG-010`; contrato em `docs/04_DATA_CONTRACTS.md`.

Scheduler (TKT-15): `POST /schedules` persiste schedules `INTERVAL`/`CRON`/
`ON_DEMAND`; `GET /schedules`/`GET /schedules/{id}` consultam e
`POST /schedules/{id}/enable|disable` alternam o estado. `POST /schedules/tick`
avalia os schedules habilitados devidos e `POST /schedules/{id}/tick` força um
schedule; ambos **apenas criam Jobs** `PENDING` (AUT-117) — nunca executam lógica
de negócio. Ticks perdidos são coalescidos em um único Job (AUT-134): um backlog
de 12 intervalos gera 1 Job com `scheduled_occurrences=12`, não 12 Jobs. Um lock
equivalente ativo (`schedule:<name>`, consultado via `POST /locks`) adia o tick
sem avançar o cursor, e quiet windows são avaliados no `timezone` do schedule
(AUT-143). Cada tick grava `SCHEDULE_JOB_ENQUEUED`/`SCHEDULE_TICK_SKIPPED` e o Job
grava `JOB_ENQUEUED` na mesma transação. Erros usam `RAD-WF-012/013`; contrato em
`docs/04_DATA_CONTRACTS.md`.

Opportunity pelo Workflow Engine (TKT-16): `POST /candidates/{id}/opportunities`
avança um Candidate avaliado e cria a Opportunity **apenas** com uma Evaluation
`APPROVE` (AUT-032); `REJECT` retorna `REJECTED` sem Opportunity, `REVIEW` cria uma
`HumanAction` `REVIEW_CANDIDATE` sem alterar a Evaluation antiga e um Candidate sem
Evaluation retorna `RAD-CAP-013`. O engine — nunca um worker chamando outro worker
(AUT-119) — cria a próxima etapa (`GENERATE_AFFILIATE_LINK`) e transiciona a
Opportunity para `LINK_PENDING` na mesma transação. `GET /opportunities/{id}` expõe
a Opportunity e o `history` auditável; `POST /opportunities/{id}/transitions`
aplica transições explícitas e rejeita uma inválida com `RAD-WF-015` (409) depois
de auditá-la (`RAD-WF-016` para estado desconhecido, `RAD-WF-014` para
inexistente). Candidate envelhecido além do TTL configurado exige revalidação
(`RAD-WF-005`, AUT-135/AUT-144); o TTL é policy versionada/hasheada
(`config/opportunity-workflow.json`, opcional) e o baseline não inventa valor —
policy inválida bloqueia a API com `RAD-CFG-011`. Contrato em
`docs/04_DATA_CONTRACTS.md`.

Controles operacionais (TKT-17): `GET /operations` expõe o estado global
(`RUNNING`/`PAUSED`/`DRAINING`/`MAINTENANCE`), o kill switch
`STOP_EXTERNAL_ACTIONS`, a automation policy e a compliance policy vigentes.
`POST /operations/mode` muda o modo global, `POST`/`DELETE
/operations/stop-external-actions` engatilha/libera o kill switch e
`POST /operations/authorize` decide permissão ou bloqueio de uma ação
(`PUBLISH`/`BROWSER`/`AUTHENTICATED_LINK` são side effects; `READ`/`DIAGNOSTIC`/
`RECOVERY` continuam disponíveis sob STOP). SHADOW nunca envia comercialmente —
mesmo com aprovação de Candidate/publicação; ASSISTED exige aprovação humana
explícita da publicação (aprovar Candidate é insuficiente); a compliance policy é
versionada/hasheada e `UNKNOWN`/vencida/`BLOCKED`/`REVIEW_REQUIRED` bloqueiam o
side effect mesmo com aprovação humana. A automation policy é versionada/hasheada
(`config/automation-policy.json`, opcional; use
`config/automation-policy.example.json`) e a compliance policy em
`config/channel-compliance.json` (use `config/channel-compliance.example.json`).
`GET /integrations` e `PUT /integrations/{name}` registram a saúde padronizada de
cada integração, então uma integração indisponível isola apenas o próprio escopo
(AUT-315). Decisões de side effect e comandos operacionais geram `AuditEvent`.
Erros usam `RAD-WF-018`; policy inválida bloqueia a API com `RAD-CFG-012/013`.
Contrato em `docs/04_DATA_CONTRACTS.md`.

Recovery de crash (TKT-18): `POST /recovery` executa o Recovery Manager na
inicialização, `GET /recovery` expõe o marcador durável de shutdown e `POST
/recovery/clean-shutdown` grava o shutdown limpo; `radarctl recover` oferece a
mesma entrada pela CLI. Um shutdown limpo grava o marcador; um startup sem ele
detecta e audita o **unclean shutdown** (`UNCLEAN_SHUTDOWN_DETECTED`). Jobs
`CLAIMED`/`RUNNING` interrompidos são reconciliados: um job seguro volta a
`PENDING` com o lease órfão limpo, então a tentativa anterior nunca confirma a
nova execução (`RAD-WF-009`/`RAD-WF-010`) e outro worker pode recuperá-lo; um job
que pode ter produzido side effect externo de resultado desconhecido
(`GENERATE_AFFILIATE_LINK`, `PUBLISH_TELEGRAM`, `PUBLISH_WHATSAPP`) é bloqueado
(`DEAD`, `UNKNOWN_RESULT`) e **nunca** reenviado automaticamente (GRILL-002), com
a suspensão específica de publicação integrada em TKT-24. Locks órfãos são
limpos (`RECOVERY_LOCK_CLEARED`) e schedules perdidos coalescidos em um único Job
por schedule (AUT-134), sem executar lógica de negócio. Cada escrita é atômica
com seu `AuditEvent`; o marcador vive em `runtime_state` (migration
`0012_runtime_state`). Erros usam `RAD-WF-019`; contrato em
`docs/04_DATA_CONTRACTS.md`.

Affiliate link e tracking (TKT-20): `POST /candidates/{id}/affiliate-link` gera o
`AffiliateLink` próprio (RDR-018) de um Candidate com Evaluation `APPROVE` cuja
Opportunity está em `LINK_PENDING`/`LINK_READY`; um Candidate não aprovado não
gera link (`RAD-LINK-007`). O `TrackingContext` interno (RDR-070) é resolvido de
um mapeamento versionado/hasheado (`config/tracking-labels.json`, opcional; use
`config/tracking-labels.example.json`) e é separado da etiqueta externa:
`tracking_label` aceita somente `[a-z0-9]{1,30}` e nunca é normalizada
(`RAD-LINK-004`); o baseline é vazio porque nenhuma etiqueta é presumida
(`rbtgoffer` é exemplo sintático), então um slice sem associação bloqueia com
`RAD-LINK-005`. O provider Fake é determinístico e offline; o retorno
`{affiliate_url, source, product_reference}` é validado por host/produto/contexto
(`RAD-LINK-003`) e o link é preservado **literalmente** — a IA nunca altera URL
(AUT-078/AUT-164). `source=FAKE` marca o link como `productive=false` (AUT-422).
A geração é idempotente por Opportunity + etiqueta e grava o `AuditEvent`
`AFFILIATE_LINK_GENERATED` na mesma transação; `GET
/candidates/{id}/affiliate-links` e `GET /affiliate-links/{id}` consultam os
links. Erros: `RAD-LINK-001/002/003/004/005/006/007/008`; mapeamento inválido
bloqueia a API com `RAD-CFG-015`. A associação real ML/landing e a geração por
adapter pertencem a #45/#46. Contrato em `docs/04_DATA_CONTRACTS.md`.

Content generation (TKT-21): `POST /opportunities/{id}/content-generations` gera a
`ContentGeneration` (RDR-019/RDR-051) de uma Opportunity não terminal que já possui
`AffiliateLink` validado. O provider Fake (RDR-051) devolve apenas
`headline`/`body`/`cta`/`warnings`; os guards determinísticos (Numeric Guard
RDR-052, Claim Guard RDR-053, regras de canal e compliance RDR-054) precedem
conteúdo utilizável: um número comercial ou claim sem Evidence bloqueia a preview
publicável (`RAD-AI-005`/`RAD-AI-006`) e uma URL inventada pela IA é recusada
(`RAD-AI-013`), sem persistir nada. O renderer determinístico (RDR-069) insere
preço (claim `CURRENT_PRICE`), a URL afiliada **literal** e o disclosure; generated
e final content ficam separados com suas versões. `GET
/opportunities/{id}/content-generations` e `GET /content-generations/{id}`
consultam as previews, reportando `STALE` quando um fato relevante (nova
observação de preço, link, versão de knowledge/prompt) muda. Um input equivalente e
ainda válido reusa o resultado persistido (`cache_hit=true`, RDR-055) sem nova
chamada ao provider; uma mudança relevante ou um resultado inválido nunca é
reusado. Erros: `RAD-AI-004/005/006/007/011/012/013/014/015`; contrato em
`docs/04_DATA_CONTRACTS.md`.

Publicação Fake idempotente (TKT-23): `POST
/opportunities/{id}/publications` publica uma `ContentGeneration` validada e
não-`STALE` de uma Opportunity em `READY_TO_PUBLISH` por um publisher Fake
offline/determinístico; a `Publication` é entidade própria (AUT-025/AUT-034),
separada de ContentGeneration/Opportunity, e `GET /opportunities/{id}/publications`
+ `GET /publications/{id}` consultam a timeline. Revalidação, o gate de
autorização TKT-17 (`SHADOW`/`ASSISTED`/compliance/kill switch) e a Publication
Policy (hard cap/burst/cooldown/quiet hours) bloqueiam **antes** do publisher e
retornam 409 `RAD-PUB-003` com `reason_code` acionável e zero side effect. Repetir
`idempotency_key` devolve a Publication confirmada (`idempotent_replay=true`) sem
novo envio. A policy é versionada/hasheada
(`config/publication-policy.json`, opcional; use
`config/publication-policy.example.json`; `RADAR_PUBLICATION_POLICY_FILE` força um
arquivo): o baseline usa os limites de referência do SDD-09 e deixa
cooldown/quiet hours explícitos. Erros: `RAD-PUB-001/002/003/004/005` e
`RAD-CFG-016`; contrato em `docs/04_DATA_CONTRACTS.md`. O resultado desconhecido
(crash após aceitação remota) e a suspensão/HumanAction pertencem a TKT-24.

Suspensão de resultado desconhecido (TKT-24, RDR-128, ADR 0001): quando o
publisher sinaliza um envio possivelmente aceito sem confirmação local, a
`Publication` fica suspensa (`status=UNKNOWN`, evento `RESULT_UNKNOWN` com o
receipt) e uma `HumanAction` (`REVIEW_PUBLICATION`/`SEND_RESULT_UNKNOWN`) é
aberta; a fronteira responde 409 `RAD-PUB-006` e **nunca** reenvia
automaticamente. Uma suspensão aberta bloqueia novas tentativas da Opportunity
até `POST /publications/{id}/resolve`, que exige evidência corroborante
(`MESSAGE_MARKER`/`PROVIDER_RECEIPT`/`DESTINATION_AUDIT`); autorização humana sem
evidência retorna 409 `RAD-PUB-007` e mantém a suspensão. `CONFIRM_SENT` marca
`PUBLISHED` e `CONFIRM_NOT_SENT` marca `FAILED`, sempre auditado; a nova tentativa
mantém revalidação/guardrails. O Fake simula o crash
(`FakePublisher(crash_after_accept=True)`).

Control Center e Home health (TKT-25, RDR-056/RDR-057): a UI React/TypeScript/Vite
fica em `packages/control-center` e consulta o read model
`GET /health/overview` por polling REST. O overview (`schema_version=1.0`)
responde 200 com as capabilities canônicas da Home (Core, Database, Scheduler,
IA/ChatGPT, Browser, Mercado Livre, Shopee, WhatsApp, Telegram, Backup):
`core` reflete a API que responde, `database` vem do probe de saúde e cada
dependência vem de `GET /integrations`; uma integração nunca registrada é
`UNKNOWN` (`INTEGRATION_NOT_REGISTERED`), nunca saudável, e o agregado usa a
regra fail-closed (`DEGRADED`/`UNHEALTHY`). Build e execução local:

```bash
pnpm --filter @radar/control-center build   # gera packages/control-center/dist
uv run radar-api                            # serve a UI em 127.0.0.1:8000 (GET /)
pnpm --filter @radar/control-center dev     # dev server (proxy /health -> 127.0.0.1:8000)
```

O `radar-api` monta os assets em `/` apenas se o build existir (ou
`RADAR_CONTROL_CENTER_DIST` apontar para ele), só em `127.0.0.1` e sem CORS; sem
build a API continua operando normalmente. O contrato em
`docs/04_DATA_CONTRACTS.md` e a rastreabilidade em
`docs/13_QA_ACCEPTANCE_MATRIX.md`.

Review de oportunidades (TKT-26, RDR-058/RDR-059/RDR-060): a aba Oportunidades
consome `GET /review/inbox` e `GET /review/candidates/{id}` (dados reais com
timeline e versões) e registra a decisão humana por
`POST /candidates/{id}/human-reviews` (`APPROVE`/`REJECT`/`EDIT_CONTENT` com
motivo), consultável por `GET /candidates/{id}/human-reviews` e
`GET /human-reviews/{id}`. A `HumanReview` é append-only e separada da `AIReview`
(AUT-035); aprovar um Candidate **não** autoriza publicação (GRILL-001) — a
resposta sempre traz `publication_authorized=false` e o portão operacional
vigente (ex.: SHADOW com envio bloqueado). O parser/cliente da UI ficam em
`packages/control-center/src/review/`.

Consulta e aprovação de publicação (TKT-27, RDR-061/RDR-062): a aba Publicações
consome `GET /publications` (Inbox com Publications reais e a projeção `PREVIEW` de
uma Opportunity `READY_TO_PUBLISH` ainda não enviada), `GET /publications/{id}`
(detail com preview, link literal, tracking, revision, external ID, última
validação, timeline e HumanAction) e `GET /publications/preview/{opportunity_id}`.
O **preview não faz envio**: a aprovação explícita é um formulário separado da
review de Candidate e chama `POST /opportunities/{id}/publications` com
`publication_approved=true`, continuando sujeita ao portão operacional e à
revalidação. As ações auditadas `POST
/publications/{id}/revalidate|expire|cancel` nunca reenviam (expirar é idempotente
e bloqueado em `UNKNOWN`; cancelar é soft, `DELETED`, e bloqueia `PUBLISHED`). O
parser/cliente da UI ficam em `packages/control-center/src/publications/`.

Testes live (browser/IA/Telegram/WhatsApp) são opt-in e ficam fora da suíte padrão.
