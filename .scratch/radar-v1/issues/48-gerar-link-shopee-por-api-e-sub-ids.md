# TKT-48: Gerar link Shopee por API e Sub IDs

**Status:** OPEN / ready-for-agent; ticket publicado, revisado em 2026-10-03. Escopo documental atualizado; blockers/gates não são considerados cumpridos.

## Objective / What to build

Gerar AffiliateLink Shopee por API oficial a partir de Opportunity aprovada e contexto/tracking verificáveis, independentemente da rota que capturou o produto. Contratos/Fake primeiro; API autenticada depende de SPIKE-02.

## Context / SDD references

Revisão autorizada em 2026-10-03 com base em `docs/recon/2026-10-02/BROWSER_RECON_COMPLETION.md`, mapas/matrizes ML/SP/WA, `API_DOCUMENTATION_FINDINGS.md`, `SHOPEE_PUBLIC_FINDINGS.md`, `DISCOVERY_URL_GUIDE.md` e `PRODUCTION_READINESS.md`. Recon funcional finalizado; 6+8 verificações offline passaram. Isso não é aceite de adapter, API autenticada, Chrome/VM, recovery ou produção. Registry/fallbacks são candidatos; há fragmentos/projeções, não fixtures completas de todas as superfícies. Não há autorização de novos links/envios, implementação ou AUTO nesta revisão documental.

SPEC-06, sob SPEC-00. SDDs 04, 07, 09, 12, 13; Shopee Capability Report. Preservar linguagem de CONTEXT, decisões do Decision Log e ADRs aplicáveis.

Cobertura canônica: RDR-097, RDR-101.

## In scope

O caminho completo descrito no objetivo: entrada pública, comportamento de domínio, persistência/transação quando aplicável, saída consultável e testes de comportamento. UI apenas quando faz parte do objetivo; outros tickets oferecem demonstração pela API/CLI ou pelo artefato de investigação. Não criar telas vazias para simular uma fatia vertical.

## Out of scope

Implementação de outros tickets, novos recursos V1.1, mudança silenciosa de arquitetura e promoção de qualquer capability para AUTO. Nenhuma autorização implícita de login, extração de sessão, endpoint privado ou envio comercial.

## Blocked by

