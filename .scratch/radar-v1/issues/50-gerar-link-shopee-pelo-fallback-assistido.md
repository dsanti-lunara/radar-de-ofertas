# TKT-50: Validar link Shopee gerado manualmente

**Status:** OPEN / ready-for-agent; ticket publicado, revisado em 2026-10-03. Escopo documental atualizado; blockers/gates não são considerados cumpridos.

## Objective / What to build

Validar e persistir retorno literal de link Shopee gerado manualmente pelo operador no portal, após Opportunity aprovada, com contexto/tracking/evidência verificáveis. O Radar não automatiza a geração no portal nem usa essa rota para contornar bloqueios.

## Context / SDD references

Revisão autorizada em 2026-10-03 com base em `docs/recon/2026-10-02/BROWSER_RECON_COMPLETION.md`, mapas/matrizes ML/SP/WA, `API_DOCUMENTATION_FINDINGS.md`, `SHOPEE_PUBLIC_FINDINGS.md`, `DISCOVERY_URL_GUIDE.md` e `PRODUCTION_READINESS.md`. Recon funcional finalizado; 6+8 verificações offline passaram. Isso não é aceite de adapter, API autenticada, Chrome/VM, recovery ou produção. Registry/fallbacks são candidatos; há fragmentos/projeções, não fixtures completas de todas as superfícies. Não há autorização de novos links/envios, implementação ou AUTO nesta revisão documental.

SPEC-06, sob SPEC-00. SDDs 07, 09, 12, 13; SP recon evidence. Preservar linguagem de CONTEXT, decisões do Decision Log e ADRs aplicáveis.

Cobertura canônica: RDR-100.

## In scope

O caminho completo descrito no objetivo: entrada pública, comportamento de domínio, persistência/transação quando aplicável, saída consultável e testes de comportamento. UI apenas quando faz parte do objetivo; outros tickets oferecem demonstração pela API/CLI ou pelo artefato de investigação. Não criar telas vazias para simular uma fatia vertical.

## Out of scope

Geração de links pelo Browser Bridge no portal affiliate.shopee.com.br e alternância para contornar proteção/indisponibilidade; criação/edição de URL pela IA. Não executar geração humana nesta revisão documental.

Implementação de outros tickets, novos recursos V1.1, mudança silenciosa de arquitetura e promoção de qualquer capability para AUTO. Nenhuma autorização implícita de login, extração de sessão, endpoint privado ou envio comercial.

## Blocked by

