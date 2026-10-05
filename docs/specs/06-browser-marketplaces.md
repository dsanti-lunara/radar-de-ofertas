# SPEC-06: Browser e marketplaces

## Problem Statement

Superfícies autenticadas e capabilities não verificadas podem causar extração incorreta, clique errado ou envio para destino inadequado.

## Solution

Entregar browser e marketplaces como parte da V1 aprovada, com contratos públicos verificáveis, caminhos de falha/recuperação auditáveis e gates das integrações externas preservados.

## User Stories

1. Como operador do Radar, quero investigar superfícies em BROWSER_RECON_MODE, para operar esta etapa de forma correta, segura e rastreável.
2. Como operador do Radar, quero confirmar capabilities oficiais da conta Shopee Brasil, para operar esta etapa de forma correta, segura e rastreável.
3. Como operador do Radar, quero registrar surface/state maps e gaps, para operar esta etapa de forma correta, segura e rastreável.
4. Como operador do Radar, quero sanitizar fixtures antes de versionar, para operar esta etapa de forma correta, segura e rastreável.
5. Como operador do Radar, quero parear a extensão ao Core com autenticação local, para operar esta etapa de forma correta, segura e rastreável.
6. Como operador do Radar, quero validar comandos versionados em allowlist, para operar esta etapa de forma correta, segura e rastreável.
7. Como operador do Radar, quero persistir jobs durante suspensão MV3, para operar esta etapa de forma correta, segura e rastreável.
8. Como operador do Radar, quero detectar auth/challenge sem automatizar login, para operar esta etapa de forma correta, segura e rastreável.
9. Como operador do Radar, quero validar host, URL, redirects e produto, para operar esta etapa de forma correta, segura e rastreável.
10. Como operador do Radar, quero usar APIs oficiais quando suficientes, para operar esta etapa de forma correta, segura e rastreável.
11. Como operador do Radar, quero gerar links ML pelas superfícies validadas, para operar esta etapa de forma correta, segura e rastreável.
12. Como operador do Radar, quero usar captura Shopee assistida quando aplicável, para operar esta etapa de forma correta, segura e rastreável.
13. Como operador do Radar, quero preservar tracking/etiquetas/Sub IDs sem PII, para operar esta etapa de forma correta, segura e rastreável.
14. Como operador do Radar, quero verificar destino e message hash WhatsApp, para operar esta etapa de forma correta, segura e rastreável.
15. Como operador do Radar, quero enviar WhatsApp em ASSISTED a destinos autorizados, para operar esta etapa de forma correta, segura e rastreável.
16. Como operador do Radar, quero falhar fechado em DOM ausente ou ambíguo, para operar esta etapa de forma correta, segura e rastreável.

## Implementation Decisions

Revisão autorizada em 2026-10-03 com base em `docs/recon/2026-10-02/BROWSER_RECON_COMPLETION.md`, mapas/matrizes ML/SP/WA, `API_DOCUMENTATION_FINDINGS.md`, `SHOPEE_PUBLIC_FINDINGS.md`, `DISCOVERY_URL_GUIDE.md` e `PRODUCTION_READINESS.md`. Recon funcional finalizado; 6+8 verificações offline passaram. Isso não é aceite de adapter, API autenticada, Chrome/VM, recovery ou produção. Registry/fallbacks são candidatos; há fragmentos/projeções, não fixtures completas de todas as superfícies. Não há autorização de novos links/envios, implementação ou AUTO nesta revisão documental.

TrackingContext interno é separado da etiqueta externa ML. `tracking_label` aceita somente `[a-z0-9]{1,30}`; mapear por configuração explícita e auditável, com unicidade e validação de associação. Não transformar silenciosamente maiúsculas, separadores ou truncar para caber; criação/configuração de etiqueta continua humana. `rbtgoffer` é exemplo sintático, não etiqueta já existente/autorizada.

Gerar link/ID ML adiciona o produto a Minhas recomendações e é side effect: somente após Opportunity aprovada, autorização/gates e auditoria. Correlacionar input, etiqueta, tentativa e resultado; erro atual invalida seção de resultado anterior ainda visível. Preservar link literal retornado. Aceitar formato social legítimo somente quando produto destacado, catálogo/anúncio e contexto esperado coincidirem; outra recomendação no perfil não comprova o link. Short redirect, variante/vendedor, ausência da barra e recuperação permanecem aceites distintos.

Shopee tem três superfícies: API oficial para operações recorrentes documentadas; `affiliate.shopee.com.br` manual/diagnóstico; `shopee.com.br` captura pública assistida candidata. Proteção/indisponibilidade não autoriza alternar para browser como contorno. Sem geração operacional recorrente de links por extensão no portal.

