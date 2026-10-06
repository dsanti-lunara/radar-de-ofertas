# 08, Workflow Engine

## Orquestração

Um único Workflow Engine controla transições. Scheduler apenas cria Jobs. Workers executam Jobs e persistem resultados.

Worker nunca chama diretamente outro Worker.

## Domain State vs Job State

`Domain state != Job state`

Exemplo:
- Opportunity: AFFILIATE_LINK_PENDING
- Job: RETRY_WAIT

## Pipeline conceitual

```text
DISCOVERED
→ NORMALIZATION_PENDING
→ NORMALIZED
→ PRE_FILTER_PENDING
→ PRE_FILTERED
→ SCORING_PENDING
→ SCORED
→ AI_REVIEW_PENDING
→ AI_REVIEWED
→ APPROVED
→ AFFILIATE_LINK_PENDING
→ AFFILIATE_LINK_READY
→ CONTENT_PENDING
→ CONTENT_READY
→ REVALIDATION_PENDING
→ REVALIDATED
→ READY_TO_PUBLISH
→ PUBLISHING
→ PUBLISHED
```

Laterais:
- REJECTED
- DUPLICATE
- EXPIRED
- CANCELLED
- FAILED
- HUMAN_REVIEW_REQUIRED
- AUTH_REQUIRED
- COMPLIANCE_BLOCKED

## Job

Campos:
- id;
- type;
- entity_type/id;
- priority;
- status;
- attempts/max_attempts;
- available_at;
- locked_by/locked_at;
- lease;
- correlation_id;
- payload;
- timestamps.

Estados:
- PENDING
- CLAIMED
- RUNNING
- RETRY_WAIT
- SUCCESS
- FAILED
- CANCELLED
- DEAD

## Jobs V1

- DISCOVER_MARKETPLACE
- NORMALIZE_CAPTURE
- PRE_FILTER_CANDIDATE
- CALCULATE_SCORES
- AI_REVIEW
- CREATE_OPPORTUNITY
- GENERATE_AFFILIATE_LINK
- GENERATE_CONTENT
- VALIDATE_CONTENT
- REVALIDATE_OFFER
- PUBLISH_TELEGRAM
- PUBLISH_WHATSAPP
- CHECK_PUBLISHED_OFFER
- UPDATE_PUBLICATION
- EXPIRE_OPPORTUNITY
- BACKUP_DATABASE
- AGGREGATE_DAILY_METRICS

## Queues lógicas

- GENERAL
- AI
- BROWSER
- PUBLISHING

Concorrência inicial sugerida:
- GENERAL 4
- AI 1
- ML_BROWSER 1
- SP_BROWSER 1
- WHATSAPP_BROWSER 1
- PUBLISHING 1

Configurável.

## Scheduler

Suporta:
- INTERVAL
- CRON
- ON_DEMAND

Não cria execução sobreposta quando lock equivalente existe.

Missed schedules apropriados usam `COALESCE`, não reproduzem todos os ticks perdidos.

## Retry

Categorias:
- TRANSIENT
- PERMANENT
- HUMAN_REQUIRED

Exemplo de backoff inicial:
- 30s
- 2m
- 10m
- 30m

AUTH_REQUIRED não entra em loop de retry.

Após limite:
- DEAD
- HumanAction

## Locks and leases

Todo lock/lease possui expiry.

Crash permite recuperação por outro worker.

## Implementação (TKT-13, RDR-034..036)

O modelo durável de Job vive em `radar.domain.job` (sem FastAPI/SQLAlchemy) e é
persistido por `radar.infrastructure.job_repository` na tabela `job`
(migration `0007_job`). O Job guarda `type`, entidade, `priority`,
`status`, `attempts`/`max_attempts`, `available_at`, `correlation_id`, `payload`
e o lease (`locked_by`/`locked_at`/`lease_expires_at`). `JobStatus` é separado do
estado de domínio (AUT-118): um estado como `NEW` nunca vira estado de Job.

