# Error Catalog

Prefixos sugeridos:
- RAD-SYS
- RAD-DB
- RAD-WF
- RAD-AI
- RAD-BRW
- RAD-ML
- RAD-SP
- RAD-WA
- RAD-TG
- RAD-CMP
- RAD-BKP
- RAD-CFG
- RAD-CAP
- RAD-LINK

## Browser

| Code | Meaning | Retry |
|---|---|---|
| RAD-BRW-001 MARKETPLACE_SESSION_EXPIRED | login manual necessário | no |
| RAD-BRW-002 DOM_CHANGED | UI não corresponde ao adapter | no |
| RAD-BRW-003 COMMAND_NOT_ALLOWED | comando fora da allowlist | no |
| RAD-BRW-004 INVALID_COMMAND_SCHEMA | payload inválido | no |
| RAD-BRW-005 HOST_MISMATCH | host incompatível com job | no |
| RAD-BRW-006 UNTRUSTED_REDIRECT | redirect inesperado | no |
| RAD-BRW-007 PRODUCT_CONTEXT_MISMATCH | produto aberto diferente do esperado | no |
| RAD-BRW-008 DESTINATION_MISMATCH | destino diferente do job | no |
| RAD-BRW-009 MESSAGE_CONTEXT_MISMATCH | mensagem inserida não corresponde ao hash | no |
| RAD-BRW-010 BROWSER_VERSION_INCOMPATIBLE | protocolo/extensão incompatível | no |
| RAD-BRW-011 CHALLENGE | proteção detectada; suspender parte afetada e ação humana | no |

## Marketplace

| Code | Meaning |
|---|---|
| RAD-ML-001 ML_UNSUPPORTED_AFFILIATE_URL | URL não elegível para link |
| RAD-ML-002 AFFILIATE_UI_NOT_FOUND | gerador/barra não encontrada |
| RAD-SP-001 SHOPEE_CAPABILITY_NOT_SUPPORTED | capability não disponível |
| RAD-SP-002 SHOPEE_API_AUTH_REQUIRED | credencial/assinatura/timestamp exige classificação e ação segura; não é sessão browser |
| RAD-SP-003 SHOPEE_API_ACCESS_REQUIRED | entitlement pendente, não NOT_SUPPORTED global |
| RAD-SP-004 SHOPEE_API_RESULT_INCOMPLETE | HTTP 200 com errors/data parcial não satisfaz contrato |
| RAD-SP-005 SHOPEE_LINK_RESULT_UNKNOWN | mutation sem confirmação; reconciliar, sem retry cego |
| RAD-ML-003 ML_TRACKING_LABEL_INVALID | etiqueta inválida ou mapeamento/associação não verificado |
| RAD-ML-004 ML_LINK_RESULT_STALE | erro atual ou resultado sem correlação com tentativa atual |

## Affiliate link / tracking

| Code | Meaning | Retry |
|---|---|---|
| RAD-LINK-001 AFFILIATE_LINK_INPUT_INVALID | input de geração de link inválido (schema_version, referência de tracking, URL original ausente) | no |
| RAD-LINK-002 AFFILIATE_LINK_NOT_FOUND | AffiliateLink consultado não existe | no |
| RAD-LINK-003 AFFILIATE_LINK_URL_INVALID | link retornado inválido (host não permitido, produto/contexto errado, source desconhecido, campo sensível); nunca editado/sintetizado | no |
| RAD-LINK-004 TRACKING_LABEL_INVALID | `tracking_label` fora de `[a-z0-9]{1,30}` ou associação não configurada; nunca normalizado | no |
| RAD-LINK-005 TRACKING_MAPPING_NOT_CONFIGURED | nenhuma etiqueta aprovada mapeia a referência interna; bloqueia o link | no |
| RAD-LINK-006 AFFILIATE_LINK_PROVIDER_UNAVAILABLE | provider de link indisponível | yes |
| RAD-LINK-007 AFFILIATE_LINK_OPPORTUNITY_NOT_LINKABLE | Opportunity não aprovada ou fora de LINK_PENDING/LINK_READY | no |
| RAD-LINK-008 AFFILIATE_LINK_NOT_PRODUCTIVE | link Fake não pode ser usado como link produtivo | no |

## AI

