# Issue Map

Revisão pós-recon autorizada em 2026-10-03: preservar IDs RDR-001..134. Tickets publicados #1–#67 e cobertura no manifesto `.scratch/radar-v1/publication-plan.json`. RDR-100 valida link manual; RDR-103..111 WA usa GROUP/vínculo, sem Channels. RDR-076/124/125 têm cobertura dividida ML/SP/WA, não três IDs novos.
Este mapa é o backlog canônico inicial. O agente pode fundir issues pequenas quando forem tecnicamente inseparáveis, mas não deve perder seus Acceptance Criteria.

## Foundation

| ID | Issue |
|---|---|
| RDR-001 | Bootstrap monorepo |
| RDR-002 | Configure Python quality toolchain |
| RDR-003 | Configure TypeScript workspace |
| RDR-004 | Implement configuration loader |
| RDR-005 | Implement SecretsProvider abstraction |
| RDR-006 | Bootstrap SQLite + SQLAlchemy |
| RDR-007 | Configure Alembic migrations |
| RDR-008 | Implement structured logging |
| RDR-009 | Implement radarctl skeleton |
| RDR-010 | Implement system health model |

## Domain

| ID | Issue |
|---|---|
| RDR-011 | Implement Product domain |
| RDR-012 | Implement MarketplaceProduct + Offer |
| RDR-013 | Implement PriceObservation |
| RDR-014 | Implement Evidence + RawCapture |
| RDR-015 | Implement DiscoveryEvent + Candidate |
| RDR-016 | Implement Evaluation |
| RDR-017 | Implement Opportunity |
| RDR-018 | Implement AffiliateLink |
| RDR-019 | Implement ContentGeneration |
| RDR-020 | Implement Publication lifecycle |
| RDR-021 | Implement Audit/Domain events |

## Intelligence

| ID | Issue |
|---|---|
| RDR-022 | Implement Brand taxonomy |
| RDR-023 | Implement Price Opportunity |
| RDR-024 | Implement Seller Quality |
| RDR-025 | Implement Demand Score |
| RDR-026 | Implement Brand Fit |
| RDR-027 | Implement Deal Score |
| RDR-028 | Implement Monetization Score |
| RDR-029 | Implement Confidence Engine |
| RDR-030 | Implement Hard/Soft Rules |
| RDR-031 | Implement Purchase Source comparison |
| RDR-032 | Implement Allowed Claims Engine |
| RDR-033 | Implement repost/dedupe rules |

## Workflow

| ID | Issue |
|---|---|
| RDR-034 | Implement persistent Job model |
| RDR-035 | Implement job claiming + leases |
| RDR-036 | Implement locks |
| RDR-037 | Implement retry/backoff |
| RDR-038 | Implement Dead Job lifecycle |
| RDR-039 | Implement Scheduler |
| RDR-040 | Implement HumanAction |
| RDR-041 | Implement workflow state transitions |
| RDR-042 | Implement Recovery Manager |
| RDR-043 | Implement pause/drain/kill switches |
| RDR-044 | Implement integration health |

## AI

| ID | Issue |
|---|---|
| RDR-045 | Implement Knowledge Pack |
| RDR-046 | Define AIProvider contract |
| RDR-047 | Implement FakeAIProvider |
| RDR-048 | Execute AI authentication spike |
| RDR-049 | Implement real AI provider |
| RDR-050 | Implement Editorial Review contract |
| RDR-051 | Implement Content Generation contract |
| RDR-052 | Implement Numeric Guard |
| RDR-053 | Implement Claim Guard |
| RDR-054 | Implement Content Validator |
| RDR-055 | Implement AI result cache |

## UI & Operations

| ID | Issue |
|---|---|
| RDR-056 | Bootstrap Control Center |
| RDR-057 | Implement Home health overview |
| RDR-058 | Implement Opportunity Inbox |
| RDR-059 | Implement Opportunity detail |
| RDR-060 | Implement Human Review |
| RDR-061 | Implement Publication Inbox |
| RDR-062 | Implement Publication detail/timeline |
| RDR-063 | Implement Human Actions center |
| RDR-064 | Implement Integration health |
| RDR-065 | Implement Jobs/Dead Jobs |
| RDR-066 | Implement operational controls |
| RDR-067 | Implement settings UI |

