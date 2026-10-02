# 00, SDD MASTER

## Produto

O Radar Engine V1 é um motor local e persistente para automação de afiliados de **Radar Beauty** e **Casa em Ordem**.

Fluxo oficial:

```text
Discovery
→ Raw Capture
→ Normalization
→ Price History
→ Candidate
→ Deterministic Scoring
→ Decision Matrix
→ AI Editorial Review
→ Opportunity
→ Tracking Context
→ Affiliate Link
→ Content Generation
→ Local Validation
→ Offer Revalidation
→ Compliance
→ Publishing Policy
→ Telegram / WhatsApp
→ Publication Lifecycle
→ Metrics / Feedback
```

## Invariantes

1. Deal Score mede qualidade da oportunidade para o consumidor.
2. Monetization Score mede potencial econômico e nunca torna uma oferta ruim em boa.
3. Confidence mede confiança nos dados, não atratividade.
4. Hard Rules precedem score, IA e monetização.
5. IA recebe fatos estruturados, não HTML bruto.
6. IA não calcula score, não cria link, não decide compliance e não publica diretamente.
7. Affiliate Link só é criado depois da aprovação da oportunidade.
8. Toda publicação é revalidada imediatamente antes do envio.
9. Side effects são idempotentes.
10. Browser, IA e conteúdo externo são tratados como não confiáveis.
11. Marketplace session fica no navegador, não no Core.
12. Telegram usa Bot API.
13. WhatsApp usa Radar Browser Bridge e começa em ASSISTED.
14. A V1 roda em um único Radar Execution Node dentro de VM local.
15. O sistema deve se recuperar de reboot/crash sem perder estado ou duplicar publicação.

## Componentes

```text
Radar Execution Node
├── radar-core
│   ├── Scheduler
│   ├── Workflow Engine
│   ├── Workers
│   ├── Scoring
│   ├── AI orchestration
│   ├── Publishing
│   ├── Backup/Recovery
│   └── Policy Engines
├── radar-api
│   ├── Control Center API
│   ├── Browser Bridge API
│   └── Operator Actions
├── SQLite WAL
├── Control Center
├── Chrome dedicado
│   ├── Mercado Livre
│   ├── Shopee
│   ├── WhatsApp Web
│   └── Radar Browser Bridge
└── Knowledge Pack
```

Externos:
- ChatGPT/AI Provider validado por spike;
- Telegram Bot API;
- APIs oficiais de Mercado Livre e Shopee quando disponíveis.

## Stack congelada

- Linux LTS com desktop leve na VM
- Python 3.13+ alvo, versão exata fixada na implementação
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- SQLite WAL
- asyncio
- httpx
- uv
- React + TypeScript + Vite
- pnpm + Node LTS fixado
- Chrome Extension Manifest V3 + TypeScript
- Playwright para teste/reconnaissance, nunca como runtime de produção
- systemd para `radar-core` e `radar-api`

Não entram na V1:
- Docker em produção
- n8n como orquestrador
- Redis
- RabbitMQ/Kafka
- PostgreSQL
- Nginx/reverse proxy
- cloud deployment
- domínio público

## Modos operacionais

`MANUAL → SHADOW → ASSISTED → AUTO`

A capability técnica de AUTO pode existir sem estar ativada.

## Estados globais

- RUNNING
- PAUSED
- DRAINING
- DEGRADED
- MAINTENANCE_REQUIRED
- RESTRICTED, quando side effects precisam ser limitados

## Spikes obrigatórios

- SPIKE-01, validar provider/autenticação ChatGPT no ambiente real.
- SPIKE-02, descobrir capabilities reais da Shopee Affiliate API da conta.
- SPIKE-03, Browser Reconnaissance ML + Shopee.
- SPIKE-04, Browser Reconnaissance WhatsApp Channels.

Nenhum adapter de navegador real deve ser implementado antes do reconnaissance correspondente.