| Code | Meaning |
|---|---|
| RAD-AI-001 AI_AUTH_REQUIRED | auth necessária |
| RAD-AI-002 AI_PROVIDER_UNAVAILABLE | provider indisponível |
| RAD-AI-003 AI_USAGE_UNAVAILABLE | quota/capability indisponível |
| RAD-AI-004 AI_INVALID_RESPONSE | schema inválido |
| RAD-AI-005 UNSUPPORTED_NUMERIC_CLAIM | número não sustentado |
| RAD-AI-006 UNSUPPORTED_CLAIM | claim não sustentado |
| RAD-AI-007 AI_POLICY_VIOLATION | conteúdo externo influenciou contrato |
| RAD-AI-008 AI_REVIEW_INPUT_INVALID | input do Editorial Review inválido (schema_version, channel) |
| RAD-AI-009 AI_REVIEW_NOT_FOUND | AIReview consultada não existe |
| RAD-AI-010 AI_REFUSAL | provider recusou a tarefa; nunca vira aprovação |
| RAD-AI-011 CONTENT_GENERATION_NOT_FOUND | ContentGeneration consultada não existe |
| RAD-AI-012 CONTENT_INPUT_INVALID | input/estado de geração de conteúdo inválido (schema_version, channel, Opportunity terminal ou sem link validado) |
| RAD-AI-013 CONTENT_URL_NOT_ALLOWED | a IA tentou introduzir uma URL; o renderer usa o link validado |
| RAD-AI-014 CONTENT_CHANNEL_INVALID | conteúdo excede as regras do canal |
| RAD-AI-015 CONTENT_COMPLIANCE_BLOCKED | policy de compliance BLOCKED recusa a preview |

## Workflow

| Code | Meaning |
|---|---|
| RAD-WF-001 JOB_TIMEOUT | transient timeout |
| RAD-WF-002 RATE_LIMITED | transient rate limit |
| RAD-WF-003 JOB_DEAD | retries esgotados |
| RAD-WF-004 LOCK_UNAVAILABLE | entidade/lock já em processamento por outro owner (retryable) |
| RAD-WF-005 REVALIDATION_REQUIRED | dados envelhecidos |
| RAD-WF-006 JOB_INPUT_INVALID | input de job/lock inválido (schema_version, type/estado de domínio, prioridade, payload, worker, lease) |
| RAD-WF-007 JOB_NOT_FOUND | job consultado não existe |
| RAD-WF-008 JOB_NOT_CLAIMABLE | nenhum job disponível para claim (ou lease perdido na corrida); retryable |
| RAD-WF-009 JOB_LEASE_NOT_HELD | worker não detém lease válido; não confirma execução alheia nem expirada |
| RAD-WF-010 JOB_STATE_INVALID | transição de estado de Job inválida |
| RAD-WF-011 HUMAN_ACTION_NOT_FOUND | HumanAction consultada não existe |
| RAD-WF-012 SCHEDULE_INPUT_INVALID | input de schedule inválido (schema_version, type, cadência mutuamente exclusiva, cron, timezone, payload, quiet window) |
| RAD-WF-013 SCHEDULE_NOT_FOUND | schedule consultado não existe |
| RAD-WF-014 OPPORTUNITY_NOT_FOUND | Opportunity consultada não existe |
| RAD-WF-015 OPPORTUNITY_TRANSITION_INVALID | transição de estado de Opportunity inválida (rejeitada e auditada) |
| RAD-WF-016 OPPORTUNITY_INPUT_INVALID | input de Opportunity inválido (schema_version, target_state desconhecido, brand/priority) |
| RAD-WF-017 CANDIDATE_REVIEW_REQUIRED | Candidate com decisão REVIEW exige resolução humana antes de virar Opportunity |
| RAD-WF-018 OPERATIONS_INPUT_INVALID | input de operações inválido (schema_version, global_mode, action, integration state, reason) |
| RAD-WF-019 RECOVERY_INPUT_INVALID | input de recovery inválido (schema_version, trigger) |

Implementação TKT-13 (RDR-034..036): `POST /jobs` persiste o job (`PENDING`),
`POST /jobs/claim` concede um único lease e retorna `RAD-WF-008` quando não há
job claimável, `POST /jobs/{id}/start`/`complete` exigem o lease do worker
(`RAD-WF-009` para worker inválido/lease expirado e `RAD-WF-010` para transição
inválida) e `GET /jobs/{id}` retorna `RAD-WF-007` quando o job não existe.
`POST`/`DELETE /locks` usam `RAD-WF-004` para lock ativo de outro owner. Inputs
inválidos (schema_version, `type`/estado de domínio, prioridade, payload
não-JSON/sensível, worker, lease) retornam `RAD-WF-006`; erros usam o contrato
`{schema_version, status:"INVALID", correlation_id, error}`.