Documentação Brasil confirmou POST GraphQL `https://open-api.affiliate.shopee.com.br/graphql`, `productOfferV2`, `shopeeOfferV2`, `shopOfferV2` e mutation `generateShortLink(originUrl, subIds)`; feeds/relatórios também foram documentados, mas sua existência não amplia analytics V1. AppID/Secret só no SecretsProvider. Assinar SHA256 de AppID + Timestamp + bytes JSON exatos + Secret, hex minúsculo; tolerância documentada de 10 minutos. Inconsistência Credential/Credentials precisa de validação oficial no SPIKE-02 antes de runtime.

HTTP 200 com errors/data parcial não é sucesso do contrato. Int64 cruza TypeScript/JSON sem perda (IDs como strings decimais); dinheiro/comissão usa Decimal a partir de strings. priceMin/Max é range de oferta, não preço de SKU escolhido/checkout. Paginação depende da operação; respeitar orçamento/backoff e classificar 10020 por reason sanitizado, 10030 como rate limit e 10035 como entitlement. Acesso da conta/API live permanece pendente; documentação não equivale a API_SUPPORTED nem ausência de acesso a NOT_SUPPORTED global.

Sub IDs preservam até cinco posições (brand, channel, content_type, category, referência interna), sem PII. Mapear/serializar valores explicitamente; comprimento por campo não foi comprovado e é gate para runtime correspondente. Retorno shortLink é literal, não sintetizado/editado. Mutation com resultado desconhecido não recebe retry cego; Core mantém idempotência/auditoria/reconciliação sem presumir chave de idempotência remota.

Captura pública registra source_url/observed_at, shop/item, campanha/categoria e contexto de variante/preço. Descobrir campanha vigente: IDs históricos de promoção não são configuração fixa. Loading difere de EMPTY; CHALLENGE após DOM inicial suspende parte afetada, exige intervenção humana e revalidação na retomada. E-SP-PUB-08 confirmou preço somente da opção 12L; opção preta/checkout/recorrência não foram validados. Cache/TTL/dedupe reduzem consultas, mas sem dado atual verificável por fonte permitida a revalidação pré-envio bloqueia publicação.

WhatsApp V1 usa grupos explicitamente cadastrados (`destination_type=GROUP`), pela capability `PUBLISH_WHATSAPP_GROUP`; `Channel.WHATSAPP` continua a plataforma. Channels não são a capability V1 deste fluxo. Nome de grupo e message-id não comprovam identidade persistente de destino.

Cada destino mantém identidade interna, marca, sandbox/produção e vínculo verificado ao grupo. O vínculo registra método/evidência, versão e revisão humana; somente pode habilitar envio após prova de identificação e reverificação segura. ID externo só é persistido se obtido por superfície permitida e validado; nunca inferido de storage/cookies/tokens. Sem essa prova, manter envio bloqueado e HumanAction/CAPABILITY_CONFLICT apenas para WA. Mudança de contexto, vínculo inválido ou grupo homônimo bloqueia antes do clique.

Serializer canônico define blocos e separadores de linha, aplica renderer determinístico e compara hash do conteúdo efetivamente preparado com o aprovado. Não usar `innerText`/`textContent` sem normalização especificada. Preview não autoriza envio. Preflight revalida destino, marca, conteúdo, oferta, compliance, nonce e aprovação da Publication imediatamente antes de um único Send.

`Enviada`/bubble/message marker são evidência de envio observado, não promessa de entrega/leitura. Receipt registra destino interno/vínculo, publication/revision, hash, correlation_id, observed_at e marcador externo quando disponível. Ausência de confirmação suficiente, timeout ou crash na janela de envio gera resultado desconhecido persistido, publicação suspensa e HumanAction, sem reenvio automático. Dedupe não depende de bubble: mensagens temporárias/reload/restore não apagam a proteção persistente (GRILL-002/003).

- Chrome MV3 TypeScript com permissões mínimas, polling/heartbeat e persistência; Playwright somente teste/reconnaissance.
- Browser Bridge é executor, não provider completo, crawler ou motor de scoring.
- Nunca extrair cookies/tokens, automatizar login/2FA/CAPTCHA, executar JS remoto ou reproduzir endpoints privados.
- ML prioriza Gerador de Links e fallback Barra validado; Shopee em massa depende de API oficial validada para a conta.
- Seletores reais apenas após reconnaissance: candidatos/fallbacks, fixture, ambiguity, errors e SAFE_LIVE; conflito real exige CAPABILITY_CONFLICT/ARCHITECTURE_CONFLICT.
- WhatsApp somente destinos cadastrados, verificação de brand/destination/message hash antes do envio; side effects sandbox requerem autorização explícita da issue.

## Testing Decisions

- Fronteira aprovada: Contratos Browser Bridge/providers com fixtures sanitizadas; SAFE_LIVE e SIDE_EFFECT em gates separados.
- Testar comportamento externo e resultados persistidos, nunca estrutura interna ou mocks que apenas repetem implementação.
- Prior art: matriz QA e contratos SDD; ainda não há código/testes versionados. Preferir as interfaces aprovadas ao criar as primeiras seams.
- fixtures primary/fallback, ambiguity fail closed e DOM_CHANGED.
- nonce replay, host/URL/redirect/command inválidos.
- produto/destino/hash mismatch, AUTH_REQUIRED e persistência MV3.
- SAFE_LIVE opt-in após fixture e evidência suficiente.
- SIDE_EFFECT somente sandbox explicitamente autorizado.

