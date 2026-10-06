# 10, Persistence, Configuration, Secrets, Backup and Recovery

## Banco

SQLite é canônico na V1.

Configuração:
- WAL;
- foreign_keys ON;
- transactions;
- busy timeout;
- indexes;
- migrations.

SQLAlchemy 2 + Alembic.

Implementação (TKT-03): a captura manual persiste `product`, `marketplace_product`
(único por `marketplace + external_id`), `offer`, `raw_capture`, `evidence`,
`discovery_event`, `candidate` e `audit_event` em uma única transação; a
constraint de identidade e as FKs são verificadas pelo SQLite. Timestamps são
ISO-8601 UTC e dinheiro é string decimal (sem float binário). A migration
`0002_manual_capture` cria o schema e atualiza `schema_version` (`db_schema`).

Implementação (TKT-04): a migration `0003_price_observation` acrescenta a tabela
append-only `price_observation` (FK para `marketplace_product` e `raw_capture`,
única por `marketplace_product_id + source + observed_at`) e atualiza
`schema_version`. Cada captura normalizada grava a observação na mesma transação;
captura repetida com a mesma identidade reutiliza a linha, sem sobrescrever o
histórico. `price`/`original_price`/`shipping_cost` são strings decimais e
`observed_at` é ISO-8601 UTC.

Implementação (TKT-09): a migration `0004_evaluation` acrescenta a tabela
append-only `evaluation` (FK para `candidate` e `audit_event`, índice
`candidate_id + created_at`) e atualiza `schema_version`. A tabela guarda o
`deal_score` decimal, `monetization_score`, `confidence`, `decision`,
`passed_rules`/`failed_rules`, `warnings`, breakdown, feature snapshot e as
scoring versions. Triggers `trg_evaluation_no_update`/`trg_evaluation_no_delete`
rejeitam `UPDATE`/`DELETE` no banco, então uma Evaluation antiga nunca é
sobrescrita; o `AuditEvent` `EVALUATION_RECORDED` é gravado na mesma transação da
Evaluation.

Implementação (TKT-10): a migration `0005_purchase_source_decision` acrescenta a
tabela append-only `purchase_source_decision` (FK para `candidate` e
`audit_event`, índice `candidate_id + created_at`) e atualiza `schema_version`. A
tabela guarda a decisão do Purchase Source Guardrail, a fonte afiliada, a melhor
alternativa, os preços efetivos e a diferença decimal, a policy
versionada/hasheada, as fontes avaliadas e warnings como JSON. Triggers
`trg_purchase_source_decision_no_update`/`trg_purchase_source_decision_no_delete`
rejeitam `UPDATE`/`DELETE` no banco; o `AuditEvent` `PURCHASE_SOURCE_DECIDED` e as
linhas de `Evidence` são gravados na mesma transação da decisão.

Implementação (TKT-12): a migration `0006_repost_decision` acrescenta a tabela
append-only `repost_decision` (FK para `candidate` e `audit_event`, índice
`candidate_id + created_at`) e atualiza `schema_version`. A tabela guarda a
decisão de dedupe/repost, o motivo, as mudanças materiais e warnings como JSON, o
baseline de publicação, a queda observada, a janela de cooldown e a policy
versionada/hasheada. Triggers `trg_repost_decision_no_update`/
`trg_repost_decision_no_delete` rejeitam `UPDATE`/`DELETE` no banco; o
`AuditEvent` `REPOST_DECIDED` e as linhas de `Evidence` são gravados na mesma
transação da decisão. O histórico de publicação usado na comparação é uma entrada
do guardrail (histórico *fake* até o publisher real), não uma tabela deste ticket.

