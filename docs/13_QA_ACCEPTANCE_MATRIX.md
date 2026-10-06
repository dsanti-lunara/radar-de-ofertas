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

## Foundation traceability, TKT-03 (RDR-011, RDR-012, RDR-014, RDR-015, RDR-021)

Escopo: receber uma captura manual versionada pela fronteira pública, sanitizar/validar, persistir `RawCapture`/`Evidence` e materializar `Product`, `MarketplaceProduct`, `Offer`, `DiscoveryEvent`, `Candidate` e `AuditEvent`; consultar o Candidate resultante. Camadas `unit`, `contract` e `integration` com SQLite temporário real; relógio e gerador de id controlados; nenhum teste live, credencial, provider externo ou side effect comercial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-011 Product | `tests/test_capture_persistence.py::test_capture_materializes_distinct_entities` | Product distinto de MarketplaceProduct, Offer e Candidate | `product` persistido com `canonical_name`; id próprio no contrato |
| RDR-012 MarketplaceProduct + Offer | `tests/test_capture_persistence.py::test_repeated_capture_does_not_duplicate_identity`, `::test_unique_constraint_blocks_duplicate_identity` | `marketplace + external_id` único; captura repetida não duplica identidade; Offer é nova condição | constraint `uq_marketplace_product_identity`; `offer` = 2, `marketplace_product` = 1 |
| RDR-014 Evidence + RawCapture | `tests/test_capture_persistence.py::test_raw_capture_is_sanitized_and_evidence_is_persisted` | Payload estruturado sanitizado (sem HTML); Evidence com proveniência | `raw_capture.payload`; linhas de `evidence` com `source_type`/`raw_reference` |
| RDR-015 DiscoveryEvent + Candidate | `tests/test_capture_persistence.py::test_capture_materializes_distinct_entities` | Captura registra origem e coloca Candidate no pipeline | `discovery_event` e `candidate` (state `NEW`) |
| RDR-021 Audit/Domain events | `tests/test_capture_persistence.py::test_discovery_event_and_audit_preserve_source_and_correlation` | Evento de auditoria append-only preserva fonte e Correlation ID | `audit_event` com `event_type=CAPTURE_RECEIVED`, `source` e `correlation_id` |
| API pública de captura | `tests/test_api_capture.py::test_manual_capture_roundtrip`, `::test_correlation_id_is_generated_when_absent` | Captura e consulta versionadas pela API com Correlation ID | `POST /captures/manual` 201; `GET /candidates/{id}` 200; `schema_version=1.0` |

### Acceptance evidence, TKT-03

