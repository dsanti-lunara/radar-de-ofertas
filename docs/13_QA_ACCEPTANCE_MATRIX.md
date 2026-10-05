# 13, QA and Acceptance Matrix

## Camadas

1. Unit
2. Contract
3. Integration
4. E2E

Quanto mais externa a camada, menor o volume.

## Testes obrigatórios por domínio

### Scoring

Range Shopee/card/desconto riscado não prova preço de variante nem histórico independente. CHALLENGE ou dados atuais indisponíveis impedem revalidação pré-envio; cache não substitui essa evidência.
- boundaries 59.99/60/79.99/80;
- hard rules precedem scores;
- comissão nunca aumenta Deal Score;
- Deal permanece 0..100;
- dinheiro sem erro de float;
- Confidence por source/freshness/history;
- purchase source guardrail;
- dedupe/repost.

### AI
- schema válido;
- schema inválido;
- enum inválido;
- timeout;
- refusal;
- rate limit;
- prompt injection;
- numeric hallucination;
- unsupported claims;
- URL inventada;
- Golden Dataset;
- adversarial dataset.

Não testar frase exata, testar propriedades.

### Database
- real temporary SQLite;
- WAL;
- FK;
- constraints;
- migrations empty→latest;
- migration N→N+1;
- rollback transacional;
- backup/restore.
- restore de backup anterior a envio remoto: diagnóstico/processamento seguro retomam, envios permanecem bloqueados até reconciliação;
- jobs restaurados e novas publicações não enviam durante esse bloqueio; ausência de registro local não autoriza reenvio;
- reconciliação pós-restore registra evidência/decisão em auditoria; resultado desconhecido gera HumanAction sem reenvio automático.

### Workflow

Shopee API: 200 com errors/partial data falha fechado; Int64/Decimal preservados, assinatura de bytes exatos, paginação específica, 10020 por reason, 10030/backoff e 10035/entitlement. Mutation unknown não recebe retry cego. ML: etiqueta charset/30/unicidade, resultado stale, social landing com outro produto destacado e contexto catálogo/anúncio errado devem falhar.
- retry;
- no retry em AUTH_REQUIRED;
- Dead Job;
- lock;
- lease expiration;
- missed schedule coalescing;
- candidate aging;
- TTL;
- content staleness;
- recovery pós-crash.

### Browser

Recon 2026-10-02 fornece 14 verificações de artefatos, não aceite de adapters. Registry/fallbacks candidatos precisam de testes completos, negativos e SAFE_LIVE no Chrome dedicado/VM antes de SIDE_EFFECT autorizado. CHALLENGE suspende somente parte afetada e exige revalidação na retomada.
Níveis:
- FIXTURE
- SAFE_LIVE
- SIDE_EFFECT

Adapter acceptance:
- fixture pass;
- primary/fallback selector;
- ambiguous selector fail closed;
- DOM_CHANGED;
- AUTH_REQUIRED;
- wrong product/context;
- safe live;
- sandbox side effect quando aplicável.

### Telegram
- resultado remoto desconhecido: registro persistente, publicação suspensa, zero reenvio automático e HumanAction;
- revisão sem evidência suficiente não autoriza nova tentativa;
- send;
- edit;
- invalid destination;
- retry;
- idempotency;
- crash after remote send before local commit;
- lifecycle revision.

### WhatsApp

- GROUP allowlisted, marca e ambiente corretos; homônimos, vínculo ausente/inválido ou troca após preview produzem zero clique;
- serializer canônico multiline/preview/hash; innerText/textContent não são contrato implícito;
- Send ausente/duplicado e marker/status pós-envio ausentes;
- Enviada não comprova entregue/lida; receipt deve corresponder à publication/revision e tentativa;
- crash após envio antes de commit, reload/reconnect/MV3 e mensagem temporária de sete dias preservam dedupe;
- resultado desconhecido suspende e gera HumanAction, sem reenvio automático; restore mantém bloqueio GRILL-003.
- sandbox destination;
- destination mismatch blocks;
- message hash mismatch blocks;
- auth required;
- assisted send;
- duplicate prevention.

### Security
- SHADOW: aprovação de Candidate/publicação não causa envio comercial;
- ASSISTED: aprovação de Candidate não autoriza envio; publicação exige aprovação humana explícita e guardrails vigentes;
- invalid bridge token;
- replayed nonce;
- unauthorized host;
- javascript URL;
- unsupported command;
- destination/brand mismatch;
- secret leakage scan;
- policy block;
- prompt injection;
- duplicate publication.

## Acceptance scenarios

