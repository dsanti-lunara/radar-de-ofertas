# Recovery Runbook

## Caso 1, reboot normal da VM/notebook

Esperado:
1. VM inicia;
2. radar-core/radar-api sobem;
3. Recovery Manager executa;
4. Browser inicia quando houver sessão gráfica;
5. Bridge reconecta;
6. sessions são checadas;
7. jobs aguardando retomam.

Nenhuma publicação duplicada.

## Caso 2, Browser não iniciou

Core continua.

Estado:
`BROWSER_OFFLINE`

Browser jobs:
`WAITING_BROWSER`

Ação:
- iniciar sessão gráfica/Chrome;
- verificar Bridge;
- não reiniciar Core sem necessidade.

## Caso 3, ML/Shopee/WhatsApp AUTH_REQUIRED

Somente integração afetada pausa.

Ação:
1. abrir serviço no Chrome dedicado;
2. autenticar manualmente;
3. resolver 2FA/CAPTCHA manualmente;
4. Bridge detecta READY;
5. jobs retomam.

Nunca extrair/injetar cookies.

## Caso 4, AI auth required

Discovery/scoring/history continuam.

Candidates:
`AI_REVIEW_PENDING`

Reautenticar provider e retomar.

## Caso 5, Telegram down

Publicações ficam em RETRY_WAIT.

Isso se aplica a falhas confirmadas e retryable. Se um envio pode ter ocorrido sem confirmação persistida, suspender a publicação, bloquear reenvio automático e abrir HumanAction; não tratar resultado desconhecido como falha confirmada.

Não recriar Opportunity.

## Caso 6, unclean shutdown

Startup deve:
- expirar leases;
- validar locks;
- reconciliar publishing;
- recuperar pending/retry jobs;
- coalescer schedules perdidos;
- gerar audit event.

Implementação (TKT-18): `radarctl recover` ou `POST /recovery` executa o Recovery
Manager e retorna o relatório auditável (`GET /recovery` lê o marcador). Um
shutdown limpo é registrado por `POST /recovery/clean-shutdown`; sem ele o
startup detecta `UNCLEAN_SHUTDOWN_DETECTED`. Jobs interrompidos seguros voltam a
`PENDING` (`RECOVERY_JOB_REQUEUED`) e podem ser claimados de novo; jobs de side
effect externo de resultado desconhecido são bloqueados (`DEAD`,
`RECOVERY_JOB_BLOCKED`/`UNKNOWN_RESULT`) e **não** são reenviados automaticamente —
a suspensão de publicação e a revisão humana são integradas em TKT-24. Locks
órfãos são limpos e schedules perdidos coalescidos em um único Job por schedule.

## Caso 7, DB integrity failure

1. `STOP_EXTERNAL_ACTIONS`;
2. entrar MAINTENANCE_REQUIRED;
3. executar doctor/integrity;
4. não restaurar automaticamente;
5. selecionar backup válido;
6. executar restore explícito.

## Caso 8, restore completo

Fluxo alvo:

```text
pause
→ validate backup
→ safeguard current state
→ restore db/config/knowledge
→ migrate if required
→ integrity check
→ recovery
→ configure secrets
→ reauthenticate services
→ doctor
→ resume safe processing with sends blocked
→ reconcile post-backup interval
→ release sends under current policies
```

Não reenviar jobs restaurados com base apenas na ausência de registro de publicação. Reconciliar os possíveis envios posteriores ao backup com evidência suficiente e registrar a decisão em auditoria. Se o resultado continuar desconhecido, manter a publicação suspensa e abrir HumanAction, mesmo que a oferta expire. Diagnóstico e processamento seguro podem continuar durante a reconciliação.

## Caso 9, recriar VM do zero

```text
clone repo
→ install/bootstrap
→ restore latest backup
→ configure secrets
→ Browser Bridge
→ pair
→ login ML
→ login Shopee
→ login WhatsApp
→ AI auth
→ Telegram
→ doctor
→ start
```

Browser profile não é requisito de restore.

A recriação da VM segue o mesmo bloqueio de envios e reconciliação do Caso 8; `start` não autoriza publicar antes dessa verificação.

## Caso 10, DOM_CHANGED

1. abrir circuit breaker da capability;
2. manter resto do Radar operando;
3. criar HumanAction;
4. entrar BROWSER_RECON_MODE;
5. seguir `BROWSER_RECONNAISSANCE.md`;
6. atualizar selector registry/fixtures;
7. tests;
8. safe live;
9. deploy adapter;
10. fechar circuito.

## Caso 11, P0 de publicação

1. `STOP_EXTERNAL_ACTIONS` ou demote capability;
2. preservar dados;
3. identificar impacto;
4. registrar incident;
5. corrigir;
6. regression test;
7. QA;
8. retomar em SHADOW/ASSISTED.