Implementação (TKT-13): a migration `0007_job` acrescenta a tabela durável `job`
(RDR-034, RDR-035) e a tabela `job_lock` (RDR-036), atualiza `schema_version` e
cria o índice `ix_job_claim` (`status`, `priority`, `available_at`). O `job`
guarda `type`, entidade, `priority`, `status`, `attempts`/`max_attempts`,
`available_at`, `correlation_id`, `payload` e os campos de lease
(`locked_by`/`locked_at`/`lease_expires_at`); os estados de Job são independentes
dos estados de domínio (AUT-118). Diferente das tabelas append-only, o `job` é
mutável por desenho (PENDING → CLAIMED → RUNNING → SUCCESS): o claim é um
`UPDATE` atômico com subquery e `RETURNING`, então SQLite concede um único lease
por job (AUT-121, AUT-140). Jobs e locks com timestamps em ISO-8601 UTC; o
histórico de transições é auditável por `AuditEvent` na mesma transação.

Implementação (TKT-14): a migration `0008_human_action` acrescenta a tabela
`human_action` (RDR-040) e o índice `ix_human_action_status` (`status`,
`created_at`), atualiza `schema_version` e **não** altera a tabela `job`: as
transições de retry/Dead reutilizam `status`, `attempts`, `available_at` e o lease
já persistidos por `0007_job`. O fluxo de falha classifica o `error_code`
(AUT-129), persiste `RETRY_WAIT` com backoff configurado, `FAILED` (permanente)
ou `DEAD` (exaustão/humano) e, quando exige intervenção, grava a `human_action` e
o `AuditEvent` `HUMAN_ACTION_CREATED` na **mesma transação** do job; a
`HumanAction` referencia a entidade existente (`entity_type`/`entity_id`) e nunca
recria a entidade. A tabela é mutável apenas como parte da resolução futura
(RDR-063); a persistência do evento de job (`JOB_RETRY_SCHEDULED`/`JOB_FAILED`/
`JOB_DEAD`) é append-only em `audit_event`.

Implementação (TKT-15): a migration `0009_schedule` acrescenta a tabela durável
`schedule` (RDR-039), o índice `ix_schedule_enabled` (`enabled`, `type`) e a
constraint `uq_schedule_name`, atualiza `schema_version` e **não** altera `job`/
`job_lock`: o Job criado pelo tick é o mesmo Job de `0007_job` e o lock
equivalente é o mesmo `job_lock` (RDR-036, AUT-140). O schedule guarda a cadência
(`interval_seconds`/`cron`), o `job_type`, a prioridade, o `timezone`, as quiet
windows como JSON e o cursor `last_tick_at`; timestamps em ISO-8601 UTC. O tick
grava o Job, os `AuditEvent` (`JOB_ENQUEUED`, `SCHEDULE_JOB_ENQUEUED`) e avança o
cursor na **mesma transação**, então um crash não deixa Job sem cursor nem
cursor sem Job; um tick adiado por lock/quiet window grava
`SCHEDULE_TICK_SKIPPED` e não avança o cursor (AUT-134).

Implementação (TKT-16): a migration `0010_opportunity` acrescenta a tabela durável
`opportunity` (RDR-017), a constraint `uq_opportunity_evaluation` (uma Opportunity
por Evaluation imutável, tornando o advance idempotente) e o índice
`ix_opportunity_candidate` (`candidate_id`, `created_at`). A Opportunity
referencia `candidate` e `evaluation` por foreign key e guarda o `state` atual mais
o `audit_event_id` do evento `OPPORTUNITY_CREATED`. O engine grava a Opportunity, o
próximo Job (`GENERATE_AFFILIATE_LINK`) e os `AuditEvent`
(`OPPORTUNITY_CREATED`/`OPPORTUNITY_TRANSITIONED`/`JOB_ENQUEUED`/
`WORKFLOW_NEXT_JOB_ENQUEUED`) na **mesma transação**, então um crash não deixa
Opportunity sem próximo Job; uma transição válida atualiza a linha com um `UPDATE`
condicional otimista e uma transição inválida grava
`OPPORTUNITY_TRANSITION_REJECTED` antes de retornar o erro (AUT-010, AUT-141).