Implementação TKT-14 (RDR-037/RDR-038/RDR-040): `POST /jobs/{id}/fail` classifica
o `error_code` e retorna `RETRY_WAIT` (com `delay_seconds`/`available_at` do
backoff configurado), `FAILED` (permanente) ou `DEAD` (exaustão/humano, com
`resolution_code` `RAD-WF-003` na exaustão). Worker sem lease retorna
`RAD-WF-009`, estado inválido `RAD-WF-010`, `error_code` ausente/inválido
`RAD-WF-006`. `DEAD`/exaustão cria uma HumanAction consultável por
`GET /human-actions`/`GET /human-actions/{id}`; ação inexistente retorna
`RAD-WF-011`. Policy de retry inválida bloqueia a API com `RAD-CFG-010`.

Implementação TKT-15 (RDR-039): `POST /schedules` valida o schedule e retorna
`RAD-WF-012` para cadência/`type`/cron/timezone/quiet window/payload inválidos
(payload sensível ou não-JSON incluído), `GET /schedules/{id}` retorna
`RAD-WF-013` quando o schedule não existe e `POST /schedules/tick`/
`POST /schedules/{id}/tick` retornam o relatório auditável de enqueue/skip. Um
tick nunca executa lógica de negócio; um lock equivalente ativo não gera erro,
gera `SKIP_LOCKED` (retryável por natureza no próximo tick) e os ticks perdidos
coalescem. Erros usam o mesmo contrato
`{schema_version, status:"INVALID", correlation_id, error}`.

Implementação TKT-16 (RDR-017/RDR-041): `POST
/candidates/{id}/opportunities` retorna `RAD-CAP-013` quando o Candidate não tem
Evaluation (não é avançado só por estar em processamento), `RAD-WF-005` (409)
quando a Evaluation excede o TTL configurado e `REJECTED`/`REVIEW_REQUIRED` como
decisões válidas (sem Opportunity); `GET /opportunities/{id}` retorna `RAD-WF-014`
quando a Opportunity não existe; `POST /opportunities/{id}/transitions` retorna
`RAD-WF-015` (409) para uma transição inválida — auditada em
`OPPORTUNITY_TRANSITION_REJECTED` antes da resposta — e `RAD-WF-016` (422) para um
`target_state` desconhecido. Policy do workflow inválida bloqueia a API com
`RAD-CFG-011`.

Implementação TKT-17 (RDR-043/RDR-044): `GET /operations` expõe o estado global, o
kill switch e as policies vigentes; `POST /operations/mode`,
`POST`/`DELETE /operations/stop-external-actions` e `PUT /integrations/{name}`
validam o input e retornam `RAD-WF-018` (422) para `schema_version`/`global_mode`/
`action`/`integration state`/`reason` inválidos. `POST /operations/authorize`
retorna `allowed=true/false` com `reason_code` acionável (`SHADOW_NO_COMMERCIAL_SEND`,
`PUBLICATION_APPROVAL_REQUIRED`, `STOP_EXTERNAL_ACTIONS`, `GLOBAL_MODE_*`,
`POLICY_BLOCK`/`POLICY_UNKNOWN`/`POLICY_EXPIRED`/`POLICY_REVIEW_REQUIRED`/
`POLICY_NOT_EFFECTIVE`, `INTEGRATION_UNAVAILABLE`, `MANUAL_MODE`, `ALLOWED`).
Automation policy inválida bloqueia a API com `RAD-CFG-012` e compliance policy
inválida com `RAD-CFG-013`. Erros usam o contrato
`{schema_version, status:"INVALID", correlation_id, error}`.