| Acceptance criterion | Verification |
|---|---|
| marketplace + external_id é único e captura repetida não duplica identidade | `tests/test_capture_persistence.py::test_repeated_capture_does_not_duplicate_identity`, `::test_unique_constraint_blocks_duplicate_identity`; `tests/test_api_capture.py::test_repeated_capture_does_not_duplicate_identity` |
| Offer, Product, MarketplaceProduct e Candidate são distintos | `tests/test_capture_persistence.py::test_capture_materializes_distinct_entities`; `tests/test_api_capture.py::test_manual_capture_roundtrip` (4 ids distintos) |
| Payload inválido ou sensível é rejeitado/sanitizado sem escrita parcial | `tests/test_api_capture.py::test_sensitive_payload_is_rejected_without_writing`, `::test_invalid_payload_returns_structured_error`, `::test_extra_unknown_field_is_rejected`, `::test_title_and_text_are_sanitized`; `tests/test_capture_persistence.py::test_invalid_capture_stops_before_persisting`; `tests/test_capture_domain.py` (sanitização/parse/URL) |
| DiscoveryEvent e auditoria preservam fonte e Correlation ID | `tests/test_capture_persistence.py::test_discovery_event_and_audit_preserve_source_and_correlation`; `tests/test_api_capture.py::test_manual_capture_roundtrip` |
| Comportamento pela fronteira pública, sem enfraquecer teste/guardrail | API `POST /captures/manual` e `GET /candidates/{id}`; erros estruturados `RAD-CAP-001..004`; sanitização e recusa de campos sensíveis antes da persistência |
| Docs/contratos e matriz QA atualizados | este documento, `docs/ERROR_CATALOG.md`, `docs/04_DATA_CONTRACTS.md`, `docs/03_DOMAIN_MODEL.md`, `docs/10_PERSISTENCE_AND_RECOVERY.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-03. Limitações e blockers remanescentes: `PriceObservation`/histórico de preços pertence a RDR-013/TKT-04 e não é criado aqui; `Evidence.confidence` fica nula até o Confidence Engine (RDR-029); não há resolução de `Product` entre marketplaces nem `brand`/`category` normalizados (tickets próprios); a dedupe é sequencial e uma corrida concorrente falha fechado com `RAD-CAP-003` (retryable); nenhum teste live/credenciado foi executado e nenhuma capability foi promovida para AUTO.

## Foundation traceability, TKT-04 (RDR-013)

Escopo: acrescentar observações monetárias append-only ao `MarketplaceProduct` durante a captura normalizada e consultar a série com proveniência. Camadas `unit`, `contract` e `integration` com SQLite temporário real, relógio/id controlados; nenhum teste live, credencial, provider externo ou side effect comercial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-013 PriceObservation append-only | `tests/test_price_history_persistence.py::test_capture_appends_price_observation_with_provenance`, `::test_previous_observations_are_never_overwritten` | Observação criada na captura; a anterior nunca é sobrescrita | `price_observation` (2 linhas, primeira preservada); `observed_at`/`price` originais |
| Identidade documentada da observação | `tests/test_price_history_domain.py::test_price_observation_identity_is_stable_across_timezones`, `::test_price_observation_identity_distinguishes_source_and_instant`; `tests/test_price_history_persistence.py::test_repeated_capture_with_same_identity_reuses_observation`; `tests/test_api_price_history.py::test_repeated_identical_capture_keeps_single_observation` | Captura repetida segue `(marketplace_product_id, source, observed_at)` e reutiliza a observação sem inventar novo preço | constraint `uq_price_observation_identity`; 1 linha e mesmo `price_observation_id` na repetição |
| Dinheiro decimal e timestamps UTC | `tests/test_price_history_domain.py::test_price_history_contract_serializes_decimal_and_utc`; `tests/test_price_history_persistence.py::test_price_observation_money_is_decimal_and_timestamps_are_utc` | Preço é string decimal (`Decimal` no domínio) e `observed_at` é UTC | `price = "79.90"` (str) e `observed_at` com `+00:00` |
| FK e rollback no banco real | `tests/test_price_history_persistence.py::test_price_observation_foreign_key_is_enforced`, `::test_failed_capture_rolls_back_price_observation`; `tests/test_database_migration.py::test_migration_adds_price_observation_from_capture_revision`, `::test_downgrade_reverts_capture_schema` | FKs de `price_observation` verificadas; transação falha sem escrita parcial; migration N→N+1 | `IntegrityError` na FK; `price_observation`/`offer`/`marketplace_product` inalterados após `RAD-CAP-003`; revision `0003_price_observation` |
| API pública de histórico | `tests/test_api_price_history.py::test_price_history_returns_series_with_provenance`, `::test_unknown_marketplace_product_returns_structured_404`; `tests/test_price_history_persistence.py::test_price_history_not_found_raises_structured_error` | Série consultável e versionada com Correlation ID e erro estruturado | `GET /marketplace-products/{id}/price-history` 200 `schema_version=1.0`; 404 `RAD-CAP-005` |

### Acceptance evidence, TKT-04

| Acceptance criterion | Verification |
|---|---|
| Observações anteriores nunca são sobrescritas | `tests/test_price_history_persistence.py::test_previous_observations_are_never_overwritten` |
| Dinheiro não usa float binário e timestamps são UTC | `tests/test_price_history_domain.py::test_price_history_contract_serializes_decimal_and_utc`; `tests/test_price_history_persistence.py::test_price_observation_money_is_decimal_and_timestamps_are_utc` |
| Captura repetida segue identidade documentada sem inventar novo preço | `tests/test_price_history_persistence.py::test_repeated_capture_with_same_identity_reuses_observation`; `tests/test_api_price_history.py::test_repeated_identical_capture_keeps_single_observation` |
| Banco real verifica FK e rollback | `tests/test_price_history_persistence.py::test_price_observation_foreign_key_is_enforced`, `::test_failed_capture_rolls_back_price_observation` |
| Comportamento pela fronteira pública, sem enfraquecer teste/guardrail | `POST /captures/manual` retorna `price_observation_id`; `GET /marketplace-products/{id}/price-history`; erro `RAD-CAP-005` |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/10_PERSISTENCE_AND_RECOVERY.md`, `docs/ERROR_CATALOG.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-04. Limitações e blockers remanescentes: `shipping_cost` permanece nulo até existir captura de frete (ticket próprio); a série ainda não alimenta o Price Opportunity/Deal Score (RDR-023/RDR-027, tickets próprios) nem o Confidence Engine (RDR-029); a dedupe é sequencial pela identidade única e uma corrida concorrente na mesma identidade falha fechado no banco; nenhum teste live/credenciado foi executado e nenhuma capability foi promovida para AUTO.

## Foundation traceability, TKT-05 (RDR-022, RDR-026)

Escopo: classificar a categoria bruta de um Candidate contra a taxonomia
versionada das marcas e resolver Brand Fit explicável, com lacunas explícitas e
Hard Rule para categoria fora de escopo. Camadas `unit`, `contract` e
`integration` com SQLite temporário real; relógio/id controlados; nenhum teste
live, credencial, provider externo ou side effect comercial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-022 Brand taxonomy | `tests/test_taxonomy_domain.py::test_approved_taxonomy_carries_radar_beauty_values`, `::test_approved_taxonomy_does_not_invent_casa_em_ordem_brand_fit`, `::test_approved_taxonomy_is_versioned_and_hashed`; `tests/test_taxonomy_config.py::test_loader_without_file_returns_approved_taxonomy`, `::test_loader_reads_versioned_file` | Taxonomia versionada/hasheada e carregada de configuração validada | `taxonomy_version`/`taxonomy_hash` no contrato; `config/brand-taxonomy.json` |
| RDR-026 Brand Fit | `tests/test_api_classification.py::test_radar_beauty_brand_fit_uses_approved_values` (6 categorias), `::test_capture_persists_raw_category`, `::test_repeated_capture_updates_raw_category_without_duplicating_identity`; `tests/test_taxonomy_domain.py::test_radar_beauty_brand_fit_is_explainable` | Brand Fit segue valores aprovados e configuração versionada | `GET /candidates/{id}/classification/{brand}` 200; `brand_fit`/`priority`/`taxonomy_hash` |
| Escopo das marcas | `tests/test_api_classification.py::test_casa_em_ordem_priorities_respect_scope_and_report_calibration_gap`, `::test_out_of_scope_category_emits_hard_rule`; `tests/test_taxonomy_domain.py::test_out_of_scope_category_emits_hard_rule` | Categorias/prioridades respeitam escopo; fora de escopo → Hard Rule | `hard_rules=[OUT_OF_SCOPE_CATEGORY]`; prioridade de Casa em Ordem |
| Lacuna explícita | `tests/test_api_classification.py::test_undefined_mapping_is_explicit_gap`, `::test_missing_category_is_explicit_gap`; `tests/test_taxonomy_domain.py::test_undefined_mapping_is_explicit_gap_without_invented_value`, `::test_missing_category_is_explicit_gap`, `::test_casa_em_ordem_calibration_gap_is_explicit` | Mapeamento/calibração ausente não recebe valor inventado | `warnings=[CATEGORY_MAPPING_NOT_DEFINED/CATEGORY_NOT_PROVIDED/BRAND_FIT_CALIBRATION_REQUIRED]`; `brand_fit=null`; `calibrated=false` |
| Config incompleta falha fechado | `tests/test_taxonomy_config.py::test_loader_invalid_json_fails_closed`, `::test_loader_invalid_document_fails_closed`, `::test_loader_explicit_missing_file_fails_closed`; `tests/test_taxonomy_domain.py::test_build_taxonomy_rejects_missing_version`, `::test_build_taxonomy_rejects_unknown_brand`, `::test_build_taxonomy_rejects_unknown_category`, `::test_build_taxonomy_rejects_out_of_range_brand_fit`, `::test_build_taxonomy_rejects_alias_to_unknown_category` | Config de taxonomia inválida não é apresentada como validada | `RAD-CFG-005`; API bloqueada na criação |
| API pública e erros | `tests/test_api_classification.py::test_unknown_brand_returns_structured_error`, `::test_taxonomy_version_mismatch_returns_structured_error`, `::test_candidate_not_found_returns_structured_404`, `::test_classification_correlation_id_is_generated_when_absent` | Fronteira pública versionada com Correlation ID e erro estruturado | `RAD-CAP-004/006/007`; header `X-Correlation-ID`; `Cache-Control: no-store` |

### Acceptance evidence, TKT-05

| Acceptance criterion | Verification |
|---|---|
| Categorias e prioridades respeitam escopo das marcas | `tests/test_api_classification.py::test_radar_beauty_brand_fit_uses_approved_values`, `::test_casa_em_ordem_priorities_respect_scope_and_report_calibration_gap`; `tests/test_taxonomy_domain.py::test_approved_taxonomy_carries_radar_beauty_values` |
| Brand Fit segue valores aprovados e configuração versionada | `tests/test_api_classification.py::test_radar_beauty_brand_fit_uses_approved_values`; `tests/test_taxonomy_config.py::test_loader_reads_versioned_file`; hash estável em `tests/test_taxonomy_domain.py::test_content_hash_changes_with_content_and_is_stable` |
| Mapeamentos não definidos não recebem valor inventado | `tests/test_api_classification.py::test_undefined_mapping_is_explicit_gap`, `::test_missing_category_is_explicit_gap`; `tests/test_taxonomy_domain.py::test_casa_em_ordem_calibration_gap_is_explicit` |
| Categoria fora de escopo resulta em Hard Rule no contrato de avaliação | `tests/test_api_classification.py::test_out_of_scope_category_emits_hard_rule`; `tests/test_taxonomy_domain.py::test_out_of_scope_category_emits_hard_rule` |
| Comportamento pela fronteira pública, sem enfraquecer teste/guardrail | `GET /candidates/{id}/classification/{brand}`; erros `RAD-CAP-004/006/007`; nenhum teste/guardrail removido |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/05_SCORING_ENGINE.md`, `docs/ERROR_CATALOG.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-05. Limitações e blockers remanescentes: o Brand Fit de Casa em Ordem permanece **sem calibração aprovada** nos SDDs, portanto a classificação devolve `brand_fit=null` com `BRAND_FIT_CALIBRATION_REQUIRED` (lacuna explícita, requer decisão humana) e não inventa valor; a classificação é read-only e determinística, sem persistência própria — o snapshot versionado pertence à Evaluation (RDR-016); `Product.category`/resolução entre marketplaces e normalização por categoria (RDR-025/TKT-08) são tickets próprios; o resultado ainda não alimenta Deal Score (RDR-027) nem Confidence (RDR-029); nenhum teste live/credenciado foi executado e nenhuma capability foi promovida para AUTO.

## Foundation traceability, TKT-06 (RDR-023)

Escopo: calcular Price Opportunity consultável a partir do histórico append-only
e das condições confirmadas do Candidate, com breakdown versionado, preço
efetivo confiável e lacunas explícitas. Camadas `unit` e `contract` com SQLite
temporário real; nenhum teste live, credencial, provider externo ou side effect
comercial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-023 pesos e faixas | `tests/test_price_opportunity_domain.py::test_component_weights_follow_sdd`, `::test_historical_position_ranges_follow_sdd`, `::test_recent_price_drop_ranges_follow_sdd`, `::test_marketplace_comparison_ranges_follow_sdd` | Pesos 45/20/20/10/5 e faixas de histórico/queda/comparação seguem SDD-05 | componentes `historical_position`/`recent_price_drop`/`marketplace_comparison` com scores de borda; `docs/05_SCORING_ENGINE.md` |
| RDR-023 histórico insuficiente | `tests/test_price_opportunity_domain.py::test_insufficient_history_uses_neutral_and_warns`, `::test_insufficient_history_does_not_become_zero`; `tests/test_api_price_opportunity.py::test_insufficient_history_uses_neutral_50` | Histórico insuficiente usa neutro 50 e warning para Confidence | `warnings=[SHORT_PRICE_HISTORY, NO_PRICE_REFERENCE]`; `score=50`; `price_opportunity=50` |
| RDR-023 cupom | `tests/test_price_opportunity_domain.py::test_unconfirmed_coupon_does_not_reduce_effective_price`, `::test_confirmed_coupon_reduces_effective_price`, `::test_other_coupon_states_never_reduce_effective_price`; `tests/test_api_price_opportunity.py::test_unconfirmed_coupon_does_not_reduce_effective_price`, `::test_confirmed_coupon_reduces_effective_price` | Cupom não confirmado não reduz integralmente preço efetivo nem vira claim | `coupon.applied=false` e `effective_price` inalterado para LIKELY/UNKNOWN/NOT_APPLICABLE; CONFIRMED reduz; warning `COUPON_NOT_CONFIRMED` |
| RDR-023 frete/referência/preço riscado | `tests/test_price_opportunity_domain.py::test_unknown_shipping_is_explicit`, `::test_unknown_shipping_disables_marketplace_comparison`, `::test_absent_comparison_reference_is_explicit_and_neutral`, `::test_struck_through_price_is_not_proof_of_advantage`, `::test_struck_through_price_is_not_used_as_history_reference`; `tests/test_api_price_opportunity.py::test_unknown_shipping_is_explicit` | Frete desconhecido e referência insuficiente explícitos; preço riscado não prova vantagem | `effective_price=null`, `UNKNOWN_SHIPPING`, `NO_MARKETPLACE_REFERENCE`, `STRUCK_THROUGH_PRICE_NOT_PROOF`; `original_price` não altera scores |
| RDR-023 calibração pendente | `tests/test_price_opportunity_domain.py::test_coupon_and_shipping_components_are_explicit_calibration_gaps` | Componentes sem faixa aprovada não recebem valor inventado | `score=null`, `calibrated=false`, `weight_covered=85`, `fully_calibrated=false`, `PRICE_OPPORTUNITY_CALIBRATION_REQUIRED` |
| API pública e erros | `tests/test_api_price_opportunity.py::test_price_opportunity_returns_breakdown_with_provenance`, `::test_candidate_not_found_returns_structured_404`, `::test_invalid_coupon_state_returns_structured_422`, `::test_invalid_shipping_cost_returns_structured_422`, `::test_correlation_id_is_generated_when_absent` | Fronteira pública versionada com Correlation ID e erro estruturado | `GET /candidates/{id}/price-opportunity` 200 `schema_version=1.0`; 404 `RAD-CAP-004`; 422 `RAD-CAP-008`; header `X-Correlation-ID`; `Cache-Control: no-store` |

### Acceptance evidence, TKT-06

| Acceptance criterion | Verification |
|---|---|
| Pesos e faixas históricas/queda/comparação seguem SDD | `tests/test_price_opportunity_domain.py::test_component_weights_follow_sdd`, `::test_historical_position_ranges_follow_sdd`, `::test_recent_price_drop_ranges_follow_sdd`, `::test_marketplace_comparison_ranges_follow_sdd` |
| Histórico insuficiente usa neutro 50 e warning para Confidence | `tests/test_price_opportunity_domain.py::test_insufficient_history_uses_neutral_and_warns`; `tests/test_api_price_opportunity.py::test_insufficient_history_uses_neutral_50` |
| Cupom não confirmado não reduz integralmente preço efetivo nem vira claim | `tests/test_price_opportunity_domain.py::test_unconfirmed_coupon_does_not_reduce_effective_price`, `::test_other_coupon_states_never_reduce_effective_price`; `tests/test_api_price_opportunity.py::test_unconfirmed_coupon_does_not_reduce_effective_price` |
| Frete desconhecido e referência insuficiente explícitos; preço riscado não prova vantagem | `tests/test_price_opportunity_domain.py::test_unknown_shipping_is_explicit`, `::test_absent_comparison_reference_is_explicit_and_neutral`, `::test_struck_through_price_is_not_proof_of_advantage`; `tests/test_api_price_opportunity.py::test_unknown_shipping_is_explicit` |
| Comportamento pela fronteira pública, sem enfraquecer teste/guardrail | `GET /candidates/{id}/price-opportunity`; erros `RAD-CAP-004/008`; nenhum teste/guardrail removido |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/05_SCORING_ENGINE.md`, `docs/ERROR_CATALOG.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-06. Limitações e blockers remanescentes: o SDD **não calibra** faixas de `Coupon / Final Price` e `Shipping Impact`, portanto esses componentes ficam `score=null`/`calibrated=false` e o `price_opportunity` é um score parcial sobre os componentes aprovados (`weight_covered=85`, `fully_calibrated=false`) — a calibração completa exige decisão humana; a captura manual ainda não persiste cupom/frete, então a fronteira aceita essas condições confirmadas como parâmetros validados (a persistência própria pertence a ticket de captura); comparação entre marketplaces depende de equivalência de Product (RDR-031/TKT-10) e sem referência verificada o componente é neutro e explícito; o snapshot versionado pertence à Evaluation (RDR-016/TKT-09), que também consome os warnings no Confidence (RDR-029); nenhum teste live/credenciado foi executado e nenhuma capability foi promovida para AUTO.

## Foundation traceability, TKT-07 (RDR-024)

Escopo: compor Seller Quality a partir dos fatos de vendedor do Candidate e de
uma normalização versionada/hasheada, com componentes independentes, origem de
cada sinal e lacunas explícitas. Camadas `unit` e `contract` com SQLite temporário
real; nenhum teste live, credencial, provider externo ou side effect comercial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-024 pesos aprovados | `tests/test_seller_quality_domain.py::test_component_weights_follow_sdd`, `::test_composition_uses_approved_weights` | Composição reputation/rating/sales/trusted mantém pesos 40/25/20/15 | componentes com pesos aprovados; `seller_quality` ponderado; `docs/05_SCORING_ENGINE.md` |
| RDR-024 dados ausentes | `tests/test_seller_quality_domain.py::test_missing_signals_are_none_and_never_zero`, `::test_partial_aggregate_uses_only_calibrated_components`; `tests/test_api_seller_quality.py::test_missing_signals_do_not_become_zero` | Dados ausentes não viram zero automaticamente | `score=null` (não 0), `reason=missing_data`, `SELLER_QUALITY_MISSING_DATA`; agregado parcial sobre componentes calibrados |
| RDR-024 normalização configurada | `tests/test_seller_quality_domain.py::test_normalization_is_versioned_and_hashed`, `::test_hash_is_stable_and_changes_with_content`, `::test_unconfigured_value_is_explicit_gap_without_invented_constant`, `::test_approved_baseline_does_not_invent_normalization`, `::test_bands_are_evaluated_deterministically_regardless_of_input_order`; `tests/test_seller_quality_config.py::test_loader_without_file_returns_approved_baseline`, `::test_loader_reads_versioned_file` | Normalizações configuradas são determinísticas e versionadas; lacunas não recebem constante inventada | `normalization_version`/`normalization_hash` no contrato; `score=null` + `SELLER_QUALITY_NORMALIZATION_NOT_DEFINED`; baseline aprovado vazio |
| RDR-024 dados inválidos/contraditórios | `tests/test_seller_quality_domain.py::test_negative_rating_is_invalid_and_warns`, `::test_negative_sales_count_is_invalid_and_warns`, `::test_signals_without_seller_identity_are_contradictory`; `tests/test_api_seller_quality.py::test_invalid_rating_generates_warning`, `::test_contradictory_signals_without_identity_generate_warning` | Dados inválidos e contraditórios geram warnings/Evidence | `SELLER_QUALITY_INVALID_DATA`/`SELLER_QUALITY_CONTRADICTION`; `reason=invalid_data`; identidade contraditória reportada |
| Origem de cada sinal | `tests/test_seller_quality_domain.py::test_component_contract_reports_signal_origin`; `tests/test_api_seller_quality.py::test_seller_quality_returns_breakdown_with_provenance` | Cada componente expõe a origem do sinal | `source=persisted_offer`/`evaluation_input` e `raw` por componente |
| Config inválida falha fechado | `tests/test_seller_quality_config.py::test_loader_explicit_missing_file_fails_closed`, `::test_loader_invalid_json_fails_closed`, `::test_loader_invalid_document_fails_closed`; `tests/test_seller_quality_domain.py::test_build_rejects_missing_version`, `::test_build_rejects_unknown_schema_version`, `::test_build_rejects_out_of_range_score`, `::test_build_rejects_overlapping_bands`, `::test_build_rejects_unknown_trusted_key`, `::test_build_rejects_float_band_limit`, `::test_build_rejects_max_below_min` | Normalização inválida não é apresentada como validada | `RAD-CFG-006`; API bloqueada na criação |
| API pública e erros | `tests/test_api_seller_quality.py::test_seller_quality_returns_breakdown_with_provenance`, `::test_default_baseline_reports_gaps_without_inventing_values`, `::test_candidate_not_found_returns_structured_404`, `::test_malformed_rating_returns_structured_422`, `::test_malformed_trusted_returns_structured_422`, `::test_malformed_sales_count_returns_structured_422`, `::test_correlation_id_is_generated_when_absent` | Fronteira pública versionada com Correlation ID e erro estruturado | `GET /candidates/{id}/seller-quality` 200 `schema_version=1.0`; 404 `RAD-CAP-004`; 422 `RAD-CAP-009`; header `X-Correlation-ID`; `Cache-Control: no-store` |

### Acceptance evidence, TKT-07

| Acceptance criterion | Verification |
|---|---|
| Composição mantém pesos aprovados | `tests/test_seller_quality_domain.py::test_component_weights_follow_sdd`, `::test_composition_uses_approved_weights`; `tests/test_api_seller_quality.py::test_seller_quality_returns_breakdown_with_provenance` |
| Dados ausentes não viram zero | `tests/test_seller_quality_domain.py::test_missing_signals_are_none_and_never_zero`; `tests/test_api_seller_quality.py::test_missing_signals_do_not_become_zero` |
| Normalizações configuradas são determinísticas e versionadas; lacunas explícitas | `tests/test_seller_quality_domain.py::test_normalization_is_versioned_and_hashed`, `::test_unconfigured_value_is_explicit_gap_without_invented_constant`, `::test_approved_baseline_does_not_invent_normalization`; `tests/test_seller_quality_config.py::test_loader_reads_versioned_file` |
| Dados inválidos e contraditórios geram warnings/Evidence | `tests/test_seller_quality_domain.py::test_negative_rating_is_invalid_and_warns`, `::test_signals_without_seller_identity_are_contradictory`; `tests/test_api_seller_quality.py::test_invalid_rating_generates_warning`, `::test_contradictory_signals_without_identity_generate_warning` |
| Comportamento pela fronteira pública, sem enfraquecer teste/guardrail | `GET /candidates/{id}/seller-quality`; erros `RAD-CAP-004/009`; nenhum teste/guardrail removido |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/05_SCORING_ENGINE.md`, `docs/ERROR_CATALOG.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-07. Limitações e blockers remanescentes: o SDD **não calibra** a normalização dos quatro sinais de Seller Quality, portanto o baseline aprovado é vazio e cada sinal é uma lacuna explícita (`SELLER_QUALITY_NORMALIZATION_NOT_DEFINED`) até um humano fornecer `config/seller-quality.json` versionado; o `seller_quality` é parcial sobre os componentes calibrados (`weight_covered`/`fully_calibrated`), nunca um valor inventado; marketplace reputation e official/trusted status ainda não são persistidos pela captura manual, então a fronteira aceita esses sinais como parâmetros validados (a persistência própria pertence a ticket de captura); o snapshot versionado pertence à Evaluation (RDR-016/TKT-09), que também consome os warnings no Confidence (RDR-029); a medição por categoria (RDR-025/TKT-08) é ticket próprio; nenhum teste live/credenciado foi executado e nenhuma capability foi promovida para AUTO.

## Foundation traceability, TKT-08 (RDR-025)

Escopo: consultar Demand de um Candidate a partir apenas dos sinais disponíveis
(categoria bruta e `sales_count` persistidos; `rating_count`, `trend`,
`affiliate_portal` e `badges` validados na avaliação) e de uma normalização
versionada por categoria, com origem de cada sinal e lacunas explícitas. Camadas
`unit` e `contract` com SQLite temporário real; relógio/id controlados; nenhum
teste live, credencial, provider externo ou side effect comercial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-025 sinais e origem | `tests/test_demand_domain.py::test_breakdown_covers_all_approved_signals`, `::test_component_contract_reports_signal_origin_and_raw`; `tests/test_api_demand.py::test_demand_returns_breakdown_with_provenance` | sales/rating counts, trends e badges têm origem registrada | `source=persisted_offer`/`evaluation_input` e `raw` por componente; `GET /candidates/{id}/demand` 200 |
| RDR-025 normalização por categoria | `tests/test_demand_domain.py::test_normalization_is_versioned_and_hashed`, `::test_hash_is_stable_and_changes_with_content`, `::test_composition_uses_configured_category_weights`; `tests/test_demand_config.py::test_loader_reads_versioned_file` | Normalização por categoria é versionada e não usa IA para calcular score | `normalization_version`/`normalization_hash` no contrato; `config/demand.json`; cálculo determinístico sem IA |
| RDR-025 ausência de dados | `tests/test_demand_domain.py::test_missing_signals_are_none_and_never_zero`, `::test_empty_badges_do_not_become_zero`, `::test_partial_aggregate_uses_only_calibrated_components`; `tests/test_api_demand.py::test_missing_signals_do_not_become_zero` | Ausência de dados fica explícita sem inventar volume/conversões | `score=null` (não 0), `reason=missing_data`, `DEMAND_MISSING_DATA`; agregado parcial sobre componentes calibrados |
| RDR-025 badge não mapeado | `tests/test_demand_domain.py::test_unmapped_badge_is_explicit_gap`, `::test_badges_use_the_strongest_recognized_badge` | Badge sem mapeamento não recebe valor inventado | `DEMAND_NORMALIZATION_NOT_DEFINED` com `unmapped`; `score=null` |
| RDR-025 config incompleta | `tests/test_api_demand.py::test_incomplete_configuration_is_not_presented_as_validated`, `::test_default_baseline_reports_gaps_without_inventing_values` | Config de normalização incompleta impede resultado apresentado como validado | `fully_calibrated=false`; `weight=null`; `DEMAND_NORMALIZATION_NOT_DEFINED`; baseline aprovado vazio |
| RDR-025 categoria não resolvida | `tests/test_demand_domain.py::test_missing_category_is_explicit_gap` | Categoria não resolvida é lacuna explícita | `DEMAND_CATEGORY_NOT_DEFINED`; `demand=null` |
| RDR-025 config inválida falha fechado | `tests/test_demand_config.py::test_loader_explicit_missing_file_fails_closed`, `::test_loader_invalid_json_fails_closed`, `::test_loader_invalid_document_fails_closed`; `tests/test_demand_domain.py::test_build_rejects_missing_version`, `::test_build_rejects_unknown_schema_version`, `::test_build_rejects_unknown_category`, `::test_build_rejects_unknown_signal_in_weights`, `::test_build_rejects_out_of_range_weight`, `::test_build_rejects_overlapping_bands`, `::test_build_rejects_float_band_limit`, `::test_build_rejects_max_below_min` | Normalização inválida não é apresentada como validada | `RAD-CFG-007`; API bloqueada na criação |
| API pública e erros | `tests/test_api_demand.py::test_candidate_not_found_returns_structured_404`, `::test_malformed_rating_count_returns_structured_422`, `::test_empty_badges_returns_structured_422`, `::test_correlation_id_is_generated_when_absent` | Fronteira pública versionada com Correlation ID e erro estruturado | `GET /candidates/{id}/demand` 200 `schema_version=1.0`; 404 `RAD-CAP-004`; 422 `RAD-CAP-010`; header `X-Correlation-ID`; `Cache-Control: no-store` |

### Acceptance evidence, TKT-08

| Acceptance criterion | Verification |
|---|---|
| sales/rating counts, tendências e badges têm origem registrada | `tests/test_demand_domain.py::test_component_contract_reports_signal_origin_and_raw`; `tests/test_api_demand.py::test_demand_returns_breakdown_with_provenance` |
| Normalização por categoria é versionada e não usa IA para calcular score | `tests/test_demand_domain.py::test_normalization_is_versioned_and_hashed`, `::test_composition_uses_configured_category_weights`; `tests/test_demand_config.py::test_loader_reads_versioned_file` |
| Ausência de dados fica explícita sem inventar volume/conversões | `tests/test_demand_domain.py::test_missing_signals_are_none_and_never_zero`; `tests/test_api_demand.py::test_missing_signals_do_not_become_zero` |
| Config de normalização incompleta impede resultado apresentado como validado | `tests/test_api_demand.py::test_incomplete_configuration_is_not_presented_as_validated`, `::test_default_baseline_reports_gaps_without_inventing_values`; `tests/test_demand_domain.py::test_unconfigured_value_is_explicit_gap_without_invented_constant`, `::test_approved_baseline_does_not_invent_normalization` |
| Comportamento pela fronteira pública, sem enfraquecer teste/guardrail | `GET /candidates/{id}/demand`; erros `RAD-CAP-004/010`; nenhum teste/guardrail removido |
| Docs/contratos e matriz QA atualizados | este documento, `docs/04_DATA_CONTRACTS.md`, `docs/05_SCORING_ENGINE.md`, `docs/ERROR_CATALOG.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-08. Limitações e blockers remanescentes: o SDD **não calibra** nem o mapeamento nem os pesos de composição de Demand, portanto o baseline aprovado é vazio e cada categoria/sinal é uma lacuna explícita (`DEMAND_NORMALIZATION_NOT_DEFINED`) até um humano fornecer `config/demand.json` versionado; o `demand` é parcial sobre os componentes calibrados (`weight_covered`/`fully_calibrated`) e config incompleta nunca é apresentada como validada; a categoria canônica depende da taxonomia/classificação aprovada (TKT-05) e, sem resolução, a demanda é lacuna explícita; `rating_count`, `trend`, `affiliate_portal` e `badges` ainda não são persistidos pela captura manual, então a fronteira aceita esses sinais como parâmetros validados (a persistência própria pertence a ticket de captura); o snapshot versionado pertence à Evaluation (RDR-016/TKT-09), que também consome os warnings no Confidence (RDR-029); a IA nunca calcula o score; nenhum teste live/credenciado foi executado e nenhuma capability foi promovida para AUTO.

