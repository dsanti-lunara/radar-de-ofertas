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

## Workflow

| Code | Meaning |
|---|---|
| RAD-WF-001 JOB_TIMEOUT | transient timeout |
| RAD-WF-002 RATE_LIMITED | transient rate limit |
| RAD-WF-003 JOB_DEAD | retries esgotados |
| RAD-WF-004 LOCK_UNAVAILABLE | entidade já em processamento |
| RAD-WF-005 REVALIDATION_REQUIRED | dados envelhecidos |

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

## Capture / Domain

Implementação TKT-03 (RDR-011, RDR-012, RDR-014, RDR-015, RDR-021): a captura
manual é validada antes de qualquer escrita e persiste em uma única transação,
portanto falha sem escrita parcial. Erros são retornados no contrato
`{schema_version, status, correlation_id, error}`.

| Code | Meaning | Retry |
|---|---|---|
| RAD-CAP-001 CAPTURE_PAYLOAD_INVALID | payload de captura inválido (schema, enum, URL, valor monetário, schema_version) | no |
| RAD-CAP-002 CAPTURE_SENSITIVE_FIELD | campo sensível (token/secret/cookie/password) recusado na captura | no |
| RAD-CAP-003 CAPTURE_IDENTITY_CONFLICT | corrida de identidade `marketplace + external_id`; identidade já existe | yes |
| RAD-CAP-004 CANDIDATE_NOT_FOUND | Candidate consultado não existe | no |


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
