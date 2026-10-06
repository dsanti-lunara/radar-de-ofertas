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