## Out of Scope

Crawling massivo, endpoint privado, conversas pessoais, contatos arbitrários e WhatsApp AUTO.

## Further Notes

### Objective

Entregar o comportamento descrito com evidência de sucesso, falha, recuperação, auditoria, segurança e idempotência quando houver side effect.

### Context / SDD references

SDDs 04, 07, 09, 12 e 13; Browser Reconnaissance; Shopee Capability Report. Vocabulário de CONTEXT e ADRs vigentes; os SDDs e Decision Log continuam autoridade. SPEC-00 organiza a entrega, sem redefinir arquitetura.

### In scope

Histórias e decisões desta spec; rastreabilidade RDR-076..RDR-111; RDR-124..RDR-125. São IDs locais do Issue Map, não números GitHub. Não renumerar nem perder AC ao fundir itens inseparáveis.

### Dependencies

SPEC-01 e SPEC-03; SPEC-05 para publicação. Recon funcional de SPIKE-03/04 finalizado; cada adapter depende da adoção de fixtures, negativos/gaps e SAFE_LIVE próprio. SPIKE-02 bloqueia runtime API da conta, não os contratos/Fake offline nem a rota manual validada.

### Contracts

Usar entradas, saídas, estados e erros dos SDDs referenciados; schema_version e Correlation ID nos contratos aplicáveis. External providers permanecem não confiáveis. Formalizar campos/enums/migrations adicionais em cada issue antes de implementação; nenhuma lacuna autoriza inventar capability externa.

### Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. Não alterar arquitetura silenciosamente. Testes seguros por padrão; live opt-in, sandbox e autorização específica para side effect. Não publicar em destino real nesta spec. Não ignorar teste, validação, idempotência ou compliance para simplificar.

### Acceptance Criteria

- [ ] Refinamentos RECON-001..005 aplicáveis demonstrados na fronteira pública; limitations/gates explícitos, sem alias CHANNEL, ID inventado ou fallback de proteção.
- [ ] Fixtures/Fake, SAFE_LIVE, API autenticada e SIDE_EFFECT sandbox têm evidências separadas; não marcar aceites reais por testes offline do recon.

- [ ] Evidência verificável para investigar superfícies em BROWSER_RECON_MODE.
- [ ] Evidência verificável para confirmar capabilities oficiais da conta Shopee Brasil.
- [ ] Evidência verificável para registrar surface/state maps e gaps.
- [ ] Evidência verificável para sanitizar fixtures antes de versionar.
- [ ] Evidência verificável para parear a extensão ao Core com autenticação local.
- [ ] Evidência verificável para validar comandos versionados em allowlist.
- [ ] Evidência verificável para persistir jobs durante suspensão MV3.
- [ ] Evidência verificável para detectar auth/challenge sem automatizar login.
- [ ] Evidência verificável para validar host, URL, redirects e produto.
- [ ] Evidência verificável para usar APIs oficiais quando suficientes.
- [ ] Evidência verificável para gerar links ML pelas superfícies validadas.
- [ ] Evidência verificável para usar captura Shopee assistida quando aplicável.
- [ ] Evidência verificável para preservar tracking/etiquetas/Sub IDs sem PII.
- [ ] Evidência verificável para verificar destino e message hash WhatsApp.
- [ ] Evidência verificável para enviar WhatsApp em ASSISTED a destinos autorizados.
- [ ] Evidência verificável para falhar fechado em DOM ausente ou ambíguo.
- [ ] Falhas e recuperação cobertas na fronteira aprovada, com guardrails preservados.
- [ ] Docs e contratos atualizados; limitações e gates pendentes explícitos.

### Tests required

Cobrir os negativos e recuperação aplicáveis da revisão RECON-001..005 e QA Matrix: identidade/charset/precisão/contexto, resultado stale/partial/unknown e dedupe persistente; estados positivos, falha e retomada auditáveis. Runtime/live permanecem opt-in nos gates autorizados.

Unit e contract relevantes; integration com dependências locais reais quando aplicável; segurança funcional e E2E do fluxo. Live/fixtures/sandbox somente nos gates descritos, nunca por padrão.

### Observability

Estado/saúde e erros acionáveis do fluxo, Correlation ID, eventos auditáveis e HumanActions quando necessária intervenção. Sem secrets/PII desnecessária em logs ou evidências.

### Documentation to update

SDDs referenciados, contratos afetados, QA traceability, Error Catalog/runbooks quando aplicáveis e Issue Map com links de execução. Registrar novas decisões difíceis de reverter em ADR quando justificadas.

### Completion report

Arquivos, testes/resultados, testes não executados/motivos, limitações, mudanças de contrato, migrations/config changes e riscos restantes. Atualizar a issue com evidência e critérios verificados; não ativar AUTO.