Implementação TKT-18 (RDR-042): `POST /recovery` executa o Recovery Manager e
retorna o relatório (`RECOVERED`, com contadores de requeue/block/locks/schedules)
e `GET /recovery` expõe o marcador durável (`clean_shutdown`, `recovery_count`).
`POST /recovery/clean-shutdown` grava o marcador de shutdown limpo. Inputs
inválidos (`schema_version`, `trigger`) retornam `RAD-WF-019` (422). Um shutdown
não limpo é auditado (`UNCLEAN_SHUTDOWN_DETECTED`); jobs interrompidos seguros são
reconciliados (`RECOVERY_JOB_REQUEUED`) e jobs de side effect externo de resultado
desconhecido são bloqueados (`RECOVERY_JOB_BLOCKED`, `UNKNOWN_RESULT`), sem
reenvio automático. `radarctl recover` oferece a mesma entrada pela CLI. Erros usam
o contrato `{schema_version, status:"INVALID", correlation_id, error}`.

Implementação TKT-19 (RDR-045..RDR-047/RDR-050): o Editorial Review Fake é
executado por `POST /candidates/{candidate_id}/ai-review` (`schema_version=1.0`,
`channel` `TELEGRAM`/`WHATSAPP`), que lê os fatos sanitizados do Candidate, a
Evaluation imutável mais recente e os `allowed_claims` do backend, seleciona o
contexto mínimo do Knowledge Pack (`brand + channel + task`) e persiste um
`AIReview` append-only com `knowledge_version`/`prompt_version`/`knowledge_hash`,
a decisão estruturada (`APPROVE`/`REVIEW`/`REJECT`) e o snapshot do input. A IA
nunca retorna `AUTO_PUBLISH` (decisão de AutomationPolicy) e uma falha/recusa/
schema inválido retorna `RAD-AI-001..004`/`RAD-AI-010` sem persistir nada, então
nenhuma aprovação cega cria Opportunity. Erros usam o contrato
`{schema_version, status:"INVALID", correlation_id, error}` com `RAD-AI-008`
(input inválido), `RAD-AI-009` (AIReview inexistente), `RAD-CAP-004` (Candidate
inexistente) e `RAD-CAP-013` (Evaluation inexistente). Knowledge Pack inválido
bloqueia a API com `RAD-CFG-014`. `GET /candidates/{candidate_id}/ai-reviews` e
`GET /ai-reviews/{ai_review_id}` consultam as decisões.

A geração de AffiliateLink (TKT-20, RDR-018/RDR-070) só ocorre para Candidate com
Evaluation `APPROVE` e Opportunity em `LINK_PENDING`/`LINK_READY`; a etiqueta
externa é resolvida do mapeamento versionado (nunca injetada pelo caller) e o
link retornado é validado por host/produto/contexto e preservado literalmente.
Candidate não aprovado/Opportunity não linkável retorna `RAD-LINK-007`,
mapeamento ausente `RAD-LINK-005`, etiqueta inválida `RAD-LINK-004`, link
inválido/produto errado/host inválido `RAD-LINK-003`, provider indisponível
`RAD-LINK-006` (retryable) e um link Fake usado produtivamente `RAD-LINK-008`.
Mapeamento de etiquetas inválido bloqueia a API com `RAD-CFG-015`.

A geração de conteúdo (TKT-21, RDR-019/RDR-051..054/RDR-069) ocorre por
`POST /opportunities/{opportunity_id}/content-generations` para uma Opportunity não
terminal que já possui `AffiliateLink` validado. A IA devolve apenas
`headline`/`body`/`cta`/`warnings`; os guards determinísticos precedem conteúdo
utilizável e um número comercial ou claim sem Evidence bloqueia a preview
publicável (`RAD-AI-005`/`RAD-AI-006`) sem persistir nada. Uma URL introduzida pela
IA é recusada (`RAD-AI-013`), um campo sensível `RAD-AI-007`, um schema inválido
`RAD-AI-004`, uma regra de canal `RAD-AI-014`, compliance `BLOCKED` `RAD-AI-015`, um
input/estado inválido (Opportunity terminal ou sem link) `RAD-AI-012` e uma geração
inexistente `RAD-AI-011`. `RAD-WF-014` cobre Opportunity inexistente e
`RAD-CAP-004`/`RAD-CAP-013` Candidate/Evaluation inexistentes. `GET
/opportunities/{opportunity_id}/content-generations` e
`GET /content-generations/{content_generation_id}` consultam as previews e reportam
`STALE` quando um fato relevante muda. O cache `ai_input_hash` (TKT-22, RDR-055)
não introduz código de erro novo: um `cache_hit` reusa um resultado já validado e
nunca transforma uma saída inválida em válida.