Implementação (TKT-17): a migration `0011_operations_control` acrescenta as tabelas
`operations_state` (linha única `id='global'` com `global_mode`,
`stop_external_actions`, motivo e `correlation_id`) e `integration_health` (uma
linha por integração, `name` como PK, `state`, `summary`), o índice
`ix_integration_health_state` (`state`, `updated_at`) e atualiza `schema_version`.
Diferente das tabelas append-only, ambas são mutáveis por desenho: o comando do
operador é um upsert gravado na **mesma transação** do `AuditEvent`
(`OPERATIONS_MODE_CHANGED`, `EXTERNAL_ACTIONS_STOPPED`/`RESUMED`,
`INTEGRATION_HEALTH_CHANGED`), então um crash não deixa estado sem trilha. A
decisão de autorização de side effect grava `EXTERNAL_ACTION_AUTHORIZED`/
`EXTERNAL_ACTION_BLOCKED` no `audit_event` (append-only) com o Correlation ID do
pipeline; leitura/diagnóstico/recovery nunca dependem de `operations_state`
(AUT-317). Timestamps em ISO-8601 UTC.

Implementação (TKT-18): a migration `0012_runtime_state` acrescenta a tabela
`runtime_state` (linha única `id='core'` com `clean_shutdown`, `started_at`,
`shutdown_at`, `last_recovery_at`, `recovery_count`) e atualiza `schema_version`.
O Recovery Manager lê/grava o marcador na **mesma transação** do `AuditEvent`
(`CLEAN_SHUTDOWN_RECORDED`, `UNCLEAN_SHUTDOWN_DETECTED`, `RECOVERY_STARTED`/
`COMPLETED`), então um crash não deixa estado sem trilha. Jobs interrompidos são
reconciliados com `UPDATE` condicional atômico + audit
(`RECOVERY_JOB_REQUEUED`/`RECOVERY_JOB_BLOCKED`) e locks órfãos com
`RECOVERY_LOCK_CLEARED`; um job de side effect externo de resultado desconhecido
é bloqueado, nunca reenviado. O startup segue `load config → validate → load
knowledge → validate → database check → migrations check → recovery → workers`:
`radarctl recover`/`POST /recovery` executa a etapa de recovery e a fiação
systemd pertence a RDR-117.

Implementação (TKT-19): a migration `0013_ai_review` acrescenta a tabela
`ai_review` (append-only via triggers `trg_ai_review_no_update`/`_no_delete`, com
FK para `candidate`/`evaluation`/`audit_event`) e atualiza `schema_version`. Cada
linha é uma `AIReview` imutável: provider/model, `knowledge_version`/
`prompt_version`/`knowledge_hash`, a decisão editorial
(`APPROVE`/`REVIEW`/`REJECT`) e os `allowed_claims`/input snapshot como JSON. A
review é gravada na **mesma transação** do seu `AuditEvent` `AI_REVIEW_RECORDED`,
então uma falha do provider (rede/recusa/schema inválido) não deixa registro
parcial. Texto de marketplace é persistido sanitizado (sem HTML bruto, sem
segredos) e dinheiro como string decimal. Ver `docs/04_DATA_CONTRACTS.md`.

Implementação (TKT-20): a migration `0014_affiliate_link` acrescenta a tabela
`affiliate_link` (FK para `opportunity`/`audit_event`, constraint única
`uq_affiliate_link_opportunity_tracking` e índice `ix_affiliate_link_opportunity`)
e atualiza `schema_version`. Cada linha é um `AffiliateLink` próprio com a URL
original, a URL afiliada **literal** retornada pelo provider, o método de geração,
o status, `productive` e o `TrackingContext` interno separado da etiqueta externa.
A geração é idempotente por Opportunity + etiqueta (a constraint única garante que
uma corrida não crie dois links) e grava o `AuditEvent`
`AFFILIATE_LINK_GENERATED` na **mesma transação**, então uma falha de provider ou
um link inválido não deixa registro parcial. A `affiliate_link` não é append-only
porque a entidade tem `status`/lifecycle; a trilha de auditoria é o
`audit_event`. Ver `docs/04_DATA_CONTRACTS.md`.