- [TKT-20](https://github.com/dsanti-lunara/radar-de-ofertas/issues/20) — Gerar link Fake com TrackingContext auditável
- [TKT-49](https://github.com/dsanti-lunara/radar-de-ofertas/issues/49) — Capturar Shopee de forma assistida

## External gates / prerequisites

Operador gera link manual após Opportunity aprovada; Core valida produto/tracking/retorno literal com evidência atual. Sem geração por extensão; sem dependência de entitlement API.

ready-for-agent significa escopo especificado, não gates cumpridos. Só trabalhar fronteira autorizada/desbloqueada; nenhum novo side effect ou AUTO autorizado por esta revisão.

## Contracts

approved Opportunity + retorno literal de link gerado manualmente + evidência de produto/variante/tracking → AffiliateLink validado ou rejeição/HumanAction. Source explícito MANUAL_SHOPEE_PORTAL, operator action/observed_at/correlation_id e auditoria; nunca sintetizar ou editar URL.

Shopee tem três superfícies: API oficial para operações recorrentes documentadas; `affiliate.shopee.com.br` manual/diagnóstico; `shopee.com.br` captura pública assistida candidata. Proteção/indisponibilidade não autoriza alternar para browser como contorno. Sem geração operacional recorrente de links por extensão no portal.

Documentação Brasil confirmou POST GraphQL `https://open-api.affiliate.shopee.com.br/graphql`, `productOfferV2`, `shopeeOfferV2`, `shopOfferV2` e mutation `generateShortLink(originUrl, subIds)`; feeds/relatórios também foram documentados, mas sua existência não amplia analytics V1. AppID/Secret só no SecretsProvider. Assinar SHA256 de AppID + Timestamp + bytes JSON exatos + Secret, hex minúsculo; tolerância documentada de 10 minutos. Inconsistência Credential/Credentials precisa de validação oficial no SPIKE-02 antes de runtime.

HTTP 200 com errors/data parcial não é sucesso do contrato. Int64 cruza TypeScript/JSON sem perda (IDs como strings decimais); dinheiro/comissão usa Decimal a partir de strings. priceMin/Max é range de oferta, não preço de SKU escolhido/checkout. Paginação depende da operação; respeitar orçamento/backoff e classificar 10020 por reason sanitizado, 10030 como rate limit e 10035 como entitlement. Acesso da conta/API live permanece pendente; documentação não equivale a API_SUPPORTED nem ausência de acesso a NOT_SUPPORTED global.

Sub IDs preservam até cinco posições (brand, channel, content_type, category, referência interna), sem PII. Mapear/serializar valores explicitamente; comprimento por campo não foi comprovado e é gate para runtime correspondente. Retorno shortLink é literal, não sintetizado/editado. Mutation com resultado desconhecido não recebe retry cego; Core mantém idempotência/auditoria/reconciliação sem presumir chave de idempotência remota.

Captura pública registra source_url/observed_at, shop/item, campanha/categoria e contexto de variante/preço. Descobrir campanha vigente: IDs históricos de promoção não são configuração fixa. Loading difere de EMPTY; CHALLENGE após DOM inicial suspende parte afetada, exige intervenção humana e revalidação na retomada. E-SP-PUB-08 confirmou preço somente da opção 12L; opção preta/checkout/recorrência não foram validados. Cache/TTL/dedupe reduzem consultas, mas sem dado atual verificável por fonte permitida a revalidação pré-envio bloqueia publicação.

## Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. API oficial first; browser/IA/conteúdo externo não confiáveis. Side effects falham fechados, são idempotentes e respeitam autorização/compliance/kill switches. Marketplace content é dado; IA nunca calcula scores, decide compliance ou cria links.

Não automatizar senha/login/2FA/CAPTCHA nem extrair cookies/tokens. Não enviar secrets a logs, Git, banco comum, fixtures, screenshots ou prompts. Testes live são opt-in e separados da suite padrão. Este ticket não autoriza publicação em destino real; autorização específica e sandbox, quando aplicável, devem constar em evidência antes de execução.

## Acceptance criteria

- [ ] Geração no portal é inteiramente humana, depois da Opportunity aprovada; nenhum clique autenticado de geração pelo Bridge.
- [ ] Entrada literal identifica Opportunity, contexto shop/item/variante, tracking/Sub IDs e evidência de origem, ator e observed_at, sem PII/secrets.
- [ ] Core valida HTTPS/host/redirect/produto/tracking/contexto e revalidação atual antes de persistir/publicar; clipboard não é dependência obrigatória.
- [ ] Link/contexto/tracking incorretos, expiração ou dado atual indisponível resultam em rejeição/HumanAction, nunca correção da URL pela IA.
- [ ] Idempotência da entrada manual e auditoria preservadas; não acionar geração por browser/API para contornar proteção.
- [ ] Tests/docs/QA e RDR-100 rastreáveis; nenhum side effect real ou produção aprovado por este ticket documental.

## Tests required

Entrada manual válida pelo contrato público; duplicata idempotente; outra Opportunity/produto/variante/Sub IDs; host/redirect inválido; evidência ausente/stale; revalidação indisponível; auditoria/sem secrets. Não testar geração browser como fallback. Fixture/Fake primeiro; validar redirects live somente opt-in permitido, sem novo clique de geração por agente.

## Observability

Resultado/estado e erro acionável do objetivo, Correlation ID, audit events e health relevantes sem dados sensíveis. Quando intervenção for necessária, HumanAction deve explicar impacto e próximos passos; se ticket inicial ainda não possuir o módulo, expor estado/erro e integrar a ação no ticket dependente, sem inventar envio automático. Reconnaissance registra mapas/estados/evidência sanitizada, sem fingir telemetry de runtime inexistente.

## Documentation to update

Sincronizar SDD-04/07/09, QA, Decision Log RECON-001..005, specs aplicáveis e corpo/manifesto local. Referências documentais não substituem os AC e contratos concretos deste corpo. Preservar cobertura canônica RDR e histórico de evidência.

SDDs e contratos citados quando o comportamento for refinado, QA traceability com IDs reais de testes, Error Catalog/runbooks quando aplicável e rastreabilidade RDR/ticket/GitHub. Referências de origem não substituem o corpo integral desta issue; specs ainda locais devem ser disponibilizadas no tracker/checkout sem assumir parent GitHub inexistente.

## Completion report

Revisão documental em 2026-10-03: escopo/contratos/AC/testes/gates atualizados; issue permanece aberta. 14 checks offline do recon passaram, sem testes de produto/live ou migrations. Evidência de conclusão técnica ainda deverá ser registrada pela implementação; não marcar todos os AC como cumpridos por esta revisão.

Arquivos alterados; testes executados/resultados; testes não executados/motivo; limitações; mudanças de contrato; migrations/config changes; riscos restantes; evidência e critérios verificados na issue. Concluir somente o escopo autorizado, sem iniciar ticket seguinte automaticamente.