## Foundation traceability, TKT-09 (RDR-016, RDR-027, RDR-028, RDR-029, RDR-030)

Escopo: compor Deal/Monetization/Confidence determinísticos a partir dos
componentes normalizados das dependências e da taxonomia ativa, aplicar Hard Rules
antes de score/IA/link/publicação, decidir pela matriz Deal x Confidence e
persistir uma Evaluation imutável e consultável. Camadas `unit`, `contract` e
`integration` com SQLite temporário real, relógio e id controlados; nenhum teste
live, credencial, provider externo, IA ou side effect comercial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-016 Evaluation imutável | `tests/test_evaluation_persistence.py::test_evaluations_are_append_only_and_immutable`, `::test_persisted_snapshot_keeps_versions_and_breakdown`; `tests/test_api_evaluation.py::test_evaluations_are_immutable_and_traceable_via_public_boundary` | Evaluation versionada, append-only e rastreável | triggers `trg_evaluation_no_update`/`trg_evaluation_no_delete`; 2 linhas preservadas; `scoring_version`/`deal_scoring_version`/`monetization_scoring_version`/`confidence_scoring_version`/`taxonomy_hash` |
| RDR-027 Deal Score | `tests/test_evaluation_domain.py::test_deal_weights_follow_sdd`, `::test_deal_score_stays_on_the_zero_to_hundred_scale`, `::test_missing_required_deal_component_is_blocking`; `tests/test_api_evaluation.py::test_boundaries_60_and_80_follow_the_matrix` | Pesos 40/25/20/15, escala 0..100 e dado obrigatório bloqueante | breakdown com pesos; `deal_score` `"60.00"`/`"80.00"`; `INSUFFICIENT_REQUIRED_DATA` com `deal_score=null` |
| RDR-028 Monetization | `tests/test_evaluation_domain.py::test_monetization_weights_and_neutral_conversion`, `::test_commission_never_changes_the_deal_score`, `::test_deal_45_with_monetization_97_stays_rejected`; `tests/test_api_evaluation.py::test_deal_45_with_monetization_97_stays_rejected`, `::test_commission_does_not_change_the_deal_score` | Pesos 40/25/20/15, Conversion neutro 50, comissão não altera Deal e não eleva rejeitado | `monetization_score=97` com `decision=REJECT`; mesmo `deal_score` para comissões diferentes; `CONVERSION_EVIDENCE_NEUTRAL` |
| RDR-029 Confidence | `tests/test_evaluation_domain.py::test_confidence_bands_follow_sdd`, `::test_confidence_weights_follow_sdd` | Faixas 0..49/50..79/80..100 e pesos 30/25/20/15/10 | `confidence_level_for(49/50/79/80)`; componentes com pesos; ausência explícita |
| RDR-030 Hard/Soft Rules | `tests/test_evaluation_domain.py::test_hard_rules_precede_scores_and_ai`, `::test_out_of_scope_category_hard_rule_is_propagated`; `tests/test_api_evaluation.py::test_hard_rules_reject_before_ai_link_and_publication`, `::test_declared_hard_rule_rejects`, `::test_missing_required_data_is_blocking_and_persisted` | Hard Rules precedem score, IA, link e publicação; soft rules viram warnings | `failed_rules` com `COMPLIANCE_BLOCK`/`OUT_OF_SCOPE_CATEGORY`/`INSUFFICIENT_REQUIRED_DATA`; sem `affiliate_link`/`ai_review`/`opportunity_id` |
| Matriz Deal x Confidence | `tests/test_evaluation_domain.py::test_decision_matrix_boundaries`; `tests/test_api_evaluation.py::test_boundaries_60_and_80_follow_the_matrix` | Boundaries 59.99/60/79.99/80 e Confidence LOW/MEDIUM/HIGH seguem a matriz | `decide(...)` = REJECT/REVIEW/APPROVE; `auto_eligible` só com Deal `>=80` + HIGH sem Hard Rule |
| Persistência/transação/auditoria | `tests/test_evaluation_persistence.py::test_evaluation_is_persisted_and_queryable`, `::test_failed_write_rolls_back_without_partial_records`, `::test_audit_event_records_the_evaluation`; `tests/test_database_migration.py::test_migration_adds_evaluation_from_price_history_revision` | Gravação atômica, FK/trigger reais, migration N→N+1 e audit event | SQLite temporário real; `IntegrityError` sem escrita parcial; `EVALUATION_RECORDED` com Correlation ID |
| API pública e erros | `tests/test_api_evaluation.py::test_evaluation_returns_decision_and_is_queryable`, `::test_candidate_not_found_returns_structured_404`, `::test_invalid_component_score_returns_structured_422`, `::test_unknown_hard_rule_returns_structured_422`, `::test_correlation_id_is_generated_when_absent` | Fronteira pública versionada com Correlation ID e erro estruturado | `POST`/`GET /candidates/{id}/evaluations` 200/201 `schema_version=1.0`; 404 `RAD-CAP-004`; 422 `RAD-CAP-011`; header `X-Correlation-ID`; `Cache-Control: no-store` |