Implementação (TKT-21): a migration `0015_content_generation` acrescenta a tabela
`content_generation` (append-only via triggers `trg_content_generation_no_update`/
`_no_delete`, com FK para `opportunity`/`candidate`/`audit_event` e índice
`ix_content_generation_opportunity`) e atualiza `schema_version`. Cada linha é uma
`ContentGeneration` versionada com o conteúdo gerado (headline/body/cta) e o
conteúdo final renderizado (preço, URL afiliada literal, disclosure, tracking)
guardados **separadamente**, além de `generation_version`/`knowledge_version`/
`prompt_version`/`renderer_version` e do snapshot `facts`/`fact_hash`. A preview é
gravada na **mesma transação** do seu `AuditEvent` `CONTENT_GENERATION_RECORDED`,
então uma falha de provider, uma URL inventada pela IA ou um guard (número/claim sem
Evidence) não deixa registro parcial. A linha nunca é mutada: `STALE` é derivado na
leitura comparando o `fact_hash` com os fatos atuais (última observação de preço,
link vigente, versão de knowledge/prompt). A migration `0016_ai_input_cache`
(TKT-22, RDR-055) acrescenta a coluna `ai_input_hash` (hash canônico do input
versionado do provider) e o índice `ix_content_generation_ai_input`, usados para
reusar um resultado persistido equivalente sem nova chamada ao provider; linhas
anteriores ficam com hash vazio e nunca casam. Ver `docs/04_DATA_CONTRACTS.md`.

Implementação (TKT-23): a migration `0017_publication` acrescenta a tabela
`publication` (FK para `opportunity`/`content_generation`/`affiliate_link`/
`audit_event`, constraint única `uq_publication_idempotency_key` e índices
`ix_publication_opportunity`/`ix_publication_published`) e a tabela append-only
`publication_event` (triggers `trg_publication_event_no_update`/`_no_delete`, FK
para `publication` e índice `ix_publication_event_publication`), atualizando
`schema_version`. Cada `publication` é o side effect confirmado de uma
`ContentGeneration` validada: destino, `external_message_id`, `published_price`,
`idempotency_key` e a referência às entidades próprias. A linha, seu histórico de
eventos e o `AuditEvent` `PUBLICATION_RECORDED` são gravados na **mesma
transação**; repetir o `idempotency_key` é rejeitado pela constraint (e a
fronteira devolve a Publication existente sem novo envio). `publication` não é
append-only porque a entidade tem `status`/lifecycle; a trilha imutável é
`publication_event`. O resultado desconhecido pós-crash e a reconciliação
pertencem a TKT-24/ADR 0001. Ver `docs/04_DATA_CONTRACTS.md`.

## Append-only

Não sobrescrever:
- PriceObservation;
- Evaluation;
- PurchaseSourceDecision;
- RepostDecision;
- AIReview;
- ContentGeneration;
- HumanReview;
- PublicationEvent;
- Domain/Audit events.

## Estrutura persistente alvo

```text
data/
  radar.db
  backups/

config/
knowledge/
logs/
diagnostics/
migrations/
runtime/
```

Código e dados persistentes devem permanecer separados.

## Config

Separar:
- `config`, comportamento operacional;
- `knowledge`, comportamento editorial/contextual.

Config deve ser validada por schema e versionada/hash.

Mudanças importantes geram snapshot.

Hot reload permitido para:
- thresholds;
- publishing caps;
- quiet hours;
- kill switches;
- automation modes;
- category weights.

Implementação (RDR-004): `config/radar.json` é JSON opcional, validado por schema com `extra=forbid`; precedência `defaults < arquivo < variáveis RADAR_*`. `radarctl config` e `GET /config` publicam `schema_version`, `config_hash` (SHA-256 do JSON canônico) e referências de secret por nome, nunca valores. Snapshot de mudanças relevantes e hot reload permanecem tickets próprios.

## Secrets

Nunca em:
- Git;
- YAML comum;
- banco comum;
- logs;
- backup;
- Knowledge Pack;
- prompt.

