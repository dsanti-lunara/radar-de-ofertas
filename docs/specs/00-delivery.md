# SPEC-00: entrega completa do Radar Engine V1

## Problem Statement

O operador possui SDDs aprovados e 134 itens de backlog, mas precisa transformá-los em trabalho rastreável, verificável e ordenado sem perder contratos, guardrails ou decisões do pequeno grill.

## Solution

Uma spec geral coordena sete specs por fluxo. As issues de implementação preservam os IDs RDR do Issue Map, explicitam dependências e AC e seguem os vertical slices e gates aprovados; specs não substituem nem reabrem os SDDs.

## User Stories

1. Como operador, quero rastrear cada requisito até issue, teste, acceptance e evidência, para ter uma entrega segura e verificável.
2. Como operador, quero iniciar por Foundation e persistência confiável, para ter uma entrega segura e verificável.
3. Como operador, quero validar o fluxo completo com providers Fake, para ter uma entrega segura e verificável.
4. Como operador, quero manter scores determinísticos e separados, para ter uma entrega segura e verificável.
5. Como operador, quero controlar SHADOW e ASSISTED com autorização correta, para ter uma entrega segura e verificável.
6. Como operador, quero validar IA real por spike antes de depender dela, para ter uma entrega segura e verificável.
7. Como operador, quero validar Telegram em sandbox antes de produção, para ter uma entrega segura e verificável.
8. Como operador, quero condicionar adapters reais a reconnaissance, para ter uma entrega segura e verificável.
9. Como operador, quero confirmar capabilities da conta Shopee antes de implementação, para ter uma entrega segura e verificável.
10. Como operador, quero validar WhatsApp ASSISTED no final das integrações, para ter uma entrega segura e verificável.
11. Como operador, quero recuperar crash e restore sem duplicação, para ter uma entrega segura e verificável.
12. Como operador, quero operar pelo Control Center sem SQL direto, para ter uma entrega segura e verificável.
13. Como operador, quero homologar notebook/VM com falhas reais controladas, para ter uma entrega segura e verificável.
14. Como operador, quero manter live tests e side effects explicitamente autorizados, para ter uma entrega segura e verificável.
15. Como operador, quero concluir a V1 sem ativar AUTO, para ter uma entrega segura e verificável.
16. Como operador, quero conhecer bloqueios e limitações antes de executar issues, para ter uma entrega segura e verificável.

## Implementation Decisions

Revisão autorizada em 2026-10-03 com base em `docs/recon/2026-10-02/BROWSER_RECON_COMPLETION.md`, mapas/matrizes ML/SP/WA, `API_DOCUMENTATION_FINDINGS.md`, `SHOPEE_PUBLIC_FINDINGS.md`, `DISCOVERY_URL_GUIDE.md` e `PRODUCTION_READINESS.md`. Recon funcional finalizado; 6+8 verificações offline passaram. Isso não é aceite de adapter, API autenticada, Chrome/VM, recovery ou produção. Registry/fallbacks são candidatos; há fragmentos/projeções, não fixtures completas de todas as superfícies. Não há autorização de novos links/envios, implementação ou AUTO nesta revisão documental.

RECON-001..005 governam GROUP, tracking ML e três rotas Shopee. Tickets existentes #1–#67 são a decomposição; preservar RDR-001..134 e não publicar specs/tickets duplicados. RDR-100 valida link manual, não automatiza portal.

- Preservar stack, arquitetura, escopo V1 e backlog RDR-001..RDR-134; não converter specs de fluxo em issues gigantes de implementação.
- GRILL-001: SHADOW sem envio comercial; ASSISTED exige aprovação explícita da publicação; aprovação de Candidate não autoriza envio.
- GRILL-002: envio desconhecido persistido, publicação suspensa, sem reenvio automático e HumanAction; resolução exige evidência suficiente.
- GRILL-003: restore mantém envios bloqueados até reconciliar intervalo posterior ao backup; diagnóstico/processamento seguro podem continuar.
- Providers Fake em desenvolvimento; APIs oficiais preferidas; capability desconhecida não é promessa de produção.

## Testing Decisions

- SPEC-01: Contratos públicos da Application com SQLite temporário real.
- SPEC-02: Avaliação pública de Candidate com fatos e relógio controlados.
- SPEC-03: Comandos públicos da Application para workflow, aprovação e controles operacionais.
- SPEC-04: Contrato AIProvider e validação pública de conteúdo gerado.
- SPEC-05: Comandos públicos de publicação/recovery/restore com SQLite real e Fake Publishers.
- SPEC-06: Contratos Browser Bridge/providers com fixtures sanitizadas; SAFE_LIVE e SIDE_EFFECT em gates separados.
- SPEC-07: API operacional pública e acceptance do Radar Execution Node; UI E2E nos fluxos críticos.
- Fronteiras confirmadas pelo usuário em 2026-10-02; testar comportamento público, falha, recuperação, auditoria e segurança. Não há testes implementados como precedente; contratos SDD e matriz QA são a referência.
- Integrações live não rodam por padrão; fixtures primeiro, SAFE_LIVE depois e SIDE_EFFECT sandbox quando explicitamente autorizado.

## Out of Scope