| ID | Cenário | Resultado |
|---|---|---|
| A | Shopee happy path | 1 publicação correta, link/preço/disclosure/tracking corretos |
| B | Deal 45, Monetization 97 | REJECT, sem IA/link/publicação |
| C | preço 79→109 antes do envio | revalidate, rescore, bloquear |
| D | IA escreve preço errado | Numeric Guard bloqueia |
| E | Shopee auth expira | só browser Shopee pausa, restante continua |
| F | WhatsApp está no grupo/vínculo errado | DESTINATION_MISMATCH, zero envio |
| G | Core cai no publishing | reconcile, zero duplicação |
| H | VM reinicia | startup/recovery/schedule coalesced |
| I | restore | histórico volta, secrets/sessions não |
| J | marketplace muda DOM | DOM_CHANGED, circuit breaker, zero clique errado |
| K | prompt injection no produto | contrato preservado, zero secret/execução |
| L | compliance bloqueada | side effect bloqueado mesmo com scores altos |

## Quality gates

### Feature Done
- implementation complete;
- tests pass;
- acceptance pass;
- docs atualizadas;
- nenhum defeito crítico conhecido.

### PR
- format/lint;
- types;
- unit;
- contract;
- integração relevante;
- security relevante.

### Release
- tests;
- migration test;
- backup;
- version tag;
- release notes;
- browser tests se adapter mudou.

## Live tests

Nunca rodam por padrão.

Markers sugeridos:
- unit
- contract
- integration
- browser_live
- ai_live
- telegram_live
- whatsapp_live
- slow

`RADAR_TEST_MODE` deve bloquear destino de produção.

## Shadow gates

Telegram, referência inicial:
- >=50 human-reviewed cases;
- >=90% ordinary agreement;
- 0 P0;
- 0 P1 nos últimos 30 casos;
- 0 duplicate publish;
- 0 invalid affiliate link;
- 100% disclosure.

WhatsApp deve ter gate mais rigoroso e histórico de assisted publications estáveis.

Números são configuráveis/calibráveis, mas o gate é obrigatório.

## Severity

P0:
- destino errado;
- link de produto errado;
- secret leak;
- publicação proibida por compliance.

P1:
- preço factual errado;
- duplicate publication;
- claim comercial grave não sustentado.

P2/P3:
- problemas não críticos de classificação, copy ou UI.

P0 impede AUTO/release.

## Soak

Antes de produção:
- 24h Shadow;
- depois 72h ou período estendido quando próximo da ativação.

Observar:
- memory growth;
- queue leak;
- stuck jobs;
- duplicates;
- browser stability;
- auth;
- log growth.

## Homologação no notebook real

Obrigatório testar:
- VM boot;
- auto-start;
- browser start;
- bridge heartbeat;
- sessions;
- AI;
- Telegram;
- WhatsApp;
- host backup;
- browser restart;
- network outage;
- abrupt process/VM termination.

## QA traceability

Toda decisão crítica deve poder ser ligada a:
`Requirement → Test → Acceptance → Evidence`.

O agente deve expandir esta matriz com IDs de testes reais durante a implementação.

## Foundation traceability, TKT-01 (RDR-001, RDR-002, RDR-003, RDR-006, RDR-007, RDR-009, RDR-010)

Escopo: iniciar Core/API locais com banco migrado e consultar saúde por CLI/API, com toolchains Python/TypeScript verificáveis. Camadas `unit`, `contract` e `integration` com SQLite temporário real; nenhum teste live ou credencial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-001 bootstrap monorepo | `tests/test_settings.py`, `packages/radar-contracts/src/health.test.ts` | Toolchains fixadas executam lint/types/testes | `uv sync`; `pnpm install`; árvores `src/radar`, `migrations`, `packages/radar-contracts` |
| RDR-002 Python quality toolchain | suíte `tests/` (29 casos) | lint/types/testes seguros sem credenciais | `uv run ruff check .`; `uv run ruff format --check .`; `uv run pyright`; `uv run pytest` |
| RDR-003 TypeScript workspace | `packages/radar-contracts/src/health.test.ts` (6 casos) | TS strict + lint + testes | `pnpm lint`; `pnpm typecheck`; `pnpm test` |
| RDR-006 SQLite + SQLAlchemy | `tests/test_database_migration.py::test_wal_and_foreign_keys_active`, `::test_foreign_keys_are_enforced` | Banco vazio com FK/WAL ativos | `PRAGMA journal_mode=wal` e `PRAGMA foreign_keys=1` por conexão; violação de FK levanta `IntegrityError` |
| RDR-007 Alembic migrations | `tests/test_database_migration.py::test_empty_database_migrates_to_head`, `::test_migration_is_idempotent`, `::test_bootstrap_table_records_schema_version` | Banco vazio migra até latest | `radarctl migrate`; revisão `0001_initial` == head |
| RDR-009 radarctl skeleton | `tests/test_cli.py` (6 casos) | Saúde consultável por CLI | `radarctl status` (exit 0 só quando operacional), `radarctl migrate`, `radarctl version` |
| RDR-010 system health model | `tests/test_health_model.py`, `tests/test_health_database.py`, `tests/test_api_health.py` | Status diferencia banco indisponível de serviço saudável | `GET /health` 200 `HEALTHY` vs 503 `UNHEALTHY` (`RAD-DB-003`); `SystemHealth` com `schema_version` e `correlation_id` |