Implementação TKT-23 (RDR-020/RDR-072): `POST
/opportunities/{opportunity_id}/publications` publica uma `ContentGeneration`
validada e não-`STALE` de uma Opportunity em `READY_TO_PUBLISH` por um publisher
Fake determinístico. O gate de autorização TKT-17 (`PUBLISH`) e a publication
policy (cap/burst/cooldown/quiet hours) precedem o publisher; um bloqueio retorna
`RAD-PUB-003` (409) com `error.context.reason_code` e **zero** side effect.
`RAD-PUB-001` cobre input/estado inválido, `RAD-PUB-002` uma Publication
inexistente, `RAD-PUB-004` (retryable) um publisher indisponível e `RAD-PUB-005`
uma resposta inválida. `GET /opportunities/{id}/publications` e `GET
/publications/{id}` consultam a timeline. Repetir `idempotency_key` devolve a
Publication persistida (`idempotent_replay=true`) sem novo envio; policy inválida
bloqueia a API com `RAD-CFG-016`. Erros usam o contrato
`{schema_version, status:"INVALID", correlation_id, error}`.

Implementação TKT-24 (RDR-128, ADR 0001/GRILL-002): quando o publisher sinaliza um
envio que pode ter sido aceito sem confirmação local (`PublicationResultUnknown`,
publisher Fake com `crash_after_accept`), `POST
/opportunities/{id}/publications` **não** trata o caso como falha confirmada:
persiste a Publication suspensa (`status=UNKNOWN`, evento `RESULT_UNKNOWN` com o
receipt: destino, revisão, `content_hash`, Correlation ID e `observed_at`),
cria a `HumanAction` (`REVIEW_PUBLICATION`, motivo `SEND_RESULT_UNKNOWN`) e
responde `RAD-PUB-006` (409). Uma suspensão aberta bloqueia qualquer nova
tentativa da Opportunity — inclusive com outra `idempotency_key` — até a
resolução. `POST /publications/{id}/resolve` exige evidência corroborante
(`MESSAGE_MARKER`/`PROVIDER_RECEIPT`/`DESTINATION_AUDIT`); `OPERATOR_NOTE`
isolada é insuficiente e retorna `RAD-PUB-007` (409) sem liberar nova tentativa
nem apagar a suspensão. Com evidência suficiente, `CONFIRM_SENT` marca
`PUBLISHED` (marcador externo registrado) e `CONFIRM_NOT_SENT` marca `FAILED`,
sempre auditado (`PUBLICATION_RESULT_UNKNOWN`, `HUMAN_ACTION_CREATED`,
`PUBLICATION_RESOLVED`, `PUBLICATION_RESOLUTION_BLOCKED`); a nova tentativa
continua sujeita a revalidação/guardrails e a oferta pode expirar durante a
revisão. Os publishers reais (RDR-071/RDR-108) mapeiam o resultado desconhecido
de WA para `RAD-WA-004`; o Slice Fake usa `RAD-PUB-006`. Erros usam o contrato
`{schema_version, status:"INVALID", correlation_id, error}`.

## Publishing

| Code | Meaning |
|---|---|
| RAD-TG-001 TELEGRAM_SEND_FAILED | envio falhou |
| RAD-TG-002 TELEGRAM_DESTINATION_INVALID | destino inválido |
| RAD-WA-001 WHATSAPP_AUTH_REQUIRED | sessão expirada |
| RAD-WA-002 WHATSAPP_DESTINATION_MISMATCH | grupo/vínculo diferente do destino cadastrado; zero clique |
| RAD-WA-003 WHATSAPP_SEND_FAILED | falha de envio confirmada; não usar para resultado desconhecido |
| RAD-WA-004 WHATSAPP_SEND_RESULT_UNKNOWN | evidência insuficiente; suspender, HumanAction e zero reenvio automático |
| RAD-WA-005 WHATSAPP_DESTINATION_IDENTITY_UNVERIFIED | vínculo/identidade não comprovados; bloquear envio |

### Publication (TKT-23, RDR-020/RDR-072)

O contrato genérico de publicação do Slice 1 Fake usa `RAD-PUB-*`; os publishers
reais (RDR-071/RDR-108) mantêm `RAD-TG-*`/`RAD-WA-*` para falhas específicas de
canal.

