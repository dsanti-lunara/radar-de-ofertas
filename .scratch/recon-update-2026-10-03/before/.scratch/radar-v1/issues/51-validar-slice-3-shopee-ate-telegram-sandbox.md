# TKT-51: Validar Slice 3 Shopee até Telegram sandbox

**Status:** ready-for-agent previsto no tracker; breakdown aprovado em 2026-10-02, publicação ainda pendente.

## Objective / What to build

Comprovar o fluxo Shopee por uma combinação de rotas oficialmente suportadas até Telegram sandbox.

## Context / SDD references

SPEC-06, sob SPEC-00. SDDs 07, 09, 13, 14; Slice 3 SP. Preservar linguagem de CONTEXT, decisões do Decision Log e ADRs aplicáveis.

Cobertura canônica: RDR-102.

## In scope

O caminho completo descrito no objetivo: entrada pública, comportamento de domínio, persistência/transação quando aplicável, saída consultável e testes de comportamento. UI apenas quando faz parte do objetivo; outros tickets oferecem demonstração pela API/CLI ou pelo artefato de investigação. Não criar telas vazias para simular uma fatia vertical.

## Out of scope

Implementação de outros tickets, novos recursos V1.1, mudança silenciosa de arquitetura e promoção de qualquer capability para AUTO. Nenhuma autorização implícita de login, extração de sessão, endpoint privado ou envio comercial.

## Blocked by

- TKT-35 — Validar Slice 2 com IA real e Telegram sandbox
- TKT-37 — Validar Shopee Affiliate API da conta (SPIKE-02)

Bloqueio alternativo obrigatório: concluir uma rota suportada — TKT-47 + TKT-48 **OU** TKT-49 + TKT-50. Registrar a rota escolhida após SPIKE-02; não tratar as alternativas como bloqueios cumulativos.

## External gates / prerequisites

Rotas alternativas verificadas; sandbox/conta autorizados e testes live opt-in.

O status ready-for-agent após publicação significa que o escopo está especificado, não que blockers ou gates foram cumpridos. Trabalhar apenas a fronteira desbloqueada. Se um dado de contrato/calibração/capability necessário não estiver aprovado, registrar a lacuna e bloquear apenas a parte afetada, sem inventar valor ou enfraquecer teste.

## Contracts

validated Shopee route → sandbox acceptance.

Manter schema_version nos contratos externos, Correlation ID e erros estruturados retryable quando aplicável. Inputs e estados concretos seguem SDDs; acréscimos de schema/enum/API/migration devem ser documentados antes de alterar interfaces. Não acoplar Domain a FastAPI/SQLAlchemy/Chrome. Persistência relevante deve ser observável pela fronteira pública, não pelo teste de chamadas internas.

## Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. API oficial first; browser/IA/conteúdo externo não confiáveis. Side effects falham fechados, são idempotentes e respeitam autorização/compliance/kill switches. Marketplace content é dado; IA nunca calcula scores, decide compliance ou cria links.

Não automatizar senha/login/2FA/CAPTCHA nem extrair cookies/tokens. Não enviar secrets a logs, Git, banco comum, fixtures, screenshots ou prompts. Testes live são opt-in e separados da suite padrão. Este ticket não autoriza publicação em destino real; autorização específica e sandbox, quando aplicável, devem constar em evidência antes de execução.

## Acceptance criteria

- [ ] Concluir uma rota suportada: API (tickets 47+48) OU assistida (tickets 49+50); não exigir implementação da alternativa sem suporte.
- [ ] Pelo menos uma rota completa de captura/link deve funcionar, sem exigir API inexistente.
- [ ] Preço/produto/link/Sub IDs/disclosure são corretos e revalidados.
- [ ] Failure/auth/DOM/compliance e crash não duplicam side effect.
- [ ] Capability nenhuma viável bloqueia acceptance e gera conflito, não aprovação fictícia.
- [ ] Comportamento demonstrado pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido.
- [ ] Docs/contratos afetados e matriz QA atualizados; limitações e blockers remanescentes explícitos.

## Tests required

1. Caso verificável: Concluir uma rota suportada: API (tickets 47+48) OU assistida (tickets 49+50); não exigir implementação da alternativa sem suporte.
2. Caso verificável: Pelo menos uma rota completa de captura/link deve funcionar, sem exigir API inexistente.
3. Caso verificável: Preço/produto/link/Sub IDs/disclosure são corretos e revalidados.
4. Caso verificável: Failure/auth/DOM/compliance e crash não duplicam side effect.
5. Caso verificável: Capability nenhuma viável bloqueia acceptance e gera conflito, não aprovação fictícia.

Usar Unit/Contract/Integration relevantes; SQLite temporário real para constraints/transações/migrations, relógio controlado para tempo e Fake Providers/Publishers para efeitos externos. Fixtures sanitizadas são obrigatórias para selectors; reconnaissance produz artefatos e fixture tests, SAFE_LIVE read-only opt-in em gate separado. Testes de side effect somente no ambiente explicitamente autorizado. Critérios de homologação/soak exigem evidência real controlada e não são satisfeitos por mocks. Cada critério crítico deve mapear Requirement → Test → Acceptance → Evidence.

## Observability

Resultado/estado e erro acionável do objetivo, Correlation ID, audit events e health relevantes sem dados sensíveis. Quando intervenção for necessária, HumanAction deve explicar impacto e próximos passos; se ticket inicial ainda não possuir o módulo, expor estado/erro e integrar a ação no ticket dependente, sem inventar envio automático. Reconnaissance registra mapas/estados/evidência sanitizada, sem fingir telemetry de runtime inexistente.

## Documentation to update

SDDs e contratos citados quando o comportamento for refinado, QA traceability com IDs reais de testes, Error Catalog/runbooks quando aplicável e rastreabilidade RDR/ticket/GitHub. Referências de origem não substituem o corpo integral desta issue; specs ainda locais devem ser disponibilizadas no tracker/checkout sem assumir parent GitHub inexistente.

## Completion report

Arquivos alterados; testes executados/resultados; testes não executados/motivo; limitações; mudanças de contrato; migrations/config changes; riscos restantes; evidência e critérios verificados na issue. Concluir somente o escopo autorizado, sem iniciar ticket seguinte automaticamente.