### Acceptance evidence, TKT-01

| Acceptance criterion | Verification |
|---|---|
| Banco vazio migra até latest e FK/WAL ativos | `tests/test_database_migration.py` (5 casos) |
| Status diferencia banco indisponível de serviço saudável | `tests/test_health_database.py` (3), `tests/test_api_health.py` (4), `tests/test_cli.py` (6) |
| Toolchains fixadas executam lint/types/testes sem credenciais | comandos Python/TypeScript acima, todos sem secrets |
| Comportamento pela fronteira pública, sem enfraquecer teste/guardrail | `GET /health`, `GET /version`, `radarctl status|migrate|version`; probes falham fechados |
| Docs/contratos e matriz QA atualizados | este documento, `docs/ERROR_CATALOG.md`, `docs/INSTALLATION.md` |

Limitações e blockers remanescentes: apenas a fronteira de fundação (`radar-core`/`radar-api` como processos systemd, `doctor`, controles operacionais e entidades de domínio) pertencem a tickets próprios; nenhuma capability foi promovida para AUTO e nenhum teste live/credenciado foi executado.

## Foundation traceability, TKT-02 (RDR-004, RDR-005, RDR-008)

Escopo: carregar e validar configuração, acessar secrets por referência segura (menor privilégio) e emitir logs JSON sanitizados com Correlation ID. Camadas `unit` e `contract`; nenhum teste live, credencial real, banco criado por `radarctl config` ou provider externo.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-004 configuration loader | `tests/test_config.py` (14 casos: defaults, env over file, hash, inválidos, JSON malformado, referência de secret) | Config validada por schema, versionada e com hash; inválida bloqueia execução com erro acionável | `radarctl config`; `RAD-CFG-001`/`RAD-CFG-002`; `schema_version=1.0` |
| RDR-005 SecretsProvider | `tests/test_secrets.py::test_provider_satisfies_protocol_and_returns_none_when_absent`, `::test_scoped_require_missing_blocks_capability`, `::test_scoped_access_outside_allowlist_fails_closed`, `::test_provider_has_no_persistence_side_effects` | Acesso least-privilege; secret ausente bloqueia a capability; nada persistido em config/banco/logs | `RAD-CFG-003`/`RAD-CFG-004`; `Secret` mascarado em `repr`/`str` |
| RDR-008 structured logging | `tests/test_logging.py` (5 casos: Correlation ID, redação de valor registrado, campos sensíveis, reconfiguração) | Logs JSON sanitizados com Correlation ID em stderr | `configure_logging` + `JsonLogFormatter` |

### Acceptance evidence, TKT-02

| Acceptance criterion | Verification |
|---|---|
| Config inválida impede execução com erro acionável | `tests/test_config.py::test_invalid_config_is_actionable`; `tests/test_cli_config.py::test_config_reports_invalid_configuration`, `::test_invalid_configuration_blocks_other_commands`; `tests/test_api_config.py::test_invalid_configuration_blocks_app_creation` |
| SecretsProvider não grava secrets em config/banco/logs | `tests/test_secrets.py::test_provider_has_no_persistence_side_effects`; `tests/test_config.py::test_config_contract_exposes_secret_references_only`; `tests/test_cli_config.py::test_config_reports_secret_presence_without_leaking_value` |
| Secret falso não aparece em logs nem exceções; Correlation ID preservado | `tests/test_logging.py`; `tests/test_secrets.py::test_secret_repr_and_str_are_masked`; `tests/test_cli_config.py::test_config_error_never_echoes_environment_secret` (Correlation ID no contrato e no log) |
| Comportamento pela fronteira pública, sem enfraquecer teste/guardrail | `radarctl config` (stdout versionado + logs JSON em stderr) e `GET /config`; config inválida bloqueia CLI e criação da API |
| Docs/contratos e matriz QA atualizados | este documento, `docs/ERROR_CATALOG.md`, `docs/04_DATA_CONTRACTS.md`, `docs/INSTALLATION.md`, `README.md`, `docs/10_PERSISTENCE_AND_RECOVERY.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-02. Limitações e blockers remanescentes: as capabilities reais (Telegram, IA, Shopee, WhatsApp) ainda não consomem `ScopedSecrets`, portanto o escopo de menor privilégio por componente é comprovado por contrato/teste e será ligado nos tickets dependentes; o provider concreto atual lê do ambiente (`EnvironmentSecretsProvider`) e o backend de armazenamento seguro do SO (keyring) permanece gate de RDR-005; `config/radar.json` é opcional e não é criado por `radarctl config`; nenhum teste live/credenciado foi executado e nenhuma capability foi promovida para AUTO.
