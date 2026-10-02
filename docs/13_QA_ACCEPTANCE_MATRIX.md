# 13, QA and Acceptance Matrix

## Camadas

1. Unit
2. Contract
3. Integration
4. E2E

Quanto mais externa a camada, menor o volume.

## Testes obrigatórios por domínio

### Scoring
- boundaries 59.99/60/79.99/80;
- hard rules precedem scores;
- comissão nunca aumenta Deal Score;
- Deal permanece 0..100;
- dinheiro sem erro de float;
- Confidence por source/freshness/history;
- purchase source guardrail;
- dedupe/repost.

### AI
- schema válido;
- schema inválido;
- enum inválido;
- timeout;
- refusal;
- rate limit;
- prompt injection;
- numeric hallucination;
- unsupported claims;
- URL inventada;
- Golden Dataset;
- adversarial dataset.

Não testar frase exata, testar propriedades.

### Database
- real temporary SQLite;
- WAL;
- FK;
- constraints;
- migrations empty→latest;
- migration N→N+1;
- rollback transacional;
- backup/restore.

### Workflow
- retry;
- no retry em AUTH_REQUIRED;
- Dead Job;
- lock;
- lease expiration;
- missed schedule coalescing;
- candidate aging;
- TTL;
- content staleness;
- recovery pós-crash.

### Browser
Níveis:
- FIXTURE
- SAFE_LIVE
- SIDE_EFFECT

Adapter acceptance:
- fixture pass;
- primary/fallback selector;
- ambiguous selector fail closed;
- DOM_CHANGED;
- AUTH_REQUIRED;
- wrong product/context;
- safe live;
- sandbox side effect quando aplicável.

### Telegram
- send;
- edit;
- invalid destination;
- retry;
- idempotency;
- crash after remote send before local commit;
- lifecycle revision.

### WhatsApp
- sandbox destination;
- destination mismatch blocks;
- message hash mismatch blocks;
- auth required;
- assisted send;
- duplicate prevention.

### Security
- invalid bridge token;
- replayed nonce;
- unauthorized host;
- javascript URL;
- unsupported command;
- destination/brand mismatch;
- secret leakage scan;
- policy block;
- prompt injection;
- duplicate publication.

## Acceptance scenarios

| ID | Cenário | Resultado |
|---|---|---|
| A | Shopee happy path | 1 publicação correta, link/preço/disclosure/tracking corretos |
| B | Deal 45, Monetization 97 | REJECT, sem IA/link/publicação |
| C | preço 79→109 antes do envio | revalidate, rescore, bloquear |
| D | IA escreve preço errado | Numeric Guard bloqueia |
| E | Shopee auth expira | só browser Shopee pausa, restante continua |
| F | WhatsApp está no canal errado | DESTINATION_MISMATCH, zero envio |
| G | Core cai no publishing | reconcile, zero duplicação |
| H | VM reinicia | startup/recovery/schedule coalesced |
| I | restore | histórico volta, secrets/sessions não |
| J | marketplace muda DOM | DOM_CHANGED, circuit breaker, zero clique errado |
| K | prompt injection no produto | contrato preservado, zero secret/execução |
| L | compliance bloqueada | side effect bloqueado mesmo com scores altos |

## Quality gates

### Feature Done
- implementation complete;
- tests pass;
- acceptance pass;
- docs atualizadas;
- nenhum defeito crítico conhecido.

### PR
- format/lint;
- types;
- unit;
- contract;
- integração relevante;
- security relevante.

### Release
- tests;
- migration test;
- backup;
- version tag;
- release notes;
- browser tests se adapter mudou.

## Live tests

Nunca rodam por padrão.

Markers sugeridos:
- unit
- contract
- integration
- browser_live
- ai_live
- telegram_live
- whatsapp_live
- slow

`RADAR_TEST_MODE` deve bloquear destino de produção.

## Shadow gates

Telegram, referência inicial:
- >=50 human-reviewed cases;
- >=90% ordinary agreement;
- 0 P0;
- 0 P1 nos últimos 30 casos;
- 0 duplicate publish;
- 0 invalid affiliate link;
- 100% disclosure.

WhatsApp deve ter gate mais rigoroso e histórico de assisted publications estáveis.

Números são configuráveis/calibráveis, mas o gate é obrigatório.

## Severity

P0:
- destino errado;
- link de produto errado;
- secret leak;
- publicação proibida por compliance.

P1:
- preço factual errado;
- duplicate publication;
- claim comercial grave não sustentado.

P2/P3:
- problemas não críticos de classificação, copy ou UI.

P0 impede AUTO/release.

## Soak

Antes de produção:
- 24h Shadow;
- depois 72h ou período estendido quando próximo da ativação.

Observar:
- memory growth;
- queue leak;
- stuck jobs;
- duplicates;
- browser stability;
- auth;
- log growth.

## Homologação no notebook real

Obrigatório testar:
- VM boot;
- auto-start;
- browser start;
- bridge heartbeat;
- sessions;
- AI;
- Telegram;
- WhatsApp;
- host backup;
- browser restart;
- network outage;
- abrupt process/VM termination.

## QA traceability

Toda decisão crítica deve poder ser ligada a:
`Requirement → Test → Acceptance → Evidence`.

O agente deve expandir esta matriz com IDs de testes reais durante a implementação.