| Code | Meaning | Retry |
|---|---|---|
| RAD-PUB-001 PUBLICATION_INPUT_INVALID | input de publicação inválido (schema_version, content_generation_id/destination_id/idempotency_key vazios, Opportunity fora de READY_TO_PUBLISH, ContentGeneration de outra Opportunity ou AffiliateLink divergente) | no |
| RAD-PUB-002 PUBLICATION_NOT_FOUND | Publication consultada não existe | no |
| RAD-PUB-003 PUBLICATION_BLOCKED | bloqueio determinístico **antes** do publisher; `error.context.reason_code` é acionável (`SHADOW_NO_COMMERCIAL_SEND`, `PUBLICATION_APPROVAL_REQUIRED`, `STOP_EXTERNAL_ACTIONS`, `POLICY_*`, `REVALIDATION_REQUIRED`, `QUIET_HOURS`, `COOLDOWN_ACTIVE`, `BURST_LIMIT`, `HARD_CAP_REACHED`) | no |
| RAD-PUB-004 PUBLICATION_PUBLISHER_UNAVAILABLE | publisher indisponível; nada é persistido | yes |
| RAD-PUB-005 PUBLICATION_PUBLISHER_INVALID | resposta do publisher inválida (não-mapping, campo sensível/desconhecido, `external_message_id` ausente) | no |
| RAD-PUB-006 PUBLICATION_RESULT_UNKNOWN | resultado do envio desconhecido (crash/timeout após aceitação sem confirmação local); publicação suspensa, HumanAction e zero reenvio automático; nunca falha confirmada | no |
| RAD-PUB-007 PUBLICATION_RESOLUTION_BLOCKED | resolução de resultado desconhecido sem evidência suficiente; a publicação permanece suspensa e nenhuma nova tentativa é liberada | no |

## Compliance

| Code | Meaning |
|---|---|
| RAD-CMP-001 POLICY_BLOCK | policy explicitamente bloqueia |
| RAD-CMP-002 POLICY_REVIEW_REQUIRED | revisão humana exigida |
| RAD-CMP-003 POLICY_EXPIRED | review_due_at vencido |
| RAD-CMP-004 MEDIA_USAGE_NOT_VERIFIED | mídia sem direito validado |

## Database/Backup

| Code | Meaning | Retry |
|---|---|---|
| RAD-DB-001 DATABASE_INTEGRITY_FAILURE | banco inconsistente | no |
| RAD-DB-002 MIGRATION_FAILED | migration não concluída | no |
| RAD-DB-003 DATABASE_UNAVAILABLE | banco inacessível; `radarctl status` read-only reporta sem criar arquivo | yes |
| RAD-BKP-001 BACKUP_FAILED | backup não concluído | |
| RAD-BKP-002 BACKUP_DEGRADED | último backup acima do limite | |
| RAD-BKP-003 RESTORE_VALIDATION_FAILED | pacote inválido | |

## System

| Code | Meaning | Retry |
|---|---|---|
| RAD-SYS-001 HEALTH_PROBE_FAILED | probe de saúde falhou inesperadamente; CLI/API reportam UNHEALTHY sem derrubar o processo | no |

## Configuration / Secrets

