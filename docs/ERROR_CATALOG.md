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

## Marketplace

| Code | Meaning |
|---|---|
| RAD-ML-001 ML_UNSUPPORTED_AFFILIATE_URL | URL não elegível para link |
| RAD-ML-002 AFFILIATE_UI_NOT_FOUND | gerador/barra não encontrada |
| RAD-SP-001 SHOPEE_CAPABILITY_NOT_SUPPORTED | capability não disponível |
| RAD-SP-002 SHOPEE_API_AUTH_REQUIRED | API precisa reautenticar |

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
| RAD-WA-002 WHATSAPP_DESTINATION_MISMATCH | canal errado |
| RAD-WA-003 WHATSAPP_SEND_FAILED | envio não confirmado |

## Compliance

| Code | Meaning |
|---|---|
| RAD-CMP-001 POLICY_BLOCK | policy explicitamente bloqueia |
| RAD-CMP-002 POLICY_REVIEW_REQUIRED | revisão humana exigida |
| RAD-CMP-003 POLICY_EXPIRED | review_due_at vencido |
| RAD-CMP-004 MEDIA_USAGE_NOT_VERIFIED | mídia sem direito validado |

## Database/Backup

| Code | Meaning |
|---|---|
| RAD-DB-001 DATABASE_INTEGRITY_FAILURE | banco inconsistente |
| RAD-DB-002 MIGRATION_FAILED | migration não concluída |
| RAD-BKP-001 BACKUP_FAILED | backup não concluído |
| RAD-BKP-002 BACKUP_DEGRADED | último backup acima do limite |
| RAD-BKP-003 RESTORE_VALIDATION_FAILED | pacote inválido |

## Regra

Erros devem ser acionáveis:
- code;
- mensagem;
- impacto;
- retryable;
- contexto;
- ação sugerida.

Não usar somente "Something went wrong".