### Acceptance evidence, TKT-09

| Acceptance criterion | Verification |
|---|---|
| Hard Rules rejeitam antes de IA, link e publicação | `tests/test_evaluation_domain.py::test_hard_rules_precede_scores_and_ai`, `::test_out_of_scope_category_hard_rule_is_propagated`; `tests/test_api_evaluation.py::test_hard_rules_reject_before_ai_link_and_publication` |
| Boundaries 59.99/60/79.99/80 e Confidence LOW/MEDIUM/HIGH seguem matriz | `tests/test_evaluation_domain.py::test_decision_matrix_boundaries`, `::test_confidence_bands_follow_sdd`; `tests/test_api_evaluation.py::test_boundaries_60_and_80_follow_the_matrix` |
| Deal 45 e Monetization 97 permanece REJECT | `tests/test_evaluation_domain.py::test_deal_45_with_monetization_97_stays_rejected`; `tests/test_api_evaluation.py::test_deal_45_with_monetization_97_stays_rejected` |
| Scores mantêm escala e pesos; comissão não altera Deal | `tests/test_evaluation_domain.py::test_deal_weights_follow_sdd`, `::test_monetization_weights_and_neutral_conversion`, `::test_commission_never_changes_the_deal_score`; `tests/test_api_evaluation.py::test_commission_does_not_change_the_deal_score` |
| Feature snapshot/breakdown/scoring versions imutáveis e rastreáveis | `tests/test_evaluation_persistence.py::test_evaluations_are_append_only_and_immutable`, `::test_persisted_snapshot_keeps_versions_and_breakdown`; `tests/test_api_evaluation.py::test_evaluations_are_immutable_and_traceable_via_public_boundary` |
| Comportamento pela fronteira pública, sem enfraquecer teste/guardrail | `POST`/`GET /candidates/{id}/evaluations`; erros `RAD-CAP-004/011`; triggers de imutabilidade; nenhum teste/guardrail removido |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/05_SCORING_ENGINE.md`, `docs/10_PERSISTENCE_AND_RECOVERY.md`, `docs/ERROR_CATALOG.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-09. Limitações e blockers remanescentes: Price Opportunity, Seller Quality e Demand ainda têm calibração parcial nos SDDs (TKT-06/07/08), então a Evaluation recebe esses componentes como entradas validadas e qualquer componente obrigatório ausente bloqueia com `INSUFFICIENT_REQUIRED_DATA` — a integração automática dos endpoints read-only no fluxo de Evaluation pertence ao workflow (RDR-041/TKT-16); o Brand Fit de Casa em Ordem permanece sem calibração aprovada, então essa marca bloqueia por dado obrigatório ausente até decisão humana; `auto_eligible=true` é apenas elegibilidade e não promove nenhuma capability para AUTO (AUT-258, AUT-452); o `AuditEvent` `EVALUATION_RECORDED` é gravado, mas a integração com o Workflow/HumanAction pertence aos tickets dependentes; nenhum teste live/credenciado foi executado e nenhuma capability foi promovida para AUTO.

