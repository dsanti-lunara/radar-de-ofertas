# 11, Operations and Minimal UI

## Control Center

Aplicação web local, cliente do Core.

Navegação:
- Visão Geral
- Oportunidades
- Publicações
- Ações
- Sistema
- Configurações

A UI não é necessária para o Core continuar funcionando.

## Home

Responder:
1. o Radar está funcionando?
2. algo precisa de mim?
3. o que está fazendo?
4. o que publicou?
5. há falha?

Health strip:
- Core
- Database
- Scheduler
- ChatGPT/AI
- Browser
- ML
- Shopee
- WhatsApp
- Telegram
- Backup

## Opportunity Inbox

Mostrar:
- produto;
- marketplace;
- preço;
- Deal;
- Monetization;
- Confidence;
- brand;
- motivo principal;
- status.

Detail:
- score breakdown;
- price history;
- warnings;
- AI review;
- Evidence;
- timeline.

## Human Review

Mostrar decisão do sistema/IA e permitir:
- Approve;
- Reject;
- Edit content.

Guardar generated vs final content.

## Publications

Inbox:
- brand;
- channel;
- product;
- price;
- status.

Detail:
- opportunity;
- affiliate link;
- tracking;
- content;
- external message id;
- revisions;
- timeline;
- last validation.

Ações:
- revalidate;
- expire;
- reprocess content;
- regenerate link;
- no repost;
- cancel.

## Human Actions

Centralizar:
- auth required;
- reviews;
- data conflict;
- DOM changed;
- AI auth;
- backup failure;
- dead jobs.

Severidade:
- INFO
- ATTENTION
- CRITICAL

Toda ação deve explicar impacto.

## System

Subáreas:
- Integrations
- Workers
- Jobs
- Dead Jobs
- Backups
- Versions
- Diagnostics

## Settings

Somente controles operacionais frequentes:
- automation modes;
- discovery;
- publication caps;
- quiet hours;
- kill switches;
- integration enable/disable.

Configuração avançada pode continuar em arquivo.

## AUTO eligibility

A UI pode mostrar readiness, nunca promover sozinha.

Critérios devem ser explícitos, por exemplo:
- samples;
- agreement;
- P0/P1;
- validation failures;
- integration health.

## Operator alerts

Telegram privado pode receber somente alertas acionáveis:
- AUTH_REQUIRED;
- BACKUP_FAILED;
- DOM_CHANGED;
- AI_AUTH_REQUIRED;
- TELEGRAM_DOWN;
- DATABASE_ERROR;
- DISK_CRITICAL.

Deduplicar por fingerprint/cooldown.

## Metrics

Técnicas:
- queue age;
- failure rate;
- worker status;
- latency;
- backup age;
- disk free.

Operacionais:
- candidates;
- strong candidates;
- approved;
- published;
- rejected;
- expired;
- human interventions;
- automation rate;
- override rate;
- browser intervention rate.

Métricas comerciais só aparecem quando houver atribuição real.

## UI principles

- desktop-first;
- responsiva o suficiente;
- moderadamente densa;
- sem dashboard template genérico;
- status não dependem só de cor;
- acessibilidade básica;
- polling, não WebSocket, na V1.

## Implementação (TKT-17, RDR-043/044)

Os controles operacionais são a fronteira pública que a Home/Settings consumirão:
`GET /operations` (modo global, kill switch, automation/compliance policy),
`POST /operations/mode` (pause/drain/resume/maintenance),
`POST`/`DELETE /operations/stop-external-actions`, `POST /operations/authorize`
(permissão/bloqueio de uma ação) e `GET /integrations`/`PUT /integrations/{name}`
(saúde padronizada por integração). `DRAINING` bloqueia novos side effects e
mantém leitura/diagnóstico/recovery; uma integração não operacional isola apenas o
próprio escopo (AUT-315). Comandos e decisões de side effect são auditáveis e
carregam Correlation ID. Esta fatia é demonstrável pela API; a UI dedicada
permanece nos tickets de Control Center (RDR-057/RDR-064/RDR-066). Ver
`docs/08_WORKFLOW_ENGINE.md` e `docs/04_DATA_CONTRACTS.md`.

## Implementação (TKT-25, RDR-056/057)

O Control Center é um app React + TypeScript + Vite (`packages/control-center`)
com polling REST e sem WebSocket (AUT-391..394). A Home consulta o read model
`GET /health/overview` a cada intervalo e desenha o health strip com as
capabilities canônicas (Core, Database, Scheduler, IA/ChatGPT, Browser, Mercado
Livre, Shopee, WhatsApp, Telegram, Backup). Cada item mostra o estado por texto
(`Saudável`/`Degradado`/`Indisponível`/`Desconhecido`), nunca só por cor, e uma
capability sem integração registrada ou sem probe é `UNKNOWN` — o strip não
inventa capacidade (AUT-243, AUT-315). Um erro de API vira mensagem acionável e
local, sem vazar corpo/credencial.

A UI compilada é servida pelo próprio `radar-api` a partir de
`packages/control-center/dist` (override `RADAR_CONTROL_CENTER_DIST`), montada
em `/` depois das rotas da API e apenas em `127.0.0.1` (AUT-401/AUT-402). A UI
não é pré-requisito do Core: sem build, a API continua servindo saúde/read models
(AUT-442). Build local: `pnpm --filter @radar/control-center build` e então
`radar-api`. Em desenvolvimento, `pnpm --filter @radar/control-center dev` faz
proxy de `/health` para `127.0.0.1:8000`. As demais telas (Inbox, Publicações,
Ações, Sistema, Configurações) seguem em RDR-058..RDR-067.