A fronteira pública (`POST /jobs`, `POST /jobs/claim`, `POST /jobs/{id}/start`,
`POST /jobs/{id}/complete`, `GET /jobs/{id}` e `POST`/`DELETE /locks`) demonstra
enqueue, claim com lease expirável, conclusão pelo dono do lease e lock lógico.
O claim é um `UPDATE` atômico com subquery e `RETURNING`, garantindo um único
lease sob concorrência; workers inválidos não confirmam execução alheia e o
lease expirado permite recuperação (AUT-133, AUT-140). Retry/backoff, Dead Jobs,
Scheduler e recuperação pós-crash permanecem em seus próprios tickets.

## Implementação (TKT-14, RDR-037/038/040)

A falha de um job é reportada pela fronteira pública
(`POST /jobs/{id}/fail`) pelo worker que detém o lease, com um `error_code`
estruturado; o domínio classifica a falha em `TRANSIENT`, `PERMANENT` ou
`HUMAN_REQUIRED` (AUT-129), sempre a partir do código, nunca de texto do
operador. `TRANSIENT` agenda `RETRY_WAIT` com o **backoff configurado**
(`config/retry-policy.json`, opcional; baseline aprovado 30s/2m/10m/30m,
AUT-130) enquanto `attempts < max_attempts`; ao esgotar o orçamento vira `DEAD`.
`PERMANENT` vira `FAILED` sem retry. `HUMAN_REQUIRED` — incluindo
`AUTH_REQUIRED` (`RAD-AI-001`, `RAD-WA-001`, `RAD-SP-002`) — vira `DEAD`
imediatamente, **sem** `RETRY_WAIT`, então nunca entra em loop (AUT-125). Um
`error_code` desconhecido falha fechado como `PERMANENT`.

`DEAD`/exaustão cria uma `HumanAction` (`RDR-040`, AUT-126/AUT-244)
referenciando a entidade existente (nunca a recriando), com `impact`/
`next_steps` determinísticos, e grava `JOB_RETRY_SCHEDULED`/`JOB_FAILED`/
`JOB_DEAD` + `HUMAN_ACTION_CREATED` no `audit_event` na mesma transação. As ações
são consultáveis por `GET /human-actions`/`GET /human-actions/{id}`; a resolução
pertence ao Human Actions center (RDR-063). O `available_at` de `RETRY_WAIT`
torna o job claimável de novo pelo claim atômico. Scheduler (RDR-039) e
recuperação pós-crash (RDR-042) permanecem em seus próprios tickets.

## Implementação (TKT-15, RDR-039)

O Scheduler suporta `INTERVAL`, `CRON` e `ON_DEMAND` e **apenas cria Jobs**
(AUT-117): um tick nunca executa lógica de negócio, só insere um Job `PENDING`.
O modelo durável vive em `radar.domain.schedule` (sem FastAPI/SQLAlchemy) e é
persistido por `radar.infrastructure.schedule_repository` na tabela `schedule`
(migration `0009_schedule`). O schedule guarda a cadência (`interval_seconds` ou
`cron`), o `job_type`, a prioridade, o `timezone`, as quiet windows (AUT-143), o
`lock_name` equivalente e o cursor `last_tick_at`.

A fronteira pública (`POST /schedules`, `GET /schedules`, `GET /schedules/{id}`,
`POST /schedules/{id}/enable|disable`, `POST /schedules/tick` e
`POST /schedules/{id}/tick`) demonstra o comportamento. Um tick devido cria
**um único** Job para todo o backlog — 12 intervalos perdidos viram 1 Job com
`scheduled_occurrences=12`, nunca 12 Jobs (AUT-134). Um lock equivalente ativo
(`schedule:<name>`, o mesmo lock lógico de RDR-036) adia o tick sem avançar o
cursor, de modo que os ticks adiados coalescem no próximo Job; uma quiet window
faz o mesmo no timezone do schedule. Cada tick grava
`SCHEDULE_JOB_ENQUEUED`/`SCHEDULE_TICK_SKIPPED` (e `JOB_ENQUEUED` para o Job) na
mesma transação, sempre com o Correlation ID do pipeline. O avanço do cursor é um
`UPDATE` condicional otimista sobre o `last_tick_at` anterior, então dois ticks
concorrentes nunca enfileiram o mesmo tick: um vence e o outro vira no-op.

A execução/renovação do lock equivalente pelo worker e a recuperação pós-crash
(RDR-042) permanecem em seus próprios tickets; aqui o Scheduler só consulta o
lock.

