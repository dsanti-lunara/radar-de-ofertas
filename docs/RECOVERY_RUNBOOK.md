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

Não recriar Opportunity.

## Caso 6, unclean shutdown

Startup deve:
- expirar leases;
- validar locks;
- reconciliar publishing;
- recuperar pending/retry jobs;
- coalescer schedules perdidos;
- gerar audit event.

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
→ resume
```

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