## Telegram

| ID | Issue |
|---|---|
| RDR-068 | Implement Telegram client |
| RDR-069 | Implement deterministic message renderer |
| RDR-070 | Implement TrackingContext |
| RDR-071 | Implement TelegramPublisher |
| RDR-072 | Implement publication idempotency |
| RDR-073 | Implement Telegram message updates |
| RDR-074 | Implement operator alerts |
| RDR-075 | Validate Telegram sandbox E2E |

## Browser foundation

| ID | Issue |
|---|---|
| RDR-076 | Execute Browser Reconnaissance |
| RDR-077 | Execute Shopee API capability spike |
| RDR-078 | Bootstrap Browser Bridge |
| RDR-079 | Implement Core pairing |
| RDR-080 | Implement heartbeat |
| RDR-081 | Implement browser job protocol |
| RDR-082 | Implement persistent browser jobs |
| RDR-083 | Implement Page Detector framework |
| RDR-084 | Implement browser security guards |
| RDR-085 | Implement diagnostic snapshots |
| RDR-086 | Implement Browser Bridge popup |

## Mercado Livre

| ID | Issue |
|---|---|
| RDR-087 | Implement ML API adapter foundation |
| RDR-088 | Implement ML discovery capabilities |
| RDR-089 | Implement ML product normalization |
| RDR-090 | Implement ML browser page detector |
| RDR-091 | Implement ML session detection |
| RDR-092 | Implement ML affiliate link generation |
| RDR-093 | Implement ML product context guard |
| RDR-094 | Validate ML adapter live |

## Shopee

| ID | Issue |
|---|---|
| RDR-095 | Implement Shopee API adapter |
| RDR-096 | Implement supported Shopee discovery |
| RDR-097 | Implement Shopee link API if supported |
| RDR-098 | Implement Shopee browser detector |
| RDR-099 | Implement Shopee assisted capture |
| RDR-100 | Validate operator-generated Shopee link (manual portal; no operational browser generation) |
| RDR-101 | Implement Shopee Sub IDs |
| RDR-102 | Validate Shopee adapter live |

## WhatsApp

| ID | Issue |
|---|---|
| RDR-103 | Implement WhatsApp page detector |
| RDR-104 | Implement destination registry |
| RDR-105 | Implement destination verification |
| RDR-106 | Implement message injection |
| RDR-107 | Implement message hash guard |
| RDR-108 | Implement assisted registered group send |
| RDR-109 | Implement WhatsApp diagnostics |
| RDR-110 | Validate sandbox group E2E |
| RDR-111 | Validate registered destinations and WhatsApp groups in Assisted mode |

## Runtime

| ID | Issue |
|---|---|
| RDR-112 | Implement backup service |
| RDR-113 | Implement restore workflow |
| RDR-114 | Implement retention cleanup |
| RDR-115 | Implement disk protection |
| RDR-116 | Implement radarctl doctor |
| RDR-117 | Implement systemd services |
| RDR-118 | Implement browser autostart |
| RDR-119 | Implement VM installation script |
| RDR-120 | Implement deployment script |
| RDR-121 | Implement upgrade/rollback workflow |

## Hardening & QA

| ID | Issue |
|---|---|
| RDR-122 | Build AI Golden Dataset |
| RDR-123 | Build AI adversarial dataset |
| RDR-124 | Build marketplace fixtures |
| RDR-125 | Implement browser contract tests |
| RDR-126 | Implement security acceptance suite |
| RDR-127 | Implement crash recovery tests |
| RDR-128 | Implement publication crash reconciliation |
| RDR-129 | Implement network outage tests |
| RDR-130 | Implement backup/restore acceptance |
| RDR-131 | Implement VM reboot acceptance |
| RDR-132 | Run 24h Shadow soak |
| RDR-133 | Run extended soak |
| RDR-134 | Production readiness audit |