## Aging / TTL

Candidate antigo deve revalidar antes de consumir IA.

Opportunity antiga deve revalidar antes de link/content/publish conforme policy.

## Revalidation

Obrigatória antes da publicação.

Mudança pequena:
- recalcular/continuar se ainda elegível.

Mudança material:
- nova PriceObservation;
- recalcular scores;
- invalidar content se necessário.

Se fatos usados na copy mudam:
`ContentGeneration = STALE`.

## Recovery

Startup:
- detecta unclean shutdown;
- reconcilia RUNNING jobs;
- expira leases;
- limpa locks órfãos;
- reconcilia publicação;
- cria apenas schedule coalescido necessário.

## Estados externos

Integrações:
- ONLINE/READY
- DEGRADED
- OFFLINE
- AUTH_REQUIRED
- PAUSED
- DISABLED
- UNKNOWN

## Modos globais

- RUNNING
- PAUSED
- DRAINING
- MAINTENANCE

`DRAINING`: não cria novos jobs, termina os seguros já iniciados.

## Execution Node

Projetado para notebook/VM persistente:
- auto-start;
- recovery após reboot;
- Core continua mesmo com Browser offline;
- Browser jobs ficam WAITING_BROWSER;
- backup diário e status de saúde.

## Implementação (TKT-16, RDR-017/041)

O Workflow Engine centraliza as transições de domínio (AUT-116, AUT-120). O
planejamento determinístico vive em `radar.domain.workflow`: dado o estado do
Candidate e a Evaluation imutável mais recente, ele decide `CREATE_OPPORTUNITY`
(apenas com `APPROVE`), `REJECTED` (com `REJECT` ou Candidate inelegível) ou
`REVIEW_REQUIRED` (com `REVIEW`). A fronteira pública
`POST /candidates/{candidate_id}/opportunities` executa esse plano: cria a
`Opportunity` em `READY`, transiciona para `LINK_PENDING` e **cria o próximo Job**
(`GENERATE_AFFILIATE_LINK`) na mesma transação — o worker nunca chama outro worker
(AUT-119). Um `REVIEW` materializa uma `HumanAction` `REVIEW_CANDIDATE` sem tocar
na Evaluation antiga. `POST /opportunities/{id}/transitions` aplica transições
explícitas: uma transição inválida é rejeitada com `RAD-WF-015` e registrada em
`audit_event` (`OPPORTUNITY_TRANSITION_REJECTED`), enquanto uma válida grava
`OPPORTUNITY_TRANSITIONED`; `GET /opportunities/{id}` expõe a trilha. Aging/TTL:
um Candidate cuja Evaluation excede o TTL configurado exige revalidação antes da
etapa dependente (`RAD-WF-005`, AUT-135/AUT-144); o TTL é policy versionada e
hasheada (`config/opportunity-workflow.json`, opcional) e o baseline não inventa
valor (o SDD não aprova um TTL numérico). Ver `docs/04_DATA_CONTRACTS.md` e
`docs/10_PERSISTENCE_AND_RECOVERY.md`.

## Implementação (TKT-17, RDR-043/044)

Os controles operacionais centralizam a autonomia e a interrupção externa. O
modelo framework-free vive em `radar.domain.operations`:

- `AutomationMode` (`MANUAL`/`SHADOW`/`ASSISTED`/`AUTO`) é resolvido por uma
  **automation policy versionada/hasheada** para o slice brand × marketplace ×
  channel × capability (AUT-127, AUT-128); o baseline aprovado é `SHADOW` e não
  inventa regra;
- `GlobalMode` (`RUNNING`/`PAUSED`/`DRAINING`/`MAINTENANCE`) é o estado global
  (AUT-149); `DRAINING` bloqueia **novos** side effects e mantém o trabalho
  seguro (leitura/diagnóstico/recovery) disponível;
- `STOP_EXTERNAL_ACTIONS` é um kill switch persistido que bloqueia publicação,
  ações de browser e geração autenticada de link, mas mantém UI, diagnóstico,
  leitura e recovery (AUT-317, SDD-12);
