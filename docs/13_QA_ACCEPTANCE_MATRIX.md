# 13, QA and Acceptance Matrix

## Camadas

1. Unit
2. Contract
3. Integration
4. E2E

Quanto mais externa a camada, menor o volume.

## Testes obrigatórios por domínio

### Scoring

Range Shopee/card/desconto riscado não prova preço de variante nem histórico independente. CHALLENGE ou dados atuais indisponíveis impedem revalidação pré-envio; cache não substitui essa evidência.
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
- restore de backup anterior a envio remoto: diagnóstico/processamento seguro retomam, envios permanecem bloqueados até reconciliação;
- jobs restaurados e novas publicações não enviam durante esse bloqueio; ausência de registro local não autoriza reenvio;
- reconciliação pós-restore registra evidência/decisão em auditoria; resultado desconhecido gera HumanAction sem reenvio automático.

### Workflow

Shopee API: 200 com errors/partial data falha fechado; Int64/Decimal preservados, assinatura de bytes exatos, paginação específica, 10020 por reason, 10030/backoff e 10035/entitlement. Mutation unknown não recebe retry cego. ML: etiqueta charset/30/unicidade, resultado stale, social landing com outro produto destacado e contexto catálogo/anúncio errado devem falhar.
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

Recon 2026-10-02 fornece 14 verificações de artefatos, não aceite de adapters. Registry/fallbacks candidatos precisam de testes completos, negativos e SAFE_LIVE no Chrome dedicado/VM antes de SIDE_EFFECT autorizado. CHALLENGE suspende somente parte afetada e exige revalidação na retomada.
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
- resultado remoto desconhecido: registro persistente, publicação suspensa, zero reenvio automático e HumanAction;
- revisão sem evidência suficiente não autoriza nova tentativa;
- send;
- edit;
- invalid destination;
- retry;
- idempotency;
- crash after remote send before local commit;
- lifecycle revision.

### WhatsApp

- GROUP allowlisted, marca e ambiente corretos; homônimos, vínculo ausente/inválido ou troca após preview produzem zero clique;
- serializer canônico multiline/preview/hash; innerText/textContent não são contrato implícito;
- Send ausente/duplicado e marker/status pós-envio ausentes;
- Enviada não comprova entregue/lida; receipt deve corresponder à publication/revision e tentativa;
- crash após envio antes de commit, reload/reconnect/MV3 e mensagem temporária de sete dias preservam dedupe;
- resultado desconhecido suspende e gera HumanAction, sem reenvio automático; restore mantém bloqueio GRILL-003.
- sandbox destination;
- destination mismatch blocks;
- message hash mismatch blocks;
- auth required;
- assisted send;
- duplicate prevention.

### Security
- SHADOW: aprovação de Candidate/publicação não causa envio comercial;
- ASSISTED: aprovação de Candidate não autoriza envio; publicação exige aprovação humana explícita e guardrails vigentes;
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
| F | WhatsApp está no grupo/vínculo errado | DESTINATION_MISMATCH, zero envio |
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
