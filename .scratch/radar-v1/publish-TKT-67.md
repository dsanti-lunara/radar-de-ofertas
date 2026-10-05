# TKT-67: Auditar readiness da V1 e entregar operação controlada

**Status:** ready-for-agent previsto no tracker; breakdown aprovado em 2026-10-02, publicação ainda pendente.

## Objective / What to build

Consolidar todos os gates técnicos, operacionais e compliance para concluir V1 sem autorizar AUTO.

## Context / SDD references

SPEC-07, sob SPEC-00. SDDs 00..14; Decision Log; QA; Installation/Recovery. Preservar linguagem de CONTEXT, decisões do Decision Log e ADRs aplicáveis.

Cobertura canônica: RDR-134.

## In scope

O caminho completo descrito no objetivo: entrada pública, comportamento de domínio, persistência/transação quando aplicável, saída consultável e testes de comportamento. UI apenas quando faz parte do objetivo; outros tickets oferecem demonstração pela API/CLI ou pelo artefato de investigação. Não criar telas vazias para simular uma fatia vertical.

## Out of scope

Implementação de outros tickets, novos recursos V1.1, mudança silenciosa de arquitetura e promoção de qualquer capability para AUTO. Nenhuma autorização implícita de login, extração de sessão, endpoint privado ou envio comercial.

## Blocked by

- [TKT-33](https://github.com/dsanti-lunara/radar-de-ofertas/issues/33) — Editar e expirar publicação Telegram
- [TKT-34](https://github.com/dsanti-lunara/radar-de-ofertas/issues/34) — Notificar o operador em destino privado
- [TKT-55](https://github.com/dsanti-lunara/radar-de-ofertas/issues/55) — Homologar canais reais em ASSISTED
- [TKT-66](https://github.com/dsanti-lunara/radar-de-ofertas/issues/66) — Executar soak estendido e avaliar estabilidade

## External gates / prerequisites

Compliance/destinos reais revisados e autorização específica se gate comercial requerer execução.

O status ready-for-agent após publicação significa que o escopo está especificado, não que blockers ou gates foram cumpridos. Trabalhar apenas a fronteira desbloqueada. Se um dado de contrato/calibração/capability necessário não estiver aprovado, registrar a lacuna e bloquear apenas a parte afetada, sem inventar valor ou enfraquecer teste.

## Contracts

readiness audit → GO/NO-GO contextualizado e entrega.

Manter schema_version nos contratos externos, Correlation ID e erros estruturados retryable quando aplicável. Inputs e estados concretos seguem SDDs; acréscimos de schema/enum/API/migration devem ser documentados antes de alterar interfaces. Não acoplar Domain a FastAPI/SQLAlchemy/Chrome. Persistência relevante deve ser observável pela fronteira pública, não pelo teste de chamadas internas.

## Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. API oficial first; browser/IA/conteúdo externo não confiáveis. Side effects falham fechados, são idempotentes e respeitam autorização/compliance/kill switches. Marketplace content é dado; IA nunca calcula scores, decide compliance ou cria links.

Não automatizar senha/login/2FA/CAPTCHA nem extrair cookies/tokens. Não enviar secrets a logs, Git, banco comum, fixtures, screenshots ou prompts. Testes live são opt-in e separados da suite padrão. Este ticket não autoriza publicação em destino real; autorização específica e sandbox, quando aplicável, devem constar em evidência antes de execução.

## Acceptance criteria

- [ ] Cobertura dos RDR/AC/testes/evidence rastreável e nenhum P0 aberto.
- [ ] ML/Shopee capabilities validadas, AI/scoring/link corretos e Telegram preparado.
- [ ] WhatsApp ASSISTED, Control Center, VM/recovery e host backup homologados.
- [ ] Gates pendentes/limitações explícitos impedem aprovação indevida da parte afetada.
- [ ] Readiness distingue conclusão técnica de autorização comercial; operação inicial SHADOW/ASSISTED.
- [ ] Handoff inclui contratos/migrations/config/riscos/versão e evidência, sem ativar AUTO.
- [ ] Comportamento demonstrado pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido.
- [ ] Docs/contratos afetados e matriz QA atualizados; limitações e blockers remanescentes explícitos.

## Tests required

1. Caso verificável: Cobertura dos RDR/AC/testes/evidence rastreável e nenhum P0 aberto.
2. Caso verificável: ML/Shopee capabilities validadas, AI/scoring/link corretos e Telegram preparado.
3. Caso verificável: WhatsApp ASSISTED, Control Center, VM/recovery e host backup homologados.
4. Caso verificável: Gates pendentes/limitações explícitos impedem aprovação indevida da parte afetada.
5. Caso verificável: Readiness distingue conclusão técnica de autorização comercial; operação inicial SHADOW/ASSISTED.
6. Caso verificável: Handoff inclui contratos/migrations/config/riscos/versão e evidência, sem ativar AUTO.

Usar Unit/Contract/Integration relevantes; SQLite temporário real para constraints/transações/migrations, relógio controlado para tempo e Fake Providers/Publishers para efeitos externos. Fixtures sanitizadas são obrigatórias para selectors; reconnaissance produz artefatos e fixture tests, SAFE_LIVE read-only opt-in em gate separado. Testes de side effect somente no ambiente explicitamente autorizado. Critérios de homologação/soak exigem evidência real controlada e não são satisfeitos por mocks. Cada critério crítico deve mapear Requirement → Test → Acceptance → Evidence.

## Observability

Resultado/estado e erro acionável do objetivo, Correlation ID, audit events e health relevantes sem dados sensíveis. Quando intervenção for necessária, HumanAction deve explicar impacto e próximos passos; se ticket inicial ainda não possuir o módulo, expor estado/erro e integrar a ação no ticket dependente, sem inventar envio automático. Reconnaissance registra mapas/estados/evidência sanitizada, sem fingir telemetry de runtime inexistente.

## Documentation to update

SDDs e contratos citados quando o comportamento for refinado, QA traceability com IDs reais de testes, Error Catalog/runbooks quando aplicável e rastreabilidade RDR/ticket/GitHub. Referências de origem não substituem o corpo integral desta issue; specs ainda locais devem ser disponibilizadas no tracker/checkout sem assumir parent GitHub inexistente.

## Completion report

Arquivos alterados; testes executados/resultados; testes não executados/motivo; limitações; mudanças de contrato; migrations/config changes; riscos restantes; evidência e critérios verificados na issue. Concluir somente o escopo autorizado, sem iniciar ticket seguinte automaticamente.