- `ChannelCompliancePolicy` é versionada/hasheada e **bloqueante**: `BLOCKED`,
  `UNKNOWN`, `REVIEW_REQUIRED`, vencida (`review_due_at`) ou ainda não vigente
  nunca libera side effect, mesmo com aprovação humana (AUT-293, AUT-294,
  AUT-295);
- `IntegrationHealth` registra o estado padronizado por integração
  (`ONLINE`/`DEGRADED`/`OFFLINE`/`AUTH_REQUIRED`/`PAUSED`/`DISABLED`/`UNKNOWN`),
  então uma integração não operacional isola somente a própria capability
  (AUT-139, AUT-315).

A fronteira pública demonstra o comportamento: `GET /operations`,
`POST /operations/mode`, `POST`/`DELETE /operations/stop-external-actions`,
`POST /operations/authorize`, `GET /integrations` e `PUT /integrations/{name}`.
`POST /operations/authorize` aplica, nesta ordem, kill switch → modo global →
compliance → integração → modo de automação: SHADOW nunca envia comercialmente
(mesmo com aprovação de publicação), ASSISTED exige aprovação humana explícita da
publicação (aprovação de Candidate é insuficiente) e AUTO só passa com compliance
vigente e integração operacional. Comandos operacionais e decisões de side effect
geram `AuditEvent` na mesma transação (`OPERATIONS_MODE_CHANGED`,
`EXTERNAL_ACTIONS_STOPPED`/`RESUMED`, `INTEGRATION_HEALTH_CHANGED`,
`EXTERNAL_ACTION_AUTHORIZED`/`BLOCKED`). O estado e a saúde são persistidos em
`operations_state`/`integration_health` (migration `0011_operations_control`).
Policy inválida bloqueia a API com `RAD-CFG-012`/`RAD-CFG-013`. Ver
`docs/04_DATA_CONTRACTS.md`, `docs/10_PERSISTENCE_AND_RECOVERY.md` e
`docs/12_SECURITY_AND_COMPLIANCE.md`.

## Implementação (TKT-18, RDR-042)

O Recovery Manager executa na inicialização (AUT-133, AUT-155). O marcador
durável de shutdown vive em `radar.domain.recovery` (sem FastAPI/SQLAlchemy/
Chrome) e é persistido por `radar.infrastructure.recovery_repository` na tabela
`runtime_state` (migration `0012_runtime_state`, linha única `id='core'`).

A fronteira pública (`POST /recovery`, `GET /recovery`, `POST
/recovery/clean-shutdown`; `radarctl recover`) demonstra o comportamento. Um
shutdown limpo grava `CLEAN_SHUTDOWN_RECORDED`; um startup que encontra o
marcador não limpo detecta e audita `UNCLEAN_SHUTDOWN_DETECTED` (AUT-229). Os
jobs `CLAIMED`/`RUNNING` interrompidos são reconciliados: um job seguro volta a
`PENDING` com o lease órfão limpo (`RECOVERY_JOB_REQUEUED`) e outro worker pode
recuperá-lo, enquanto a tentativa anterior nunca confirma a nova execução
(`RAD-WF-009`/`RAD-WF-010`, AUT-140). Um job que pode ter produzido side effect
externo de resultado desconhecido (`GENERATE_AFFILIATE_LINK`, `PUBLISH_TELEGRAM`,
`PUBLISH_WHATSAPP`) **não** é reenviado automaticamente: ele é bloqueado
(`DEAD`, `RECOVERY_JOB_BLOCKED`, motivo `UNKNOWN_RESULT`), então o recovery nunca
reenvia um resultado desconhecido (GRILL-002). A suspensão específica de
publicação e a revisão humana são integradas pelo TKT-24.

Locks órfãos são limpos (`RECOVERY_LOCK_CLEARED`) e os schedules perdidos são
coalescidos em um único Job por schedule pelo Scheduler (AUT-134), sem executar
lógica de negócio (AUT-117). Cada escrita é atômica com seu `AuditEvent`; o
resumo grava `RECOVERY_COMPLETED` com o Correlation ID do pipeline. Recovery não
executa negócio, não chama IA e não cria link/publicação. Ver
`docs/04_DATA_CONTRACTS.md`, `docs/10_PERSISTENCE_AND_RECOVERY.md` e
`docs/RECOVERY_RUNBOOK.md`.