| Code | Meaning | Retry |
|---|---|---|
| RAD-CFG-001 CONFIG_INVALID | configuração ausente de schema válido (tipo/enum/JSON) | no |
| RAD-CFG-002 CONFIG_UNREADABLE | arquivo de config indicado não encontrado ou ilegível | no |
| RAD-CFG-003 SECRET_UNAVAILABLE | secret referenciado ausente no armazenamento seguro; bloqueia a capability do componente | no |
| RAD-CFG-004 SECRET_ACCESS_DENIED | componente pediu secret fora do seu escopo de menor privilégio | no |
| RAD-CFG-005 TAXONOMY_INVALID | taxonomia de marcas ausente de schema/semântica válidos (versão, brand, categoria, prioridade, Brand Fit, alias) | no |
| RAD-CFG-006 SELLER_QUALITY_INVALID | normalização de Seller Quality ausente de schema/semântica válidos (versão, score 0..100, bandas sobrepostas, label/chave inválida) | no |
| RAD-CFG-007 DEMAND_INVALID | normalização de Demand ausente de schema/semântica válidos (versão, categoria canônica, sinal, peso/score 0..100, bandas sobrepostas, label/chave inválida) | no |
| RAD-CFG-008 PURCHASE_SOURCE_POLICY_INVALID | policy de Purchase Source ausente de schema/semântica válidos (versão, threshold finito `>=0`, ação `REVIEW`/`SUBSTITUTE`) | no |
| RAD-CFG-009 REPOST_POLICY_INVALID | policy de repost ausente de schema/semântica válidos (versão, cooldown inteiro `>0`, queda finita `>=0`, piso de Deal `0..100`) | no |
| RAD-CFG-010 RETRY_POLICY_INVALID | policy de retry ausente de schema/semântica válidos (versão, schedule de backoff em segundos inteiros `>0`) | no |
| RAD-CFG-011 WORKFLOW_POLICY_INVALID | policy do workflow ausente de schema/semântica válidos (versão, TTL inteiro `>0` ou nulo) | no |
| RAD-CFG-012 AUTOMATION_POLICY_INVALID | automation policy ausente de schema/semântica válidos (versão, `default_mode`, rule com matcher, mode/brand válidos) | no |
| RAD-CFG-013 COMPLIANCE_POLICY_INVALID | compliance policy ausente de schema/semântica válidos (versão, status, timestamps ISO-8601) | no |
| RAD-CFG-014 KNOWLEDGE_INVALID | Knowledge Pack ausente de schema/semântica válidos (versão, prompt, brand/channel, guidance, campo sensível/desconhecido) | no |
| RAD-CFG-015 TRACKING_LABELS_INVALID | mapeamento de etiquetas de tracking ausente de schema/semântica válidos (versão, referência interna, marketplace, label `[a-z0-9]{1,30}`, unicidade) | no |
| RAD-CFG-016 PUBLICATION_POLICY_INVALID | publication policy ausente de schema/semântica válidos (versão, limites inteiros `>0`, timezone IANA, quiet window HH:MM, canal conhecido, override de canal que não afrouxa o threshold) | no |

## Capture / Domain

Implementação TKT-03 (RDR-011, RDR-012, RDR-014, RDR-015, RDR-021): a captura
manual é validada antes de qualquer escrita e persiste em uma única transação,
portanto falha sem escrita parcial. Implementação TKT-04 (RDR-013): a consulta de
histórico `GET /marketplace-products/{id}/price-history` retorna `RAD-CAP-005`
quando o `MarketplaceProduct` não existe. Implementação TKT-05 (RDR-022,
RDR-026): a classificação de categoria retorna `RAD-CAP-004` quando o Candidate
não existe, `RAD-CAP-006` para brand desconhecida e `RAD-CAP-007` quando a
`taxonomy_version` solicitada difere da ativa; lacunas de mapeamento/calibração
não são erros, são warnings explícitos no contrato de classificação.
Implementação TKT-06 (RDR-023): a avaliação de Price Opportunity retorna
`RAD-CAP-004` quando o Candidate não existe e `RAD-CAP-008` quando uma condição
informada na avaliação (coupon_state, coupon_amount, shipping_cost,
comparable_price) é inválida; histórico insuficiente, frete desconhecido,
referência comparável ausente, cupom não confirmado e preço riscado não são
erros, são warnings explícitos no contrato. Implementação TKT-07 (RDR-024): a
avaliação de Seller Quality retorna `RAD-CAP-004` quando o Candidate não existe e
`RAD-CAP-009` quando um sinal informado (reputation, rating, sales_count,
trusted) é malformado; sinal ausente, inválido, sem normalização configurada ou
contraditório não são erros, são warnings explícitos no contrato. Implementação
TKT-08 (RDR-025): a avaliação de Demand retorna `RAD-CAP-004` quando o Candidate
não existe e `RAD-CAP-010` quando um sinal informado (rating_count, trend,
affiliate_portal, badges) é malformado; sinal ausente, inválido, sem normalização
configurada para a categoria ou categoria não resolvida não são erros, são
warnings explícitos no contrato. Implementação TKT-09 (RDR-016, RDR-027..RDR-030):
a avaliação de Candidate retorna `RAD-CAP-004` quando o Candidate não existe e
`RAD-CAP-011` quando um componente de score está fora de `0..100` ou uma Hard Rule
declarada é desconhecida; Hard Rules violadas e dado obrigatório ausente não são
erros de transporte, são `failed_rules`/warnings explícitos que forçam `REJECT`.
Implementação TKT-10 (RDR-031): a comparação de fonte de compra retorna
`RAD-CAP-004` quando o Candidate não existe e `RAD-CAP-012` quando uma oferta/fonte
informada é inválida (source_id vazio/duplicado, preço não positivo, condição
malformada); produto não identificado como equivalente, condições não comparáveis,
frete/cupom não confiáveis e ausência de referência confiável não são erros, são
warnings explícitos no contrato; policy inválida bloqueia a criação da API com
`RAD-CFG-008`.
Implementação TKT-11 (RDR-032): a consulta de allowed claims retorna
`RAD-CAP-004` quando o Candidate não existe, `RAD-CAP-013` quando o Candidate não
possui Evaluation (ou a `evaluation_id` informada não existe) e `RAD-CAP-014`
quando uma condição de cupom informada é inválida; histórico insuficiente para
`LOWEST_OBSERVED_30D`, cupom não confirmado e preço riscado não são erros, são
`omitted_claims`/warnings explícitos no contrato.
Implementação TKT-12 (RDR-033): o guardrail de dedupe/repost retorna
`RAD-CAP-004` quando o Candidate não existe e `RAD-CAP-015` quando o preço atual
ou uma publicação informada é inválida; mudança irrelevante com cooldown ativo,
cupom/condição material sem `Evidence` e cooldown vencido sem Deal forte não são
erros de transporte, são `decision=BLOCKED`/warnings explícitos no contrato;
policy inválida bloqueia a criação da API com `RAD-CFG-009`.
Erros são
retornados no contrato `{schema_version, status, correlation_id, error}`.