Implementação nesta etapa, ativação de AUTO, arquitetura distribuída/cloud, funcionalidades V1.1 e mudança silenciosa de decisões aprovadas.

## Further Notes

### Objective / Context / SDD references

Cobrir SDDs 00..14, Decision Log, CONTEXT, ADR 0001, Browser Reconnaissance, Shopee Capability Report, QA, Installation e Recovery Runbook.

### Specs e cobertura

- SPEC-01 — Fundação e domínio: RDR-001..RDR-021. Dependências: Nenhuma spec funcional; primeira entrega executável.
- SPEC-02 — Seleção de oportunidades: RDR-022..RDR-033. Dependências: SPEC-01.
- SPEC-03 — Workflow e autorização: RDR-034..RDR-044; integração com RDR-060, RDR-066 e RDR-108. Dependências: SPEC-01; SPEC-02 para transições de seleção.
- SPEC-04 — IA e conteúdo: RDR-045..RDR-055; RDR-122..RDR-123. Dependências: SPEC-01, SPEC-02 e SPEC-03; provider real condicionado a SPIKE-01/RDR-048.
- SPEC-05 — Publicação e recuperação: RDR-068..RDR-075; RDR-112..RDR-113; RDR-128; integração com RDR-020, RDR-042 e RDR-130. Dependências: SPEC-01, SPEC-03 e SPEC-04; seleção de SPEC-02. WhatsApp usa SPEC-06.
- SPEC-06 — Browser e marketplaces: RDR-076..RDR-111; RDR-124..RDR-125. Dependências: SPEC-01 e SPEC-03; SPEC-05 para publicação. SPIKE-02 para runtime API da conta; recon funcional de SPIKE-03/04 finalizado, mas fixtures/negativos/SAFE_LIVE de adapter continuam gates próprios.
- SPEC-07 — Operação e homologação: RDR-056..RDR-067; RDR-114..RDR-121; RDR-126..RDR-127; RDR-129..RDR-134; integração com RDR-130. Dependências: SPEC-01 para início da UI; demais specs conforme controles e acceptance. Homologação final depende dos fluxos validados.

A spec anterior de autorização/recuperação é incorporada por SPEC-03 e SPEC-05, sem publicação duplicada como oitava spec de fluxo. RDR-130 cruza publicação/restore e homologação; demais integrações explicitadas acima não mudam ownership dos IDs.

### Dependency order / delivery gates

1. Foundation → Domain/Persistence → Scoring → Workflow → Fake E2E (Slice 1).
2. Knowledge/Fake AI e UI podem evoluir após Foundation conforme dependências; SPIKE-01 antes do provider real.
3. AI real + Telegram sandbox (Slice 2).
4. SPIKE-02 e reconnaissance ML/Shopee; Browser Bridge e capabilities reais somente após evidência suficiente → Telegram sandbox (Slice 3).
5. Recon WhatsApp → WhatsApp grupo sandbox ASSISTED (Slice 4).
6. Runtime/recovery → Hardening → Shadow pilot → readiness na VM real.

### Dependencies / blockers

Provider/auth AI ainda requer SPIKE-01; Shopee conta/API autenticada requer SPIKE-02. Recon funcional ML/SP/WA finalizado; adoção das fixtures, gaps e SAFE_LIVE Chrome/VM de adapters permanecem gates. Contratos/Fake Shopee podem avançar offline com documentação oficial, sem promover API_SUPPORTED. Execução comercial depende de compliance revisada e autorização de destino; conclusão técnica não autoriza AUTO.

Specs são publicadas como ready-for-agent para sua execução de planejamento/entrega respeitando dependências. Issues futuras de adapter real não podem ser marcadas executáveis antes do gate correspondente. Publicar specs não executa spikes nem autoriza side effects.

### Contracts / constraints

Usar contratos versionados e estados explícitos; idempotência, Evidence, Correlation ID, precisão monetária, fail closed e least privilege são obrigatórios. Reportar ARCHITECTURE_CONFLICT/CAPABILITY_CONFLICT apenas na parte afetada.

### Acceptance Criteria

- [ ] Contratos, objetivos, AC, testes e blockers usam GROUP e as rotas Shopee coerentes; documentação/recon não substitui os gates de adapter/API/produção.

- [ ] Sete specs cobrem os 134 IDs RDR sem perder AC.
- [ ] Issues executáveis contêm objetivo, escopo, dependências, contratos, restrições, AC, testes, observabilidade e docs.
- [ ] Quatro slices validados com evidência e gates respeitados.
- [ ] Refinamentos do grill cobertos por testes e contratos.
- [ ] VM recupera reboot/crash; backup/restore e segurança homologados.
- [ ] Shadow pilot e readiness completos, sem P0 aberto; produção inicial SHADOW/ASSISTED.

### Tests required / Observability

Matriz QA Unit/Contract/Integration/E2E, testes determinísticos e failure injection, security suite, soak e homologação real. Eventos/health/HumanActions acionáveis sem leakage; Requirement→Test→Acceptance→Evidence.

### Documentation to update / Completion report

Issue Map e QA com links/evidências reais; docs de contratos e operação conforme entregas. Reportar testes executados/não executados, limitações, contratos, migrations/config e riscos. Não implementar nem abrir automaticamente a próxima fase nesta publicação de specs.

