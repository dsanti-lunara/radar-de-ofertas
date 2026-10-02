# 02, Architecture

## Contexto

O sistema roda em um notebook dedicado, preferencialmente dentro de uma VM Linux com interface gráfica leve.

```text
Windows Host
└── Radar VM
    ├── radar-core
    ├── radar-api
    ├── SQLite
    ├── Control Center
    ├── Chrome Radar Profile
    │   ├── ML
    │   ├── Shopee
    │   ├── WhatsApp Web
    │   └── Browser Bridge
    └── Backup path montado no host
```

## Processos

### radar-core

Responsável por:
- Scheduler;
- Workflow Engine;
- Worker pools;
- scoring;
- policies;
- AI orchestration;
- publication orchestration;
- lifecycle;
- backup/recovery;
- housekeeping.

### radar-api

Responsável por:
- REST API do Control Center;
- API do Browser Bridge;
- health/read models;
- ações do operador;
- servir os assets estáticos do frontend.

### Chrome

Perfil dedicado, sem navegação pessoal e sem extensões não necessárias.

O Browser Bridge é executor de capabilities autenticadas, não é backend de negócio.

## Direção de dependência

```text
API/UI
 ↓
Application
 ↓
Domain
```

Infraestrutura implementa interfaces usadas pela aplicação:
- repositories;
- marketplace providers;
- AI provider;
- browser executor;
- publishers.

O Domain deve evitar dependência de FastAPI, SQLAlchemy, httpx ou Chrome.

## Capability Registry

Integrações anunciam capabilities como:
- DISCOVERY
- PRODUCT_DETAILS
- REVALIDATION
- AFFILIATE_LINK
- CONVERSION_REPORT

e método:
- API
- BROWSER
- MANUAL

O Workflow escolhe a rota por capability, evitando `if marketplace == ...` espalhado.

## Confiabilidade

- Jobs e estado de domínio são conceitos diferentes.
- Workers não chamam diretamente outros workers.
- Workflow Engine cria a próxima etapa a partir de fatos persistidos.
- Leases e locks expiram.
- Crash gera recovery/reconciliation.
- Side effects são idempotentes.

## Rede

V1 não é exposta à internet.

Preferência:
- Core/API em localhost ou interface privada específica;
- Control Center acessível somente host ↔ VM;
- nenhuma porta no roteador;
- CORS restrito.

## Startup

```text
Host boot
→ VM auto-start
→ systemd inicia radar-core e radar-api
→ sessão gráfica inicia
→ Chrome Radar Profile
→ Browser Bridge heartbeat
→ Recovery Manager
→ health evaluation
→ RUNNING / DEGRADED
```

Auto-login da VM é opcional e documentado como tradeoff de segurança.
