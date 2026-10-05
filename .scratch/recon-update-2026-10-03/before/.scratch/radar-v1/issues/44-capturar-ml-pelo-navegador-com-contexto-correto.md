# TKT-44: Capturar ML pelo navegador com contexto correto

**Status:** ready-for-agent previsto no tracker; breakdown aprovado em 2026-10-02, publicação ainda pendente.

## Objective / What to build

Reconhecer páginas ML reais validadas, detectar sessão e capturar produto sem clique em contexto errado.

## Context / SDD references

SPEC-06, sob SPEC-00. SDDs 07, 12, 13; ML recon evidence. Preservar linguagem de CONTEXT, decisões do Decision Log e ADRs aplicáveis.

Cobertura canônica: RDR-090, RDR-091, RDR-093.

## In scope

O caminho completo descrito no objetivo: entrada pública, comportamento de domínio, persistência/transação quando aplicável, saída consultável e testes de comportamento. UI apenas quando faz parte do objetivo; outros tickets oferecem demonstração pela API/CLI ou pelo artefato de investigação. Não criar telas vazias para simular uma fatia vertical.

## Out of scope

Implementação de outros tickets, novos recursos V1.1, mudança silenciosa de arquitetura e promoção de qualquer capability para AUTO. Nenhuma autorização implícita de login, extração de sessão, endpoint privado ou envio comercial.

## Blocked by

- TKT-36 — Investigar ML e validar fixtures de navegador
- TKT-42 — Detectar página e emitir diagnóstico sanitizado

## External gates / prerequisites

Recon ML suficiente com fixture e SAFE_LIVE; login sempre humano.

O status ready-for-agent após publicação significa que o escopo está especificado, não que blockers ou gates foram cumpridos. Trabalhar apenas a fronteira desbloqueada. Se um dado de contrato/calibração/capability necessário não estiver aprovado, registrar a lacuna e bloquear apenas a parte afetada, sem inventar valor ou enfraquecer teste.

## Contracts

validated ML browser context → page/session/product result.

Manter schema_version nos contratos externos, Correlation ID e erros estruturados retryable quando aplicável. Inputs e estados concretos seguem SDDs; acréscimos de schema/enum/API/migration devem ser documentados antes de alterar interfaces. Não acoplar Domain a FastAPI/SQLAlchemy/Chrome. Persistência relevante deve ser observável pela fronteira pública, não pelo teste de chamadas internas.

## Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. API oficial first; browser/IA/conteúdo externo não confiáveis. Side effects falham fechados, são idempotentes e respeitam autorização/compliance/kill switches. Marketplace content é dado; IA nunca calcula scores, decide compliance ou cria links.

Não automatizar senha/login/2FA/CAPTCHA nem extrair cookies/tokens. Não enviar secrets a logs, Git, banco comum, fixtures, screenshots ou prompts. Testes live são opt-in e separados da suite padrão. Este ticket não autoriza publicação em destino real; autorização específica e sandbox, quando aplicável, devem constar em evidência antes de execução.

## Acceptance criteria

- [ ] Usar apenas seletores/superfícies do gate ML confirmado.
- [ ] AUTH_REQUIRED/CHALLENGE não automatizam autenticação e não entram em retry cego.
- [ ] Marketplace/produto esperado é comparado com contexto real.
- [ ] Fixture primary/fallback/ambiguity e SAFE_LIVE opt-in validam adapter.
- [ ] DOM_CHANGED suspende capability sem derrubar restante.
- [ ] Comportamento demonstrado pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido.
- [ ] Docs/contratos afetados e matriz QA atualizados; limitações e blockers remanescentes explícitos.

## Tests required

1. Caso verificável: Usar apenas seletores/superfícies do gate ML confirmado.
2. Caso verificável: AUTH_REQUIRED/CHALLENGE não automatizam autenticação e não entram em retry cego.
3. Caso verificável: Marketplace/produto esperado é comparado com contexto real.
4. Caso verificável: Fixture primary/fallback/ambiguity e SAFE_LIVE opt-in validam adapter.
5. Caso verificável: DOM_CHANGED suspende capability sem derrubar restante.

Usar Unit/Contract/Integration relevantes; SQLite temporário real para constraints/transações/migrations, relógio controlado para tempo e Fake Providers/Publishers para efeitos externos. Fixtures sanitizadas são obrigatórias para selectors; reconnaissance produz artefatos e fixture tests, SAFE_LIVE read-only opt-in em gate separado. Testes de side effect somente no ambiente explicitamente autorizado. Critérios de homologação/soak exigem evidência real controlada e não são satisfeitos por mocks. Cada critério crítico deve mapear Requirement → Test → Acceptance → Evidence.

## Observability

Resultado/estado e erro acionável do objetivo, Correlation ID, audit events e health relevantes sem dados sensíveis. Quando intervenção for necessária, HumanAction deve explicar impacto e próximos passos; se ticket inicial ainda não possuir o módulo, expor estado/erro e integrar a ação no ticket dependente, sem inventar envio automático. Reconnaissance registra mapas/estados/evidência sanitizada, sem fingir telemetry de runtime inexistente.

## Documentation to update

SDDs e contratos citados quando o comportamento for refinado, QA traceability com IDs reais de testes, Error Catalog/runbooks quando aplicável e rastreabilidade RDR/ticket/GitHub. Referências de origem não substituem o corpo integral desta issue; specs ainda locais devem ser disponibilizadas no tracker/checkout sem assumir parent GitHub inexistente.

## Completion report

Arquivos alterados; testes executados/resultados; testes não executados/motivo; limitações; mudanças de contrato; migrations/config changes; riscos restantes; evidência e critérios verificados na issue. Concluir somente o escopo autorizado, sem iniciar ticket seguinte automaticamente.

