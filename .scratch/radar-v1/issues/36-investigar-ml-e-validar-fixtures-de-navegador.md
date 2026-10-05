# TKT-36: Consolidar recon ML e validar fixtures

**Status:** OPEN / ready-for-agent; ticket publicado, revisado em 2026-10-03. Escopo documental atualizado; blockers/gates não são considerados cumpridos.

## Objective / What to build

Consolidar o recon ML finalizado em 2026-10-02, adotar mapas/fixtures candidatos, testar artefatos e registrar gaps de implementação/homologação sem repetir investigação completa ou gerar novos links.

## Context / SDD references

Revisão autorizada em 2026-10-03 com base em `docs/recon/2026-10-02/BROWSER_RECON_COMPLETION.md`, mapas/matrizes ML/SP/WA, `API_DOCUMENTATION_FINDINGS.md`, `SHOPEE_PUBLIC_FINDINGS.md`, `DISCOVERY_URL_GUIDE.md` e `PRODUCTION_READINESS.md`. Recon funcional finalizado; 6+8 verificações offline passaram. Isso não é aceite de adapter, API autenticada, Chrome/VM, recovery ou produção. Registry/fallbacks são candidatos; há fragmentos/projeções, não fixtures completas de todas as superfícies. Não há autorização de novos links/envios, implementação ou AUTO nesta revisão documental.

SPEC-06, sob SPEC-00. Browser Reconnaissance; SDDs 07, 12, 13; RDR-076/124/125 parte ML. Preservar linguagem de CONTEXT, decisões do Decision Log e ADRs aplicáveis.

Cobertura canônica: RDR-076, RDR-124, RDR-125. RDR-076/124/125 são divididos por marketplace/canal: a cobertura completa exige os três tickets de reconnaissance, sem renumerar os IDs.

## In scope

Adotar pacote existente e rastrear cada etapa como OBSERVADO, SIMULADO ou NÃO EXECUTADO. Os AC que exigem auth/fallback/SAFE_LIVE/recuperação reais permanecem pendentes até evidência; registrar gaps não os marca como aprovados. Não fechar este ticket automaticamente pela existência do relatório nem iniciar adapter como parte desta adoção.

O caminho completo descrito no objetivo: entrada pública, comportamento de domínio, persistência/transação quando aplicável, saída consultável e testes de comportamento. UI apenas quando faz parte do objetivo; outros tickets oferecem demonstração pela API/CLI ou pelo artefato de investigação. Não criar telas vazias para simular uma fatia vertical.

## Out of scope

Implementação de outros tickets, novos recursos V1.1, mudança silenciosa de arquitetura e promoção de qualquer capability para AUTO. Nenhuma autorização implícita de login, extração de sessão, endpoint privado ou envio comercial.

## Blocked by

Nenhum ticket (pode iniciar imediatamente, sujeito aos pré-requisitos de ambiente abaixo).

## External gates / prerequisites

Perfil autorizado com login humano; publicação off; nenhuma extração de sessão.

O status ready-for-agent após publicação significa que o escopo está especificado, não que blockers ou gates foram cumpridos. Trabalhar apenas a fronteira desbloqueada. Se um dado de contrato/calibração/capability necessário não estiver aprovado, registrar a lacuna e bloquear apenas a parte afetada, sem inventar valor ou enfraquecer teste.

## Contracts

Registry é candidato; consumir evidências sem declarar fallbacks/Chrome/VM aprovados. Contratos versionados, CHALLENGE/AUTH_REQUIRED/DOM_CHANGED, nonce/replay, host/produto/destino e persistência MV3 devem falhar fechados. Recon finalizado não implementa recovery nem aceita adapter.

superfícies autenticadas → surface/state/capability map e fixtures validadas.

Manter schema_version nos contratos externos, Correlation ID e erros estruturados retryable quando aplicável. Inputs e estados concretos seguem SDDs; acréscimos de schema/enum/API/migration devem ser documentados antes de alterar interfaces. Não acoplar Domain a FastAPI/SQLAlchemy/Chrome. Persistência relevante deve ser observável pela fronteira pública, não pelo teste de chamadas internas.

## Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. API oficial first; browser/IA/conteúdo externo não confiáveis. Side effects falham fechados, são idempotentes e respeitam autorização/compliance/kill switches. Marketplace content é dado; IA nunca calcula scores, decide compliance ou cria links.