| Code | Meaning | Retry |
|---|---|---|
| RAD-CAP-001 CAPTURE_PAYLOAD_INVALID | payload de captura inválido (schema, enum, URL, valor monetário, schema_version) | no |
| RAD-CAP-002 CAPTURE_SENSITIVE_FIELD | campo sensível (token/secret/cookie/password) recusado na captura | no |
| RAD-CAP-003 CAPTURE_IDENTITY_CONFLICT | corrida de identidade `marketplace + external_id`; identidade já existe | yes |
| RAD-CAP-004 CANDIDATE_NOT_FOUND | Candidate consultado não existe | no |
| RAD-CAP-005 MARKETPLACE_PRODUCT_NOT_FOUND | MarketplaceProduct consultado não existe | no |
| RAD-CAP-006 CLASSIFICATION_INPUT_INVALID | brand desconhecida na classificação de categoria | no |
| RAD-CAP-007 TAXONOMY_VERSION_MISMATCH | `taxonomy_version` solicitada difere da taxonomia ativa | no |
| RAD-CAP-008 PRICE_OPPORTUNITY_INPUT_INVALID | condição de Price Opportunity inválida (coupon_state, coupon_amount, shipping_cost, comparable_price) | no |
| RAD-CAP-009 SELLER_QUALITY_INPUT_INVALID | sinal de Seller Quality malformado na avaliação (reputation, rating, sales_count, trusted) | no |
| RAD-CAP-010 DEMAND_INPUT_INVALID | sinal de Demand malformado na avaliação (rating_count, trend, affiliate_portal, badges) | no |
| RAD-CAP-011 EVALUATION_INPUT_INVALID | componente de Evaluation fora de `0..100` ou Hard Rule declarada desconhecida | no |
| RAD-CAP-012 PURCHASE_SOURCE_INPUT_INVALID | oferta/fonte de Purchase Source inválida (source_id vazio/duplicado, preço não positivo, condição malformada) | no |
| RAD-CAP-013 EVALUATION_NOT_FOUND | Evaluation consultada não existe para o Candidate (ou `evaluation_id` informada não existe) | no |
| RAD-CAP-014 ALLOWED_CLAIMS_INPUT_INVALID | condição de Allowed Claims inválida (coupon_state/coupon_amount/coupon_code) | no |
| RAD-CAP-015 REPOST_INPUT_INVALID | entrada de repost inválida (preço atual/publicação não positivo, valor monetário/condição malformados) | no |


Config inválida bloqueia a inicialização de CLI/API antes de qualquer comando
(AUT-224, AUT-225). Secret ausente bloqueia somente a capability afetada; nunca
expõe valor em mensagem, log ou contrato.

## Regra

Erros devem ser acionáveis:
- code;
- mensagem;
- impacto;
- retryable;
- contexto;
- ação sugerida.

Não usar somente "Something went wrong".
