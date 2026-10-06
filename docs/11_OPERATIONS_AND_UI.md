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

## Implementação (TKT-26, RDR-058/059/060)

O Control Center ganha a navegação **Visão geral / Oportunidades**. A tela
Oportunidades consome `GET /review/inbox` e `GET /review/candidates/{id}` pelo
mesmo polling REST same-origin; cada linha e o detail são dados reais persistidos
(produto, marketplace, preço, Deal, Monetization, Confidence, brand, motivo,
status, breakdown, warnings, preço append-only, Evidence, AI review, timeline e
versões). O portão operacional é exibido no detail (ex.: SHADOW com envio
comercial **bloqueado**), então aprovar um Candidate não aparenta autorizar envio.

O formulário de Human Review oferece **Aprovar / Rejeitar / Editar conteúdo** com
motivo obrigatório e o payload de `EDIT_CONTENT` (headline/body/cta). O envio é
otimista-zero: enquanto a requisição está em andamento o botão fica desabilitado
e, em falha, o erro estruturado do `radar-api` (`RAD-UI-001..003`) vira mensagem
acionável sem mutação local; loading, vazio e indisponível têm feedback textual
(rótulos, nunca só cor). O parser dos contratos fica em
`packages/control-center/src/review/contracts.ts` e o cliente REST em
`.../review/api.ts`; as ações e o estado assíncrono são testáveis sem DOM
(`.../review/state.ts`). A UI não cria capabilities que a API não possui e não
envia conteúdo comercial por conta própria. As telas de Publicações, Ações,
Sistema e Configurações seguem em RDR-061..RDR-067.

## Implementação (TKT-27, RDR-061/062)

O Control Center ganha a navegação **Publicações**. A tela consome `GET
/publications`, `GET /publications/{id}` e `GET /publications/preview/{opportunity_id}`
pelo mesmo polling REST same-origin; cada linha e o detail são dados reais
persistidos (brand, canal, produto, preço, status, revision, external message ID e
última validação) mais a projeção **PREVIEW** de uma Opportunity `READY_TO_PUBLISH`
que ainda não tem publicação aberta — a UI não cria uma `Publication` que a API não
possui (AUT-442, RDR-061). O detail mostra o preview renderizado, o link literal e
o tracking, a revision, o external ID, a última validação, a timeline
(eventos + auditoria) e a `HumanAction` do resultado desconhecido, explicando
impacto e próximos passos sem reenviar sozinha.

A aprovação explícita fica num formulário separado da review de Candidate
(**Aprovar e publicar**): exige confirmação, informa o destino e chama
`POST /opportunities/{id}/publications` com `publication_approved=true`; o envio
continua sujeito ao portão operacional (SHADOW/ASSISTED/compliance/kill switch) e à
revalidação. O **preview não faz envio**. O detail oferece as ações auditadas
**Revalidar** (`POST /publications/{id}/revalidate`), **Expirar** (`/expire`) e
**Cancelar** (`/cancel`); nenhuma delas reenvia e cada uma carrega Correlation ID,
erro estruturado acionável (`RAD-PUB-003`) e feedback textual (rótulo, nunca só
cor). O parser fica em
`packages/control-center/src/publications/contracts.ts`, o cliente em
`.../api.ts` e o estado assíncrono é testável sem DOM (`.../state.ts`).

As telas de Ações, Sistema e Configurações seguem em RDR-063..RDR-067.

## Implementação (TKT-28, RDR-063..RDR-067)

O Control Center ganha a navegação **Ações / Sistema / Configurações**, todas
consumindo a fronteira pública por polling REST same-origin, sem criar
capability que a API não possui.

- **Ações** consome `GET /human-actions`/`GET /human-actions/{id}` e
  `POST /human-actions/{id}/resolve`. A lista mostra tipo, status, entidade,
  motivo e impacto; o detail mostra impacto/próximos passos e a orientação de
  resolução. O formulário de resolução exige motivo e uma confirmação explícita
  (otimista-zero) e só aparece para ação `OPERATOR_ACK` aberta; uma ação
  delegada (`CANDIDATE_REVIEW`/`PUBLICATION_RESOLUTION`) nunca aparece
  executável aqui e explica o fluxo correto (acceptance #5).
- **Sistema** consome `GET /integrations`/`PUT /integrations/{name}` e
  `GET /jobs`. Integrações usam o estado padronizado e um controle habilitar/
  desabilitar/pausar com confirmação; Jobs/Dead Jobs usam o status real com o
  filtro "Somente Dead Jobs" (`status=DEAD`).
- **Configurações** consome `GET /settings` (read model read-only) e os
  controles operacionais `POST /operations/mode` e `POST`/`DELETE
  /operations/stop-external-actions`. Mostra as políticas efetivas
  versionadas/hasheadas, a elegibilidade AUTO critério a critério e o kill
  switch. Toda mudança perigosa exige confirmação e é auditada pelo `radar-api`;
  a UI **nunca promove** uma capability para AUTO (AUT-256, AUT-257, AUT-258).

O parser de cada tela fica em `packages/control-center/src/{actions,system,settings}/contracts.ts`,
o cliente REST em `.../api.ts` e o estado assíncrono é testável sem DOM em
`.../state.ts`. Estados loading/vazio/erro têm feedback textual (rótulo, nunca
só cor). Como as políticas avançadas seguem em arquivo versionado
(`config/*.json`), a tela reflete o snapshot efetivo e não introduz um segundo
fonte de verdade. A geração TS a partir do OpenAPI segue pendente (AUT-395).