Não automatizar senha/login/2FA/CAPTCHA nem extrair cookies/tokens. Não enviar secrets a logs, Git, banco comum, fixtures, screenshots ou prompts. Testes live são opt-in e separados da suite padrão. Este ticket não autoriza publicação em destino real; autorização específica e sandbox, quando aplicável, devem constar em evidência antes de execução.

## Acceptance criteria

- [ ] Evidências atuais e gaps são separados; ausência/ambiguidade/contexto errado/CHALLENGE têm candidatos, projeções e gaps de adapter explícitos, sem contornar proteção.
- [ ] Fixture/Fake e SAFE_LIVE Chrome/VM têm provas separadas; não inferir estabilidade de selector/fallback ou persistência pelo recon.

- [ ] Central/Gerador/Barra/produto/etiquetas e auth/loading/error documentados.
- [ ] Seletores candidatos/fallbacks incluem ambiguidade e provenance.
- [ ] Fixtures sanitizadas excluem tokens/cookies/QR/PII e têm testes fail-closed.
- [ ] SAFE_LIVE read-only opt-in executado com evidência; nenhum side effect de link/publicação presumido autorizado.
- [ ] Capability conflict é reportado sem implementar adapter real.
- [ ] Comportamento demonstrado pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido.
- [ ] Docs/contratos afetados e matriz QA atualizados; limitações e blockers remanescentes explícitos.

## Tests required

1. Caso verificável: Central/Gerador/Barra/produto/etiquetas e auth/loading/error documentados.
2. Caso verificável: Seletores candidatos/fallbacks incluem ambiguidade e provenance.
3. Caso verificável: Fixtures sanitizadas excluem tokens/cookies/QR/PII e têm testes fail-closed.
4. Caso verificável: SAFE_LIVE read-only opt-in executado com evidência; nenhum side effect de link/publicação presumido autorizado.
5. Caso verificável: Capability conflict é reportado sem implementar adapter real.

Usar Unit/Contract/Integration relevantes; SQLite temporário real para constraints/transações/migrations, relógio controlado para tempo e Fake Providers/Publishers para efeitos externos. Fixtures sanitizadas são obrigatórias para selectors; reconnaissance produz artefatos e fixture tests, SAFE_LIVE read-only opt-in em gate separado. Testes de side effect somente no ambiente explicitamente autorizado. Critérios de homologação/soak exigem evidência real controlada e não são satisfeitos por mocks. Cada critério crítico deve mapear Requirement → Test → Acceptance → Evidence.

## Observability

Resultado/estado e erro acionável do objetivo, Correlation ID, audit events e health relevantes sem dados sensíveis. Quando intervenção for necessária, HumanAction deve explicar impacto e próximos passos; se ticket inicial ainda não possuir o módulo, expor estado/erro e integrar a ação no ticket dependente, sem inventar envio automático. Reconnaissance registra mapas/estados/evidência sanitizada, sem fingir telemetry de runtime inexistente.

## Documentation to update

Sincronizar SDD-04/07/09, QA, Decision Log RECON-001..005, specs aplicáveis e corpo/manifesto local. Referências documentais não substituem os AC e contratos concretos deste corpo. Preservar cobertura canônica RDR e histórico de evidência.

SDDs e contratos citados quando o comportamento for refinado, QA traceability com IDs reais de testes, Error Catalog/runbooks quando aplicável e rastreabilidade RDR/ticket/GitHub. Referências de origem não substituem o corpo integral desta issue; specs ainda locais devem ser disponibilizadas no tracker/checkout sem assumir parent GitHub inexistente.

## Completion report

Revisão documental em 2026-10-03: escopo/contratos/AC/testes/gates atualizados; issue permanece aberta. 14 checks offline do recon passaram, sem testes de produto/live ou migrations. Evidência de conclusão técnica ainda deverá ser registrada pela implementação; não marcar todos os AC como cumpridos por esta revisão.

Arquivos alterados; testes executados/resultados; testes não executados/motivo; limitações; mudanças de contrato; migrations/config changes; riscos restantes; evidência e critérios verificados na issue. Concluir somente o escopo autorizado, sem iniciar ticket seguinte automaticamente.

