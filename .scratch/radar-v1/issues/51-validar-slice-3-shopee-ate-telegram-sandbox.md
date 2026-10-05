# TKT-51: Validar Slice 3 Shopee até Telegram sandbox

**Status:** OPEN / ready-for-agent; ticket publicado, revisado em 2026-10-03. Escopo documental atualizado; blockers/gates não são considerados cumpridos.

## Objective / What to build

Comprovar uma rota Shopee validada até Telegram sandbox: captura API+link API, captura pública assistida+link API ou captura assistida+link manual validado, sempre com revalidação atual e guards.

## Context / SDD references

Revisão autorizada em 2026-10-03 com base em `docs/recon/2026-10-02/BROWSER_RECON_COMPLETION.md`, mapas/matrizes ML/SP/WA, `API_DOCUMENTATION_FINDINGS.md`, `SHOPEE_PUBLIC_FINDINGS.md`, `DISCOVERY_URL_GUIDE.md` e `PRODUCTION_READINESS.md`. Recon funcional finalizado; 6+8 verificações offline passaram. Isso não é aceite de adapter, API autenticada, Chrome/VM, recovery ou produção. Registry/fallbacks são candidatos; há fragmentos/projeções, não fixtures completas de todas as superfícies. Não há autorização de novos links/envios, implementação ou AUTO nesta revisão documental.

SPEC-06, sob SPEC-00. SDDs 07, 09, 13, 14; Slice 3 SP. Preservar linguagem de CONTEXT, decisões do Decision Log e ADRs aplicáveis.

Cobertura canônica: RDR-102.

## In scope

O caminho completo descrito no objetivo: entrada pública, comportamento de domínio, persistência/transação quando aplicável, saída consultável e testes de comportamento. UI apenas quando faz parte do objetivo; outros tickets oferecem demonstração pela API/CLI ou pelo artefato de investigação. Não criar telas vazias para simular uma fatia vertical.

## Out of scope

Implementação de outros tickets, novos recursos V1.1, mudança silenciosa de arquitetura e promoção de qualquer capability para AUTO. Nenhuma autorização implícita de login, extração de sessão, endpoint privado ou envio comercial.

## Blocked by