## Foundation traceability, TKT-10 (RDR-031)

Escopo: comparar ofertas confiáveis do mesmo Product, aplicar o Purchase Source
Guardrail (`>8%` configurável) sem favorecer comissão e persistir a decisão
append-only com Evidence e audit event. Camadas `unit`, `contract` e `integration`
com SQLite temporário real, relógio e id controlados; nenhum teste live,
credencial, provider externo, IA ou side effect comercial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-031 Guardrail `>8%` | `tests/test_purchase_source_domain.py::test_reference_above_8_percent_goes_to_review`, `::test_exactly_8_percent_is_not_material`; `tests/test_api_purchase_source.py::test_material_difference_reviews_and_is_queryable` | Diferença de referência `>8%` usa `REVIEW`/substituição conforme policy; exatamente `8%` não é material | `difference_percent="9.0000"` → `REVIEW`; `"8.0000"` → `KEEP`; `reference_difference_percent="8"` |
| RDR-031 Substituição conforme policy | `tests/test_purchase_source_domain.py::test_substitute_action_replaces_the_source`, `::test_cheapest_eligible_alternative_is_selected`; `tests/test_api_purchase_source.py::test_substitute_policy_replaces_the_source` | Policy `SUBSTITUTE` substitui pela melhor alternativa confiável | `decision=SUBSTITUTE`, `substituted_source_id="shopee:1"`; policy versionada/hasheada |
| Preço efetivo confiável | `tests/test_purchase_source_domain.py::test_confirmed_coupon_reduces_effective_price`, `::test_unconfirmed_coupon_never_reduces_effective_price`, `::test_unknown_shipping_excludes_the_source`, `::test_alternative_without_known_shipping_is_unreliable`; `tests/test_api_purchase_source.py::test_confirmed_coupon_is_applied`, `::test_unconfirmed_coupon_is_not_applied`, `::test_unknown_shipping_has_no_reliable_comparison` | `preço + frete - cupom CONFIRMED`; cupom não confirmado nunca reduz; frete desconhecido exclui a oferta | `effective_price` só com frete conhecido; `LIKELY` não aplicado; `PURCHASE_SOURCE_UNRELIABLE_PRICE`/`PURCHASE_SOURCE_NO_RELIABLE_COMPARISON` |
| Produto equivalente | `tests/test_purchase_source_domain.py::test_non_equivalent_product_is_not_a_valid_comparison`, `::test_unidentified_product_has_no_valid_comparison`, `::test_different_conditions_are_not_comparable`; `tests/test_api_purchase_source.py::test_non_equivalent_product_is_not_a_valid_comparison` | Produto não identificado como equivalente (ou condições diferentes) não é comparação válida | `PURCHASE_SOURCE_NOT_EQUIVALENT`/`PURCHASE_SOURCE_PRODUCT_NOT_IDENTIFIED`/`PURCHASE_SOURCE_CONDITIONS_NOT_COMPARABLE`; `difference_percent=null` |
| Monetization não contorna | `tests/test_purchase_source_domain.py::test_commission_never_changes_the_decision`; `tests/test_api_purchase_source.py::test_high_commission_never_bypasses_the_guardrail` | Comissão não é entrada e nunca favorece a seleção afiliada | `commission_considered=false`; mesma decisão para comissões distintas; `PURCHASE_SOURCE_COMMISSION_IGNORED` |
| Persistência/transação/auditoria | `tests/test_purchase_source_persistence.py::test_decision_is_persisted_with_evidence_and_queryable`, `::test_decisions_are_append_only_and_immutable`, `::test_audit_event_records_the_decision`, `::test_failed_write_rolls_back_without_partial_records`, `::test_persisted_row_keeps_policy_and_breakdown`; `tests/test_database_migration.py::test_migration_adds_purchase_source_decision_from_evaluation_revision` | Gravação atômica com Evidence, FK/trigger reais, migration N→N+1 e audit event | SQLite temporário real; triggers `trg_purchase_source_decision_no_update/no_delete`; `IntegrityError` sem escrita parcial; `PURCHASE_SOURCE_DECIDED` com Correlation ID |
| API pública e erros | `tests/test_api_purchase_source.py::test_material_difference_reviews_and_is_queryable`, `::test_candidate_not_found_returns_structured_404`, `::test_invalid_money_returns_structured_422`, `::test_sensitive_field_is_rejected`, `::test_correlation_id_is_generated_when_absent` | Fronteira pública versionada com Correlation ID e erro estruturado | `POST`/`GET /candidates/{id}/purchase-source` 201/200 `schema_version=1.0`; 404 `RAD-CAP-004`; 422 `RAD-CAP-012`/`RAD-CAP-002`; header `X-Correlation-ID`; `Cache-Control: no-store` |

### Acceptance evidence, TKT-10

| Acceptance criterion | Verification |
|---|---|
| Diferença de referência >8% usa REVIEW ou substituição conforme policy configurada | `tests/test_purchase_source_domain.py::test_reference_above_8_percent_goes_to_review`, `::test_exactly_8_percent_is_not_material`, `::test_substitute_action_replaces_the_source`; `tests/test_api_purchase_source.py::test_material_difference_reviews_and_is_queryable`, `::test_substitute_policy_replaces_the_source` |
| Preço efetivo usa apenas frete/cupom confiáveis e condições comparáveis | `tests/test_purchase_source_domain.py::test_confirmed_coupon_reduces_effective_price`, `::test_unconfirmed_coupon_never_reduces_effective_price`, `::test_different_conditions_are_not_comparable`; `tests/test_api_purchase_source.py::test_confirmed_coupon_is_applied`, `::test_unconfirmed_coupon_is_not_applied` |
| Produto não identificado como equivalente não é comparação válida | `tests/test_purchase_source_domain.py::test_non_equivalent_product_is_not_a_valid_comparison`, `::test_unidentified_product_has_no_valid_comparison`; `tests/test_api_purchase_source.py::test_non_equivalent_product_is_not_a_valid_comparison` |
| Monetization não contorna rejeição nem guardrail | `tests/test_purchase_source_domain.py::test_commission_never_changes_the_decision`; `tests/test_api_purchase_source.py::test_high_commission_never_bypasses_the_guardrail` |
| Comportamento pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido | `POST`/`GET /candidates/{id}/purchase-source`; `decision_id`/`audit_event_id`/`evidence` no contrato; triggers de imutabilidade; nenhum teste/guardrail removido |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/05_SCORING_ENGINE.md`, `docs/ERROR_CATALOG.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-10. Limitações e blockers remanescentes: a equivalência de Product (`product_equivalence_id`) e as condições comparáveis não são persistidas pela captura manual ainda, então são entradas validadas na fronteira e pertencem a um ticket de resolução de Product; a captura manual também não persiste cupom/frete/comissão, então as condições confirmadas são parâmetros validados; a policy baseline usa `REVIEW` (a substituição é configuração explícita do operador) e nenhuma capability é promovida para AUTO (AUT-257); a integração do guardrail na matriz de decisão da Evaluation/Workflow pertence aos tickets dependentes (RDR-041/TKT-16); nenhum teste live/credenciado foi executado e nenhuma capability foi promovida para AUTO.

## Foundation traceability, TKT-11 (RDR-032)