- [TKT-20](https://github.com/dsanti-lunara/radar-de-ofertas/issues/20) — Gerar link Fake com TrackingContext auditável
- [TKT-37](https://github.com/dsanti-lunara/radar-de-ofertas/issues/37) — Validar Shopee Affiliate API da conta (SPIKE-02)

## External gates / prerequisites

Contratos/Fake offline permitidos; runtime/API autenticada de link exige entitlement e SPIKE-02, Opportunity/contexto e limites validados. Discovery API #47 não é obrigatório.

ready-for-agent significa escopo especificado, não gates cumpridos. Só trabalhar fronteira autorizada/desbloqueada; nenhum novo side effect ou AUTO autorizado por esta revisão.

## Contracts

Shopee tem três superfícies: API oficial para operações recorrentes documentadas; `affiliate.shopee.com.br` manual/diagnóstico; `shopee.com.br` captura pública assistida candidata. Proteção/indisponibilidade não autoriza alternar para browser como contorno. Sem geração operacional recorrente de links por extensão no portal.

Documentação Brasil confirmou POST GraphQL `https://open-api.affiliate.shopee.com.br/graphql`, `productOfferV2`, `shopeeOfferV2`, `shopOfferV2` e mutation `generateShortLink(originUrl, subIds)`; feeds/relatórios também foram documentados, mas sua existência não amplia analytics V1. AppID/Secret só no SecretsProvider. Assinar SHA256 de AppID + Timestamp + bytes JSON exatos + Secret, hex minúsculo; tolerância documentada de 10 minutos. Inconsistência Credential/Credentials precisa de validação oficial no SPIKE-02 antes de runtime.

HTTP 200 com errors/data parcial não é sucesso do contrato. Int64 cruza TypeScript/JSON sem perda (IDs como strings decimais); dinheiro/comissão usa Decimal a partir de strings. priceMin/Max é range de oferta, não preço de SKU escolhido/checkout. Paginação depende da operação; respeitar orçamento/backoff e classificar 10020 por reason sanitizado, 10030 como rate limit e 10035 como entitlement. Acesso da conta/API live permanece pendente; documentação não equivale a API_SUPPORTED nem ausência de acesso a NOT_SUPPORTED global.

Sub IDs preservam até cinco posições (brand, channel, content_type, category, referência interna), sem PII. Mapear/serializar valores explicitamente; comprimento por campo não foi comprovado e é gate para runtime correspondente. Retorno shortLink é literal, não sintetizado/editado. Mutation com resultado desconhecido não recebe retry cego; Core mantém idempotência/auditoria/reconciliação sem presumir chave de idempotência remota.

Captura pública registra source_url/observed_at, shop/item, campanha/categoria e contexto de variante/preço. Descobrir campanha vigente: IDs históricos de promoção não são configuração fixa. Loading difere de EMPTY; CHALLENGE após DOM inicial suspende parte afetada, exige intervenção humana e revalidação na retomada. E-SP-PUB-08 confirmou preço somente da opção 12L; opção preta/checkout/recorrência não foram validados. Cache/TTL/dedupe reduzem consultas, mas sem dado atual verificável por fonte permitida a revalidação pré-envio bloqueia publicação.

approved Opportunity + official API tracking → AffiliateLink, capability indisponível ou resultado desconhecido, classificados por evidência.

Manter schema_version nos contratos externos, Correlation ID e erros estruturados retryable quando aplicável. Inputs e estados concretos seguem SDDs; acréscimos de schema/enum/API/migration devem ser documentados antes de alterar interfaces. Não acoplar Domain a FastAPI/SQLAlchemy/Chrome. Persistência relevante deve ser observável pela fronteira pública, não pelo teste de chamadas internas.

## Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. API oficial first; browser/IA/conteúdo externo não confiáveis. Side effects falham fechados, são idempotentes e respeitam autorização/compliance/kill switches. Marketplace content é dado; IA nunca calcula scores, decide compliance ou cria links.

Não automatizar senha/login/2FA/CAPTCHA nem extrair cookies/tokens. Não enviar secrets a logs, Git, banco comum, fixtures, screenshots ou prompts. Testes live são opt-in e separados da suite padrão. Este ticket não autoriza publicação em destino real; autorização específica e sandbox, quando aplicável, devem constar em evidência antes de execução.

## Acceptance criteria

- [ ] generateShortLink preserva originUrl e até cinco posições de subIds; retorno literal, Opportunity e produto/tracking validados.
- [ ] Signature/precision/errors/entitlement/limites por campo cobertos; mutation unknown tem auditoria/idempotência/reconciliação sem retry cego.
- [ ] Link não exige discovery #47 se contexto veio de #49; runtime continua bloqueado por #37; nenhuma geração browser de fallback.

- [ ] Capacidade link/Sub IDs e limites vêm do report da conta.
- [ ] brand/channel/content/category/internal ref não incluem PII.
- [ ] Produto/link/redirect e oportunidade aprovados são validados.
- [ ] Falha de API não produz link inventado nem endpoint privado.
- [ ] API indisponível tem causa explícita; não acionar fallback browser de geração. Link manual validado pertence a #50 e mantém o mesmo contrato de tracking.
- [ ] Comportamento demonstrado pela fronteira pública com evidência rastreável; nenhum teste/guardrail enfraquecido.
- [ ] Docs/contratos afetados e matriz QA atualizados; limitações e blockers remanescentes explícitos.

## Tests required

Casos RECON-SP aplicáveis: 200+errors/partial data; Int64/Decimal/range de oferta; assinatura de bytes exatos; paginação específica; 10020/10030/10035; mutation unknown; loading/EMPTY, campanha atual, variante/contexto divergentes e CHALLENGE após render. Fake/fixture primeiro; API live e SIDE_EFFECT em gates próprios.

1. Caso verificável: Capacidade link/Sub IDs e limites vêm do report da conta.
2. Caso verificável: brand/channel/content/category/internal ref não incluem PII.
3. Caso verificável: Produto/link/redirect e oportunidade aprovados são validados.
4. Caso verificável: Falha de API não produz link inventado nem endpoint privado.
5. Caso verificável: API indisponível tem causa explícita; não acionar fallback browser de geração. Link manual validado pertence a #50 e mantém o mesmo contrato de tracking.

Usar Unit/Contract/Integration relevantes; SQLite temporário real para constraints/transações/migrations, relógio controlado para tempo e Fake Providers/Publishers para efeitos externos. Fixtures sanitizadas são obrigatórias para selectors; reconnaissance produz artefatos e fixture tests, SAFE_LIVE read-only opt-in em gate separado. Testes de side effect somente no ambiente explicitamente autorizado. Critérios de homologação/soak exigem evidência real controlada e não são satisfeitos por mocks. Cada critério crítico deve mapear Requirement → Test → Acceptance → Evidence.

## Observability

Resultado/estado e erro acionável do objetivo, Correlation ID, audit events e health relevantes sem dados sensíveis. Quando intervenção for necessária, HumanAction deve explicar impacto e próximos passos; se ticket inicial ainda não possuir o módulo, expor estado/erro e integrar a ação no ticket dependente, sem inventar envio automático. Reconnaissance registra mapas/estados/evidência sanitizada, sem fingir telemetry de runtime inexistente.

## Documentation to update

Sincronizar SDD-04/07/09, QA, Decision Log RECON-001..005, specs aplicáveis e corpo/manifesto local. Referências documentais não substituem os AC e contratos concretos deste corpo. Preservar cobertura canônica RDR e histórico de evidência.

SDDs e contratos citados quando o comportamento for refinado, QA traceability com IDs reais de testes, Error Catalog/runbooks quando aplicável e rastreabilidade RDR/ticket/GitHub. Referências de origem não substituem o corpo integral desta issue; specs ainda locais devem ser disponibilizadas no tracker/checkout sem assumir parent GitHub inexistente.

## Completion report

Revisão documental em 2026-10-03: escopo/contratos/AC/testes/gates atualizados; issue permanece aberta. 14 checks offline do recon passaram, sem testes de produto/live ou migrations. Evidência de conclusão técnica ainda deverá ser registrada pela implementação; não marcar todos os AC como cumpridos por esta revisão.

Arquivos alterados; testes executados/resultados; testes não executados/motivo; limitações; mudanças de contrato; migrations/config changes; riscos restantes; evidência e critérios verificados na issue. Concluir somente o escopo autorizado, sem iniciar ticket seguinte automaticamente.

