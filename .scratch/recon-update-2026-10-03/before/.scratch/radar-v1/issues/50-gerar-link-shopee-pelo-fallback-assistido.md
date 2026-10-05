# TKT-50: Gerar link Shopee pelo fallback assistido

**Status:** ready-for-agent previsto no tracker; breakdown aprovado em 2026-10-02, publicação ainda pendente.

## Objective / What to build

Usar Link de Conversão browser validado quando apropriado, preservando o contrato de AffiliateLink/tracking.

## Context / SDD references

SPEC-06, sob SPEC-00. SDDs 07, 09, 12, 13; SP recon evidence. Preservar linguagem de CONTEXT, decisões do Decision Log e ADRs aplicáveis.

Cobertura canônica: RDR-100.

## In scope

O caminho completo descrito no objetivo: entrada pública, comportamento de domínio, persistência/transação quando aplicável, saída consultável e testes de comportamento. UI apenas quando faz parte do objetivo; outros tickets oferecem demonstração pela API/CLI ou pelo artefato de investigação. Não criar telas vazias para simular uma fatia vertical.

## Out of scope

Implementação de outros tickets, novos recursos V1.1, mudança silenciosa de arquitetura e promoção de qualquer capability para AUTO. Nenhuma autorização implícita de login, extração de sessão, endpoint privado ou envio comercial.

## Blocked by

- TKT-20 — Gerar link Fake com TrackingContext auditável
- TKT-37 — Validar Shopee Affiliate API da conta (SPIKE-02)
- TKT-49 — Capturar Shopee de forma assistida

## External gates / prerequisites

Fallback confirmado e geração autenticada autorizada; não requer API link quando ela não existir.

O status ready-for-agent após publicação significa que o escopo está especificado, não que blockers ou gates foram cumpridos. Trabalhar apenas a fronteira desbloqueada. Se um dado de contrato/calibração/capability necessário não estiver aprovado, registrar a lacuna e bloquear apenas a parte afetada, sem inventar valor ou enfraquecer teste.

## Contracts

Opportunity + validated fallback → AffiliateLink ou capability unavailable.

Manter schema_version nos contratos externos, Correlation ID e erros estruturados retryable quando aplicável. Inputs e estados concretos seguem SDDs; acréscimos de schema/enum/API/migration devem ser documentados antes de alterar interfaces. Não acoplar Domain a FastAPI/SQLAlchemy/Chrome. Persistência relevante deve ser observável pela fronteira pública, não pelo teste de chamadas internas.

## Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. API oficial first; browser/IA/conteúdo externo não confiáveis. Side effects falham fechados, são idempotentes e respeitam autorização/compliance/kill switches. Marketplace content é dado; IA nunca calcula scores, decide compliance ou cria links.

Não automatizar senha/login/2FA/CAPTCHA nem extrair cookies/tokens. Não enviar secrets a logs, Git, banco comum, fixtures, screenshots ou prompts. Testes live são opt-in e separados da suite padrão. Este ticket não autoriza publicação em destino real; autorização específica e sandbox, quando aplicável, devem constar em evidência antes de execução.

## Acceptance criteria

- [ ] Seleção de rota respeita API first e capability report.
- [ ] Produto/tracking/Sub IDs seguem limites reais da superfície, sem PII.
- [ ] Resultado é validado e auditado antes de persistir.
- [ ] Auth/DOM/context mismatch impede geração e não improvisa fluxo.
- [ ] Capability de fallback ausente vira gap explícito, não adapter presumido.
- [ ] Comportamento demonstrado pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido.
- [ ] Docs/contratos afetados e matriz QA atualizados; limitações e blockers remanescentes explícitos.

## Tests required

1. Caso verificável: Seleção de rota respeita API first e capability report.
2. Caso verificável: Produto/tracking/Sub IDs seguem limites reais da superfície, sem PII.
3. Caso verificável: Resultado é validado e auditado antes de persistir.
4. Caso verificável: Auth/DOM/context mismatch impede geração e não improvisa fluxo.
5. Caso verificável: Capability de fallback ausente vira gap explícito, não adapter presumido.

Usar Unit/Contract/Integration relevantes; SQLite temporário real para constraints/transações/migrations, relógio controlado para tempo e Fake Providers/Publishers para efeitos externos. Fixtures sanitizadas são obrigatórias para selectors; reconnaissance produz artefatos e fixture tests, SAFE_LIVE read-only opt-in em gate separado. Testes de side effect somente no ambiente explicitamente autorizado. Critérios de homologação/soak exigem evidência real controlada e não são satisfeitos por mocks. Cada critério crítico deve mapear Requirement → Test → Acceptance → Evidence.

## Observability

Resultado/estado e erro acionável do objetivo, Correlation ID, audit events e health relevantes sem dados sensíveis. Quando intervenção for necessária, HumanAction deve explicar impacto e próximos passos; se ticket inicial ainda não possuir o módulo, expor estado/erro e integrar a ação no ticket dependente, sem inventar envio automático. Reconnaissance registra mapas/estados/evidência sanitizada, sem fingir telemetry de runtime inexistente.

## Documentation to update

SDDs e contratos citados quando o comportamento for refinado, QA traceability com IDs reais de testes, Error Catalog/runbooks quando aplicável e rastreabilidade RDR/ticket/GitHub. Referências de origem não substituem o corpo integral desta issue; specs ainda locais devem ser disponibilizadas no tracker/checkout sem assumir parent GitHub inexistente.

## Completion report

Arquivos alterados; testes executados/resultados; testes não executados/motivo; limitações; mudanças de contrato; migrations/config changes; riscos restantes; evidência e critérios verificados na issue. Concluir somente o escopo autorizado, sem iniciar ticket seguinte automaticamente.