- [TKT-35](https://github.com/dsanti-lunara/radar-de-ofertas/issues/35) — Validar Slice 2 com IA real e Telegram sandbox

Bloqueio alternativo obrigatório: concluir #47+#48 OU #49+#48 OU #49+#50. A rota API herda o gate #37 via #47/#48; a rota manual validada não requer entitlement. Registrar a rota escolhida e sua evidência; não cadastrar os três pares como blockers cumulativos nativos.

## External gates / prerequisites

Uma rota completa validada e sandbox autorizado; API exige SPIKE-02 via #47/#48, manual não exige entitlement. Todas exigem revalidação atual/guards/disclosure.

ready-for-agent significa escopo especificado, não gates cumpridos. Só trabalhar fronteira autorizada/desbloqueada; nenhum novo side effect ou AUTO autorizado por esta revisão.

## Contracts

Shopee tem três superfícies: API oficial para operações recorrentes documentadas; `affiliate.shopee.com.br` manual/diagnóstico; `shopee.com.br` captura pública assistida candidata. Proteção/indisponibilidade não autoriza alternar para browser como contorno. Sem geração operacional recorrente de links por extensão no portal.

Documentação Brasil confirmou POST GraphQL `https://open-api.affiliate.shopee.com.br/graphql`, `productOfferV2`, `shopeeOfferV2`, `shopOfferV2` e mutation `generateShortLink(originUrl, subIds)`; feeds/relatórios também foram documentados, mas sua existência não amplia analytics V1. AppID/Secret só no SecretsProvider. Assinar SHA256 de AppID + Timestamp + bytes JSON exatos + Secret, hex minúsculo; tolerância documentada de 10 minutos. Inconsistência Credential/Credentials precisa de validação oficial no SPIKE-02 antes de runtime.

HTTP 200 com errors/data parcial não é sucesso do contrato. Int64 cruza TypeScript/JSON sem perda (IDs como strings decimais); dinheiro/comissão usa Decimal a partir de strings. priceMin/Max é range de oferta, não preço de SKU escolhido/checkout. Paginação depende da operação; respeitar orçamento/backoff e classificar 10020 por reason sanitizado, 10030 como rate limit e 10035 como entitlement. Acesso da conta/API live permanece pendente; documentação não equivale a API_SUPPORTED nem ausência de acesso a NOT_SUPPORTED global.

Sub IDs preservam até cinco posições (brand, channel, content_type, category, referência interna), sem PII. Mapear/serializar valores explicitamente; comprimento por campo não foi comprovado e é gate para runtime correspondente. Retorno shortLink é literal, não sintetizado/editado. Mutation com resultado desconhecido não recebe retry cego; Core mantém idempotência/auditoria/reconciliação sem presumir chave de idempotência remota.

Captura pública registra source_url/observed_at, shop/item, campanha/categoria e contexto de variante/preço. Descobrir campanha vigente: IDs históricos de promoção não são configuração fixa. Loading difere de EMPTY; CHALLENGE após DOM inicial suspende parte afetada, exige intervenção humana e revalidação na retomada. E-SP-PUB-08 confirmou preço somente da opção 12L; opção preta/checkout/recorrência não foram validados. Cache/TTL/dedupe reduzem consultas, mas sem dado atual verificável por fonte permitida a revalidação pré-envio bloqueia publicação.

validated Shopee route → sandbox acceptance.

Manter schema_version nos contratos externos, Correlation ID e erros estruturados retryable quando aplicável. Inputs e estados concretos seguem SDDs; acréscimos de schema/enum/API/migration devem ser documentados antes de alterar interfaces. Não acoplar Domain a FastAPI/SQLAlchemy/Chrome. Persistência relevante deve ser observável pela fronteira pública, não pelo teste de chamadas internas.

## Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. API oficial first; browser/IA/conteúdo externo não confiáveis. Side effects falham fechados, são idempotentes e respeitam autorização/compliance/kill switches. Marketplace content é dado; IA nunca calcula scores, decide compliance ou cria links.

Não automatizar senha/login/2FA/CAPTCHA nem extrair cookies/tokens. Não enviar secrets a logs, Git, banco comum, fixtures, screenshots ou prompts. Testes live são opt-in e separados da suite padrão. Este ticket não autoriza publicação em destino real; autorização específica e sandbox, quando aplicável, devem constar em evidência antes de execução.

## Acceptance criteria

- [ ] API/portal manual/site público são capabilities distintas; sem extensão operacional recorrente de geração de link no portal ou fallback de proteção.
- [ ] Documentação/Fake não implica API_SUPPORTED; entitlement/credenciais/API live e limites desconhecidos bloqueiam só a fronteira dependente.
- [ ] Preço/variante/condições atuais e contexto shop/item são verificáveis; CHALLENGE/cache/DOM inicial não autorizam publicação.
- [ ] Tracking até cinco posições e retorno literal são preservados; falha/partial/unknown não produz link inventado nem retry cego.

- [ ] Concluir uma rota validada: captura API+link API (#47+#48) OU captura pública assistida+link API (#49+#48) OU captura assistida+link manual validado (#49+#50). Não exigir as três; sem fallback operacional de geração pelo portal.
- [ ] Pelo menos uma rota completa de captura/link deve funcionar, sem exigir API inexistente.
- [ ] Preço/produto/link/Sub IDs/disclosure são corretos e revalidados.
- [ ] Failure/auth/DOM/compliance e crash não duplicam side effect.
- [ ] Capability nenhuma viável bloqueia acceptance e gera conflito, não aprovação fictícia.
- [ ] Comportamento demonstrado pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido.
- [ ] Docs/contratos afetados e matriz QA atualizados; limitações e blockers remanescentes explícitos.

## Tests required

Casos RECON-SP aplicáveis: 200+errors/partial data; Int64/Decimal/range de oferta; assinatura de bytes exatos; paginação específica; 10020/10030/10035; mutation unknown; loading/EMPTY, campanha atual, variante/contexto divergentes e CHALLENGE após render. Fake/fixture primeiro; API live e SIDE_EFFECT em gates próprios.

1. Caso verificável: Concluir uma rota validada: captura API+link API (#47+#48) OU captura pública assistida+link API (#49+#48) OU captura assistida+link manual validado (#49+#50). Não exigir as três; sem fallback operacional de geração pelo portal.
2. Caso verificável: Pelo menos uma rota completa de captura/link deve funcionar, sem exigir API inexistente.
3. Caso verificável: Preço/produto/link/Sub IDs/disclosure são corretos e revalidados.
4. Caso verificável: Failure/auth/DOM/compliance e crash não duplicam side effect.
5. Caso verificável: Capability nenhuma viável bloqueia acceptance e gera conflito, não aprovação fictícia.

Usar Unit/Contract/Integration relevantes; SQLite temporário real para constraints/transações/migrations, relógio controlado para tempo e Fake Providers/Publishers para efeitos externos. Fixtures sanitizadas são obrigatórias para selectors; reconnaissance produz artefatos e fixture tests, SAFE_LIVE read-only opt-in em gate separado. Testes de side effect somente no ambiente explicitamente autorizado. Critérios de homologação/soak exigem evidência real controlada e não são satisfeitos por mocks. Cada critério crítico deve mapear Requirement → Test → Acceptance → Evidence.

## Observability

Resultado/estado e erro acionável do objetivo, Correlation ID, audit events e health relevantes sem dados sensíveis. Quando intervenção for necessária, HumanAction deve explicar impacto e próximos passos; se ticket inicial ainda não possuir o módulo, expor estado/erro e integrar a ação no ticket dependente, sem inventar envio automático. Reconnaissance registra mapas/estados/evidência sanitizada, sem fingir telemetry de runtime inexistente.

## Documentation to update

Sincronizar SDD-04/07/09, QA, Decision Log RECON-001..005, specs aplicáveis e corpo/manifesto local. Referências documentais não substituem os AC e contratos concretos deste corpo. Preservar cobertura canônica RDR e histórico de evidência.

SDDs e contratos citados quando o comportamento for refinado, QA traceability com IDs reais de testes, Error Catalog/runbooks quando aplicável e rastreabilidade RDR/ticket/GitHub. Referências de origem não substituem o corpo integral desta issue; specs ainda locais devem ser disponibilizadas no tracker/checkout sem assumir parent GitHub inexistente.

## Completion report

Revisão documental em 2026-10-03: escopo/contratos/AC/testes/gates atualizados; issue permanece aberta. 14 checks offline do recon passaram, sem testes de produto/live ou migrations. Evidência de conclusão técnica ainda deverá ser registrada pela implementação; não marcar todos os AC como cumpridos por esta revisão.

Arquivos alterados; testes executados/resultados; testes não executados/motivo; limitações; mudanças de contrato; migrations/config changes; riscos restantes; evidência e critérios verificados na issue. Concluir somente o escopo autorizado, sem iniciar ticket seguinte automaticamente.