Usar `SecretsProvider` com armazenamento seguro do OS/usuário.

Implementação (RDR-005): o protocolo `SecretsProvider` é implementado por `EnvironmentSecretsProvider` (lê `RADAR_SECRET_<NOME>`, com referência explícita opcional via config). `ScopedSecrets` aplica menor privilégio por componente: pedido fora da allowlist falha com `RAD-CFG-004` e secret ausente com `RAD-CFG-003`, bloqueando somente a capability afetada. O provider não escreve em config/banco; todo valor lido é registrado no redator de logs.

Sessões ML/Shopee/WhatsApp ficam exclusivamente no browser profile.

## Browser profile

É runtime state, não dado canônico.

Pode ser recriado:
- novo profile;
- instalar extensão;
- parear;
- autenticar serviços.

## Logs

Application logs estruturados em JSON.

Audit events persistentes separados.

Nunca logar:
- password;
- authorization;
- cookies;
- OAuth tokens;
- API secrets;
- pairing secret.

Implementação (RDR-008): `configure_logging` emite JSON estruturado no `radar` logger (stderr) com `correlation_id` do contexto; `JsonLogFormatter` redige valores de secret registrados pelo provider e mascara campos sensíveis por nome (`password`, `authorization`, `cookie(s)`, `token`, `secret`, `api_key`, `pairing_secret`, etc.). Audit events continuam persistentes e separados.

## Retenção inicial

- browser screenshots: 7 dias
- debug logs: 14 dias
- application logs: 30 dias
- audit/domain events: permanente
- price history: permanente
- publications: permanente

## Backup

Usar mecanismo consistente de backup do SQLite.

Pacote:
```text
backup_TIMESTAMP/
├── radar.db
├── config/
├── knowledge/
├── manifest.json
└── checksums.sha256
```

Excluir:
- secrets;
- cookies;
- browser profile;
- diagnostics temporários;
- caches.

Retenção inicial:
- 7 diários;
- 4 semanais;
- 3 mensais.

Ao menos uma cópia deve ficar fora da VM, no host.

## Restore

Operação explícita:
```text
PAUSE
→ validate backup
→ safeguard current state
→ restore db/config/knowledge
→ migrations se necessárias
→ integrity check
→ recovery
→ retomar diagnóstico e processamento seguro com envios bloqueados
→ reconciliar intervalo posterior ao backup
→ liberar envios sujeitos às políticas vigentes
```

Restore nunca é automático.

Um backup pode não conter publicações realizadas após sua criação. A ausência de um registro no banco restaurado não prova que o envio remoto não ocorreu. Até reconciliar esse intervalo, manter os envios bloqueados, inclusive jobs recuperados e novas publicações. Registrar a evidência e a decisão de reconciliação em auditoria; resultados desconhecidos suspendem a publicação afetada e geram HumanAction, sem reenvio automático, conforme `adr/0001-unknown-publication-result.md`.

Após desastre completo, sessões/secrets precisam ser reconfigurados.

## Startup validation

```text
load config
→ validate
→ load knowledge
→ validate
→ database check
→ migrations check
→ recovery
→ workers
```

Migration failure impede side effects.

## Upgrade

```text
DRAINING
→ backup
→ stop
→ update code
→ dependency sync
→ migrate
→ integrity check
→ restart
→ doctor
```

## Time and money

Dedupe/receipt/vínculo de destino e auditoria persistem independentemente de mensagens temporárias WA, cache ou bubble removido. Retenção não pode apagar proteção necessária contra reenvio/reconciliação; restore segue bloqueio dos envios até reconciliar intervalo pós-backup.

- timestamps persistidos em UTC;
- timezone operacional configurado, alvo `America/Maceio`;
- dinheiro não usa floating point binário como representação de domínio.

## Low disk

Primeiro limpar:
- diagnostics expirados;
- logs;
- temp.

Persistindo nível crítico:
- pausar discovery;
- HumanAction.
