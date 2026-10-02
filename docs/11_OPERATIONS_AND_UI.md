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