Escopo: produzir claims comerciais verificáveis a partir de uma Evaluation
imutável e das evidências persistidas (`Offer` + histórico append-only), com
provenance por afirmação e omissão explícita de claims sem suporte. Camadas
`unit` e `contract` com SQLite temporário real; relógio controlado; nenhum teste
live, credencial, provider externo, IA ou side effect comercial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-032 claims versionados com provenance | `tests/test_allowed_claims_domain.py::test_current_price_and_history_claims_carry_traceable_evidence`, `::test_sales_count_claim_uses_persisted_offer_evidence`; `tests/test_api_allowed_claims.py::test_current_and_history_claims_are_traceable_via_public_boundary` | `CURRENT_PRICE` e claims de queda/histórico carregam `Evidence` rastreável | `evidence_type`/`reference_id`/`raw_capture_id`/`correlation_id` no contrato; `GET /candidates/{id}/allowed-claims` 200 `schema_version=1.0` |
| RDR-032 `LOWEST_OBSERVED_30D` | `tests/test_allowed_claims_domain.py::test_lowest_observed_30d_requires_a_covered_window`; `tests/test_api_allowed_claims.py::test_lowest_observed_30d_is_omitted_without_covered_history`, `::test_lowest_observed_30d_is_produced_with_covered_history` | Claim não é produzido sem histórico que cubra a janela de 30 dias | `omitted_claims=[{claim_type:LOWEST_OBSERVED_30D, reason_code:HISTORY_INSUFFICIENT}]`; warning `LOWEST_OBSERVED_30D_HISTORY_INSUFFICIENT`; cobertura exige observação <= início da janela |
| RDR-032 cupom/preço riscado | `tests/test_allowed_claims_domain.py::test_unconfirmed_coupon_is_not_proof_and_confirmed_coupon_is`, `::test_struck_through_price_is_never_proof`; `tests/test_api_allowed_claims.py::test_coupon_state_controls_the_confirmed_coupon_claim`, `::test_struck_through_price_does_not_become_proof` | Cupom provável/desconhecido e preço riscado isolado não viram prova | `CONFIRMED_COUPON` só com `CONFIRMED`; LIKELY/UNKNOWN omitidos com `COUPON_NOT_CONFIRMED`; warning `STRUCK_THROUGH_PRICE_NOT_PROOF` e zero claim de histórico a partir de `original_price` |
| RDR-032 claims sem suporte | `tests/test_allowed_claims_domain.py::test_unsupported_claims_are_omitted_and_forbidden_claims_are_explicit`, `::test_engine_is_deterministic_for_the_same_facts`; `tests/test_api_allowed_claims.py::test_forbidden_claims_are_explicit_and_never_produced` | Claims sem suporte são omitidos/bloqueados e nunca criados pela IA | `omitted_claims` com motivo; `forbidden_claims` do SDD-06 no contrato; motor determinístico sem IA (`engine_version=allowed-claims-1.0`) |
| Persistência observável / erros | `tests/test_api_allowed_claims.py::test_evaluation_version_can_be_selected`, `::test_candidate_without_evaluation_fails_closed`, `::test_candidate_not_found_returns_structured_404`, `::test_invalid_coupon_state_returns_structured_422`, `::test_correlation_id_is_generated_when_absent` | Resultado ligado à Evaluation imutável e erros estruturados pela fronteira pública | `evaluation_id` no contrato; 404 `RAD-CAP-004`/`RAD-CAP-013`; 422 `RAD-CAP-014`; header `X-Correlation-ID`; `Cache-Control: no-store` |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/05_SCORING_ENGINE.md`, `docs/ERROR_CATALOG.md`, `README.md` | Docs/contratos e matriz QA atualizados | contrato JSON de Allowed Claims; `RAD-CAP-013/014`; este traceability |

### Acceptance evidence, TKT-11

| Acceptance criterion | Verification |
|---|---|
| CURRENT_PRICE e claims de queda/histórico possuem evidência rastreável | `tests/test_allowed_claims_domain.py::test_current_price_and_history_claims_carry_traceable_evidence`; `tests/test_api_allowed_claims.py::test_current_and_history_claims_are_traceable_via_public_boundary` |
| LOWEST_OBSERVED_30D não é produzido sem histórico suficiente para a afirmação | `tests/test_allowed_claims_domain.py::test_lowest_observed_30d_requires_a_covered_window`; `tests/test_api_allowed_claims.py::test_lowest_observed_30d_is_omitted_without_covered_history` |
| Cupom provável/desconhecido e preço riscado isolado não viram prova | `tests/test_allowed_claims_domain.py::test_unconfirmed_coupon_is_not_proof_and_confirmed_coupon_is`, `::test_struck_through_price_is_never_proof`; `tests/test_api_allowed_claims.py::test_coupon_state_controls_the_confirmed_coupon_claim`, `::test_struck_through_price_does_not_become_proof` |
| Claims sem suporte são omitidos/bloqueados e nunca criados pela IA | `tests/test_allowed_claims_domain.py::test_unsupported_claims_are_omitted_and_forbidden_claims_are_explicit`; `tests/test_api_allowed_claims.py::test_forbidden_claims_are_explicit_and_never_produced` |
| Comportamento pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido | `GET /candidates/{id}/allowed-claims`; `evidence`/`raw_capture_id`/`correlation_id` no contrato; erros `RAD-CAP-004/013/014`; nenhum teste/guardrail removido |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/05_SCORING_ENGINE.md`, `docs/ERROR_CATALOG.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-11. Limitações e blockers remanescentes: o resultado é read-only e determinístico, sem store próprio — é função da Evaluation imutável (RDR-016) e das evidências append-only (RDR-013), então o snapshot do input de IA pertence ao ticket de AI Review (RDR-050/TKT-19), que consumirá `allowed_claims`; o SDD não calibra um mínimo de observações para `LOWEST_OBSERVED_30D`, então a regra é conservadora e explícita (o histórico precisa cobrir a janela de 30 dias) e nunca inventa um mínimo "desde que começamos"; a captura manual ainda não persiste cupom/frete, então o cupom `CONFIRMED` é uma condição validada na fronteira (a persistência própria pertence a um ticket de captura); `PRICE_DROP_PERCENT` é emitido apenas quando a queda é positiva (nunca um "aumento" disfarçado de queda); a IA não cria, altera ou calcula claim e nenhuma capability foi promovida para AUTO; nenhum teste live/credenciado foi executado.

## Foundation traceability, TKT-12 (RDR-033)

Escopo: aplicar o guardrail determinístico de dedupe/repost a um Candidate
persistido usando o `Offer`, a Evaluation mais recente (Deal) e um histórico de
publicação fornecido pelo chamador (histórico *fake* antes do publisher real),
com policy versionada/hasheada, `Evidence`, audit event e decisão append-only
consultável. Camadas `unit`, `contract` e `integration` com SQLite temporário
real, relógio controlado; nenhum teste live, credencial, provider externo, IA ou
side effect comercial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-033 cooldown/queda aprovados | `tests/test_repost_domain.py::test_approved_policy_follows_sdd_reference`, `::test_price_drop_at_or_above_ten_percent_releases_repost`, `::test_price_drop_below_ten_percent_is_not_material`; `tests/test_repost_config.py::test_loader_reads_versioned_file` | Cooldown 72h e queda `>=10%` seguem a policy configurada | `cooldown_hours=72`; queda `10.00` libera; `9.99` não; `config/repost.json` |
| RDR-033 mudança irrelevante | `tests/test_repost_domain.py::test_irrelevant_change_with_active_cooldown_blocks_repost`, `::test_first_publication_is_allowed_without_history`; `tests/test_api_repost.py::test_irrelevant_change_with_active_cooldown_blocks_repost` | Mudança irrelevante não libera repost; primeira publicação libera | `decision=BLOCKED`, `reason=DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE`; warning `DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE` |
| RDR-033 cupom/condição material + Deal forte | `tests/test_repost_domain.py::test_material_coupon_requires_evidence`, `::test_material_condition_requires_evidence`, `::test_cooldown_expired_without_material_change_requires_strong_deal`, `::test_unconfirmed_coupon_is_never_material`; `tests/test_api_repost.py::test_material_coupon_requires_evidence`, `::test_expired_cooldown_requires_strong_deal` | Cupom/condição material exige `Evidence`; cooldown vencido exige Deal forte | sem evidência → `REPOST_COUPON_WITHOUT_EVIDENCE`/`REPOST_CONDITION_WITHOUT_EVIDENCE`; cooldown vencido fraco → `DEAL_NOT_STRONG`; forte → `COOLDOWN_EXPIRED_STRONG_DEAL` |
| RDR-033 guardrail consultável | `tests/test_api_repost.py::test_first_publication_is_allowed_and_queryable`, `::test_correlation_id_is_generated_when_absent`; `tests/test_repost_persistence.py::test_decision_is_persisted_with_evidence_and_queryable` | Guardrail funciona com histórico fake de publicação antes do publisher real e é consultável | `POST`/`GET /candidates/{id}/repost` 201/200 `schema_version=1.0`; `decision_id`/`audit_event_id`/`evidence` |
| Persistência/transação/auditoria | `tests/test_repost_persistence.py::test_decisions_are_append_only_and_immutable`, `::test_audit_event_records_the_decision`, `::test_failed_write_rolls_back_without_partial_records`, `::test_persisted_row_keeps_policy_and_breakdown`; `tests/test_database_migration.py::test_migration_adds_repost_decision_from_purchase_source_revision` | Gravação atômica com `Evidence`, FK/trigger reais, migration N→N+1 e audit event | triggers `trg_repost_decision_no_update/no_delete`; `IntegrityError` sem escrita parcial; `REPOST_DECIDED` com Correlation ID; revision `0006_repost_decision` |
| API pública e erros | `tests/test_api_repost.py::test_candidate_not_found_returns_structured_404`, `::test_invalid_money_returns_structured_422`, `::test_sensitive_field_is_rejected` | Fronteira pública versionada com Correlation ID e erro estruturado | 404 `RAD-CAP-004`; 422 `RAD-CAP-015`/`RAD-CAP-002`; header `X-Correlation-ID`; `Cache-Control: no-store` |

### Acceptance evidence, TKT-12

| Acceptance criterion | Verification |
|---|---|
| Cooldown 72h e queda `>=10%` seguem a config aprovada | `tests/test_repost_domain.py::test_approved_policy_follows_sdd_reference`, `::test_price_drop_at_or_above_ten_percent_releases_repost`; `tests/test_repost_config.py::test_loader_reads_versioned_file` |
| Mudança irrelevante não libera repost | `tests/test_repost_domain.py::test_irrelevant_change_with_active_cooldown_blocks_repost`; `tests/test_api_repost.py::test_irrelevant_change_with_active_cooldown_blocks_repost` |
| Cupom/condição material exige Evidence e cooldown vencido exige Deal forte | `tests/test_repost_domain.py::test_material_coupon_requires_evidence`, `::test_material_condition_requires_evidence`, `::test_cooldown_expired_without_material_change_requires_strong_deal`; `tests/test_api_repost.py::test_material_coupon_requires_evidence`, `::test_expired_cooldown_requires_strong_deal` |
| Guardrail consultável com histórico fake antes do publisher real | `tests/test_api_repost.py::test_first_publication_is_allowed_and_queryable`; `tests/test_repost_persistence.py::test_decision_is_persisted_with_evidence_and_queryable` |
| Comportamento pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido | `POST`/`GET /candidates/{id}/repost`; `decision_id`/`audit_event_id`/`evidence` no contrato; triggers de imutabilidade; nenhum teste/guardrail removido |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/05_SCORING_ENGINE.md`, `docs/10_PERSISTENCE_AND_RECOVERY.md`, `docs/ERROR_CATALOG.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-12. Limitações e blockers remanescentes: o histórico de publicação é uma entrada do guardrail (histórico *fake*), pois a entidade `Publication`/publisher real pertence aos tickets de publicação (RDR-020/RDR-071+), então a integração com o Workflow/Publisher fica para o ticket dependente; a captura manual ainda não persiste cupom/frete/condições, então o cupom confirmado e as condições comparáveis são entradas validadas na fronteira (a persistência própria pertence a um ticket de captura); o `HumanAction` para repost bloqueado pertence ao módulo de HumanAction (RDR-040), que ainda não existe — aqui só o estado/decisão e o warning são expostos, sem inventar envio automático; a decisão de repost não publica nada e nenhuma capability foi promovida para AUTO; nenhum teste live/credenciado foi executado.

## Workflow traceability, TKT-13 (RDR-034, RDR-035, RDR-036)

Escopo: enfileirar trabalho persistente, claimar com lease expirável e lock
lógico, consultar resultado e atualizar estado sem execução concorrente
equivalente. Camadas `unit`, `contract` e `integration` com SQLite temporário
real, relógio controlado e claim concorrente; nenhum teste live, credencial,
provider externo, IA ou side effect comercial.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-034 Job persistente | `tests/test_job_domain.py::test_create_job_persists_priority_availability_attempts_and_correlation`; `tests/test_job_persistence.py::test_job_persists_priority_availability_attempts_and_correlation` | Job persiste prioridade, disponibilidade, attempts/max_attempts e Correlation ID | tabela `job` com `priority=9`, `available_at`, `attempts`, `correlation_id`; `GET /jobs/{id}` 200 `schema_version=1.0` |
| RDR-034/035 claim único | `tests/test_job_persistence.py::test_claim_grants_a_single_lease_under_concurrency`; `tests/test_api_jobs.py::test_claim_grants_one_lease_then_no_job_is_available` | Claim concorrente concede um único lease válido | dois workers concorrentes → 1 `CLAIMED`, 1 `RAD-WF-008` retryable; `attempts=1`; `locked_by`/`lease_expires_at` persistidos |
| RDR-035 lease expira/recovery | `tests/test_job_domain.py::test_expired_lease_is_claimable_by_another_worker`; `tests/test_job_persistence.py::test_lease_expiry_lets_another_worker_recover_and_blocks_the_old_worker` | Lease expira e outro worker recupera; worker antigo não confirma | relógio controlado +31s → `worker-b` claima `attempts=2`; `worker-a` recebe `RAD-WF-009` |
| RDR-035 worker inválido | `tests/test_job_domain.py::test_worker_cannot_confirm_another_workers_execution`, `::test_start_requires_the_lease_owner`; `tests/test_job_persistence.py::test_worker_cannot_start_or_complete_another_workers_job`; `tests/test_api_jobs.py::test_invalid_worker_cannot_complete_anothers_execution` | Worker inválido não inicia/confirma execução alheia nem lease expirado | `RAD-WF-009` antes e depois da expiração; job permanece `CLAIMED`/inalterado |
| RDR-036 lock lógico | `tests/test_job_domain.py::test_lock_expiration_is_explicit`; `tests/test_job_persistence.py::test_logical_lock_is_exclusive_and_expires`, `::test_lock_acquire_writes_audit_events`; `tests/test_api_jobs.py::test_logical_lock_boundary_is_exclusive` | Locks expiram e são exclusivos por owner | lock ativo de outro owner → `RAD-WF-004` retryable; renovação pelo mesmo owner; takeover após expirar; só o owner libera |
| Estado de domínio ≠ estado de Job | `tests/test_job_domain.py::test_job_status_is_independent_from_domain_state`, `::test_job_type_rejects_domain_state`, `::test_invalid_schema_version_is_rejected`, `::test_invalid_priority_and_attempt_budget_are_rejected`, `::test_payload_must_be_json_and_free_of_sensitive_fields`; `tests/test_job_persistence.py::test_invalid_job_is_rejected_without_persisting`; `tests/test_api_jobs.py::test_domain_state_is_never_accepted_as_a_job_state`, `::test_invalid_schema_version_is_rejected`, `::test_missing_job_type_returns_structured_workflow_error`, `::test_sensitive_payload_is_rejected` | Schema/job inválido é rejeitado e estado de domínio não vira estado de Job | `JobStatus("NEW")` falha; `type="NEW"` → `RAD-WF-006` 422 sem escrita; `JobStatus` = PENDING/CLAIMED/RUNNING/RETRY_WAIT/SUCCESS/FAILED/CANCELLED/DEAD |
| Persistência/transação/migração | `tests/test_database_migration.py::test_migration_adds_job_queue_from_repost_revision`, `::test_empty_database_migrates_to_head`, `::test_downgrade_reverts_capture_schema`; `tests/test_job_persistence.py::test_job_lifecycle_writes_audit_events` | Migration N→N+1 real e histórico de transições auditável | revision `0007_job`; tabelas `job`/`job_lock` e índice `ix_job_claim`; `JOB_ENQUEUED/CLAIMED/STARTED/SUCCEEDED` com Correlation ID |
| API pública e erros | `tests/test_api_jobs.py::test_enqueue_returns_pending_job_with_persisted_fields`, `::test_unknown_job_returns_structured_404`, `::test_correlation_id_is_generated_when_absent` | Fronteira pública versionada com Correlation ID e erro estruturado | `POST/GET /jobs`, `POST /jobs/claim|start|complete`, `POST/DELETE /locks`; 404 `RAD-WF-007`; 409 `RAD-WF-008/009/004`; 422 `RAD-WF-006`; `Cache-Control: no-store` |

### Acceptance evidence, TKT-13

| Acceptance criterion | Verification |
|---|---|
| Job persiste prioridade, disponibilidade, attempts e Correlation ID | `tests/test_job_domain.py::test_create_job_persists_priority_availability_attempts_and_correlation`; `tests/test_job_persistence.py::test_job_persists_priority_availability_attempts_and_correlation` |
| Claim concorrente concede um único lease válido | `tests/test_job_persistence.py::test_claim_grants_a_single_lease_under_concurrency`; `tests/test_api_jobs.py::test_claim_grants_one_lease_then_no_job_is_available` |
| Locks/leases expiram; worker inválido não confirma execução alheia | `tests/test_job_domain.py::test_expired_lease_is_claimable_by_another_worker`, `::test_worker_cannot_confirm_another_workers_execution`; `tests/test_job_persistence.py::test_lease_expiry_lets_another_worker_recover_and_blocks_the_old_worker`, `::test_worker_cannot_start_or_complete_another_workers_job`, `::test_logical_lock_is_exclusive_and_expires` |
| Schema/job inválido é rejeitado e estado de domínio não vira estado de Job | `tests/test_job_domain.py::test_job_status_is_independent_from_domain_state`, `::test_job_type_rejects_domain_state`; `tests/test_api_jobs.py::test_domain_state_is_never_accepted_as_a_job_state`, `::test_invalid_schema_version_is_rejected`; `tests/test_job_persistence.py::test_invalid_job_is_rejected_without_persisting` |
| Comportamento pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido | `tests/test_api_jobs.py` (10 casos); `RAD-WF-006..010` + `RAD-WF-004`; `AuditEvent` por transição; nenhum teste/guardrail removido |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/08_WORKFLOW_ENGINE.md`, `docs/10_PERSISTENCE_AND_RECOVERY.md`, `docs/ERROR_CATALOG.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-13. Limitações e blockers remanescentes: retry/backoff e Dead Job lifecycle pertencem a RDR-037/RDR-038 (TKT-14) — aqui `max_attempts` é persistido e `attempts` incrementa no claim, mas nenhum job é movido para `RETRY_WAIT`/`FAILED`/`DEAD` e o claim não bloqueia por orçamento de tentativas (recovery não pode ser impedido por lease expirado); o Scheduler (RDR-039/TKT-15) e a recuperação pós-crash (RDR-042/TKT-18) consomem este modelo (o Scheduler passou a existir em TKT-15; a recuperação permanece em ticket próprio); `HumanAction` (RDR-040) para Dead Job/ intervenção é ticket dependente; `job_lock` é lógico e não substitui o lock de destino/compliance dos publishers; nenhum teste live/credenciado foi executado e nenhuma capability foi promovida para AUTO.

## Workflow traceability, TKT-14 (RDR-037, RDR-038, RDR-040)

Escopo: consultar tentativas, classificar falhas por classe, encaminhar Dead Jobs
e materializar HumanAction auditável com relógio controlável. Camadas `unit`,
`contract` e `integration` com SQLite temporário real e clock injetado; nenhum
teste live, credencial, provider externo, IA ou side effect comercial. A
classificação parte do `error_code` (AUT-043/AUT-129), nunca de texto do operador.

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-037 backoff configurado | `tests/test_job_retry_domain.py::test_transient_uses_configured_backoff_and_attempt_limit`, `::test_retry_policy_builds_and_validates`; `tests/test_job_retry_config.py`; `tests/test_job_retry_persistence.py::test_configured_policy_is_used_for_backoff` | `TRANSIENT` usa o backoff configurado e o limite de tentativas | baseline 30/120/600/1800; `attempts=1→30s`, `attempts=2→120s`; policy operador `[7,11]`→`7s`; schedule vazio/`<=0`→`RAD-CFG-010` |
| RDR-037/038 exaustão | `tests/test_job_retry_domain.py::test_transient_exhaustion_produces_dead_and_dead_job_review`; `tests/test_job_retry_persistence.py::test_transient_failure_uses_configured_backoff_and_attempt_limit`; `tests/test_api_job_retry.py::test_exhaustion_returns_dead_and_creates_a_queryable_human_action` | Exaustão produz `DEAD` com HumanAction auditável sem recriar entidade | `attempts=max_attempts` → `DEAD`; `resolution_code=RAD-WF-003`; `JOB_DEAD` + `HUMAN_ACTION_CREATED`; `COUNT(job)=1`; `GET /human-actions/{id}` 200 |
| RDR-037 AUTH/HUMAN sem loop | `tests/test_job_retry_domain.py::test_auth_required_and_human_required_do_not_loop`; `tests/test_job_retry_persistence.py::test_auth_required_does_not_loop_and_raises_a_human_action`; `tests/test_api_job_retry.py::test_auth_required_does_not_loop` | `AUTH_REQUIRED`/`HUMAN_REQUIRED` não entram em loop | `RAD-AI-001`→`DEAD`+`RESTORE_AI_AUTH`; `RAD-WA-001`→`AUTHENTICATE_MARKETPLACE`; `delay_seconds=null`; `attempts` não avança; claim seguinte `RAD-WF-008` |
| RDR-037 permanente sem retry | `tests/test_job_retry_domain.py::test_permanent_never_gets_automatic_retry`, `::test_unknown_error_fails_closed_as_permanent`; `tests/test_job_retry_persistence.py::test_permanent_failure_never_retries`; `tests/test_api_job_retry.py::test_permanent_failure_does_not_retry` | `PERMANENT` não recebe retry automático | `RAD-CAP-004`→`FAILED`; `retryable=false`/`delay_seconds=null`; `JOB_FAILED`; sem HumanAction; claim seguinte `RAD-WF-008`; código desconhecido→`PERMANENT` |
| RDR-040 HumanAction | `tests/test_job_retry_persistence.py::test_exhaustion_creates_auditable_human_action_without_recreating_the_entity`; `tests/test_api_job_retry.py::test_human_action_status_filter_and_invalid_status` | Intervenção formal, auditável e consultável pela fronteira pública | `human_action` OPEN referenciando `entity_type`/`entity_id`; `impact`/`next_steps`; `GET /human-actions`/`{id}`; `status` inválido `RAD-WF-006`; inexistente `RAD-WF-011` |
| Lease/estado e validação | `tests/test_job_retry_domain.py::test_apply_failure_requires_the_lease_owner`, `::test_invalid_error_code_is_rejected`; `tests/test_job_retry_persistence.py::test_fail_requires_the_lease_owner`; `tests/test_api_job_retry.py::test_foreign_worker_cannot_report_the_failure`, `::test_missing_error_code_returns_structured_workflow_error` | Side effect falha fechado e só o dono do lease reporta a falha | worker inválido `RAD-WF-009`; estado inválido `RAD-WF-010`; `error_code` ausente `RAD-WF-006`; job inalterado após negação |
| Persistência/transação/migração | `tests/test_database_migration.py::test_migration_adds_human_action_from_job_revision`, `::test_empty_database_migrates_to_head`, `::test_downgrade_reverts_capture_schema` | Migration N→N+1 real e transição atômica | revision `0008_human_action`; tabela `human_action` + índice `ix_human_action_status`; downgrade remove a tabela; job + human_action na mesma transação |
| Contrato/erros | `tests/test_api_job_retry.py::test_transient_failure_schedules_backoff_from_the_public_boundary`; `docs/04_DATA_CONTRACTS.md`; `docs/ERROR_CATALOG.md` | Fronteira pública versionada com Correlation ID e erro acionável | `POST /jobs/{id}/fail` 200 com `failure`; `GET /human-actions`; `RAD-WF-009/010/011`, `RAD-WF-006`, `RAD-CFG-010`; `Cache-Control: no-store` |

### Acceptance evidence, TKT-14

| Acceptance criterion | Verification |
|---|---|
| TRANSIENT usa backoff configurado e limite de tentativas | `tests/test_job_retry_domain.py::test_transient_uses_configured_backoff_and_attempt_limit`; `tests/test_job_retry_persistence.py::test_transient_failure_uses_configured_backoff_and_attempt_limit`, `::test_configured_policy_is_used_for_backoff`; `tests/test_job_retry_config.py` |
| AUTH_REQUIRED/HUMAN_REQUIRED não entram em loop | `tests/test_job_retry_domain.py::test_auth_required_and_human_required_do_not_loop`; `tests/test_job_retry_persistence.py::test_auth_required_does_not_loop_and_raises_a_human_action`; `tests/test_api_job_retry.py::test_auth_required_does_not_loop` |
| PERMANENT não recebe retry automático | `tests/test_job_retry_domain.py::test_permanent_never_gets_automatic_retry`; `tests/test_job_retry_persistence.py::test_permanent_failure_never_retries`; `tests/test_api_job_retry.py::test_permanent_failure_does_not_retry` |
| Exaustão produz DEAD e HumanAction auditável sem recriar entidade | `tests/test_job_retry_domain.py::test_transient_exhaustion_produces_dead_and_dead_job_review`; `tests/test_job_retry_persistence.py::test_exhaustion_creates_auditable_human_action_without_recreating_the_entity`; `tests/test_api_job_retry.py::test_exhaustion_returns_dead_and_creates_a_queryable_human_action` |
| Comportamento pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido | `tests/test_api_job_retry.py` (7 casos); `POST /jobs/{id}/fail`; `GET /human-actions`; `AuditEvent` por transição; nenhum teste/guardrail removido |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/08_WORKFLOW_ENGINE.md`, `docs/10_PERSISTENCE_AND_RECOVERY.md`, `docs/ERROR_CATALOG.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-14. Limitações e blockers remanescentes: a recuperação pós-crash (RDR-042/TKT-18) continua em ticket próprio e o Scheduler (RDR-039/TKT-15) passou a existir em TKT-15 — aqui o `RETRY_WAIT` apenas torna o job claimável a partir de `available_at`; a resolução/mutação de HumanAction pertence ao Human Actions center (RDR-063), então este ticket só cria `OPEN` e expõe leitura; a classificação é derivada do `error_code` e um código desconhecido falha fechado como `PERMANENT`, então a cobertura de cada integração cresce junto do Error Catalog; o mapeamento `HUMAN_REQUIRED`→`DEAD` (e `PERMANENT`→`FAILED`) é a interpretação adotada porque o SDD-08 não fixa o estado terminal por categoria; nenhum teste live/credenciado foi executado e nenhuma capability foi promovida para AUTO.

## Workflow traceability, TKT-15 (RDR-039)

Escopo: criar schedules `INTERVAL`/`CRON`/`ON_DEMAND` que geram Jobs observáveis
sem sobreposição, coalescendo ticks perdidos e respeitando quiet windows/timezone
com relógio controlado. Camadas `unit`, `contract` e `integration` com SQLite
temporário real e clock injetado; nenhum teste live, credencial, provider
externo, IA ou side effect comercial. O Scheduler apenas cria Jobs (AUT-117).

| Requirement | Test (arquivo::caso) | Acceptance | Evidence |
|---|---|---|---|
| RDR-039 Scheduler só cria Jobs | `tests/test_schedule_domain.py::test_interval_schedule_persists_cadence_and_contract`, `::test_plan_tick_coalesces_missed_ticks_into_one_enqueue`; `tests/test_schedule_persistence.py::test_tick_creates_one_pending_job_and_never_executes` | Scheduler cria Job `PENDING` e nunca executa lógica de negócio | `job` `PENDING`/`attempts=0`; audit do job só `JOB_ENQUEUED`; sem `JOB_CLAIMED/STARTED/SUCCEEDED`; `SCHEDULE_JOB_ENQUEUED` |
| RDR-039 lock equivalente | `tests/test_schedule_domain.py::test_plan_tick_skips_when_equivalent_lock_is_active`; `tests/test_schedule_persistence.py::test_equivalent_lock_defers_tick_and_coalesces`, `::test_concurrent_ticks_never_create_overlapping_jobs`; `tests/test_api_schedules.py::test_equivalent_lock_defers_tick_via_public_boundary` | Lock equivalente ativo impede novo Job sobreposto | `SKIP_LOCKED`/`EQUIVALENT_LOCK_HELD`; `COUNT(job)=0`; `last_tick_at` inalterado; `SCHEDULE_TICK_SKIPPED`; ticks concorrentes → 1 Job (cursor condicional) |
| RDR-039 coalescing | `tests/test_schedule_domain.py::test_occurrence_count_coalesces_interval_backlog`, `::test_occurrence_count_cron_backlog`, `::test_plan_tick_coalesces_missed_ticks_into_one_enqueue`; `tests/test_schedule_persistence.py::test_tick_creates_one_pending_job_and_never_executes`, `::test_cron_schedule_enqueues_coalesced_job` | Ticks perdidos viram um único Job, não um replay | 12 intervalos → 1 Job com `occurrence_count=12`; cron 35min → 1 Job com 7 |
| RDR-039 quiet window/timezone | `tests/test_schedule_domain.py::test_quiet_window_wraps_midnight_in_configured_timezone`, `::test_quiet_window_respects_days`, `::test_plan_tick_skips_in_quiet_window`; `tests/test_schedule_persistence.py::test_quiet_window_defers_with_controlled_clock` | Quiet window no timezone configurado adia com relógio controlado | `America/Maceio` 02:00Z==23:00 local → `SKIP_QUIET_WINDOW`; 12:00Z==09:00 local → 1 Job |
| RDR-039 cadência e validação | `tests/test_schedule_domain.py::test_cron_next_after_matches_weekday_expression`, `::test_cron_step_and_list_fields`, `::test_invalid_cron_and_timezone_fail_closed`, `::test_on_demand_only_enqueues_when_forced`; `tests/test_schedule_persistence.py::test_on_demand_schedule_only_ticks_when_forced`, `::test_disabled_schedule_is_never_ticked` | INTERVAL/CRON/ON_DEMAND validados e falham fechado | cadência mutuamente exclusiva; cron/`timezone`/payload inválidos → `RAD-WF-012`; `ON_DEMAND` só com tick forçado; disabled não enfileira |
| Persistência/transação/migração | `tests/test_database_migration.py::test_migration_adds_schedule_from_human_action_revision`, `::test_empty_database_migrates_to_head`, `::test_downgrade_reverts_capture_schema`; `tests/test_schedule_persistence.py::test_tick_creates_one_pending_job_and_never_executes` | Migration N→N+1 real e tick atômico | revision `0009_schedule`; `uq_schedule_name` + `ix_schedule_enabled`; Job + audit + cursor na mesma transação |
| API pública e erros | `tests/test_api_schedules.py::test_create_and_read_schedule_roundtrip`, `::test_on_demand_tick_creates_pending_job_via_public_boundary`, `::test_unknown_schedule_returns_structured_404`, `::test_invalid_cadence_returns_structured_workflow_error`, `::test_tick_correlation_id_is_generated_when_absent` | Fronteira pública versionada com Correlation ID e erro estruturado | `POST/GET /schedules`, `POST /schedules/{id}/tick`, `.../enable|disable`; 404 `RAD-WF-013`; 422 `RAD-WF-012`; `Cache-Control: no-store` |

### Acceptance evidence, TKT-15

| Acceptance criterion | Verification |
|---|---|
| Scheduler cria Jobs e nunca executa lógica de negócio | `tests/test_schedule_persistence.py::test_tick_creates_one_pending_job_and_never_executes`; `tests/test_api_schedules.py::test_on_demand_tick_creates_pending_job_via_public_boundary`; `tests/test_schedule_domain.py::test_plan_tick_coalesces_missed_ticks_into_one_enqueue` |
| Lock equivalente impede execução sobreposta | `tests/test_schedule_domain.py::test_plan_tick_skips_when_equivalent_lock_is_active`; `tests/test_schedule_persistence.py::test_equivalent_lock_defers_tick_and_coalesces`, `::test_concurrent_ticks_never_create_overlapping_jobs`; `tests/test_api_schedules.py::test_equivalent_lock_defers_tick_via_public_boundary` |
| Ticks perdidos apropriados são coalescidos | `tests/test_schedule_domain.py::test_occurrence_count_coalesces_interval_backlog`, `::test_occurrence_count_cron_backlog`; `tests/test_schedule_persistence.py::test_tick_creates_one_pending_job_and_never_executes`, `::test_cron_schedule_enqueues_coalesced_job` |
| Quiet windows/timezone testados com relógio controlado | `tests/test_schedule_domain.py::test_quiet_window_wraps_midnight_in_configured_timezone`, `::test_plan_tick_skips_in_quiet_window`; `tests/test_schedule_persistence.py::test_quiet_window_defers_with_controlled_clock` |
| Comportamento pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido | `tests/test_api_schedules.py` (9 casos); `POST /schedules/tick`; `RAD-WF-012/013`; `AuditEvent` por tick; nenhum teste/guardrail removido |
| Docs/contratos e matriz QA atualizados | este documento, `docs/03_DOMAIN_MODEL.md`, `docs/04_DATA_CONTRACTS.md`, `docs/08_WORKFLOW_ENGINE.md`, `docs/10_PERSISTENCE_AND_RECOVERY.md`, `docs/ERROR_CATALOG.md`, `README.md` |

Requirement → Test → Acceptance → Evidence completo para TKT-15. Limitações e blockers remanescentes: o Scheduler **consulta** o lock equivalente (`lock_name`, RDR-036), mas quem o adquire/renova/libera é o worker durante a execução; o wiring worker↔lock e a recuperação pós-crash (RDR-042/TKT-18) continuam em tickets próprios. O `POST /schedules/tick` usa o relógio real (a evidência de coalescing/quiet window usa o clock injetado nos testes de integração); a expressão cron é de 5 campos e a busca tem limite de ~5 anos, e a aritmética de avanço é wall-clock (o alvo operacional `America/Maceio` não observa DST). O schedule só cria Jobs V1 já existentes — nenhum worker/execução de negócio foi implementado aqui e nenhuma capability foi promovida para AUTO; nenhum teste live/credenciado foi executado.
