# Avaliação consolidada — ML, Shopee API/browser e WhatsApp grupo

**Status da investigação: FINALIZADA**, por autorização do operador. Sessão de 2026-10-02 America/Sao_Paulo, atravessando 2026-10-03 UTC.

Entrega consolidada para revisão/criação de issues: evidências observadas, relatos do operador identificados, mapas/matrizes, seletores candidatos, fixtures sanitizadas, documentação API, URLs de discovery e gaps registrados. As 14 verificações offline do pacote passaram. Limitações e experimentos não executados permanecem documentados; não representam investigação ainda em andamento.

**Status de produção: NÃO APROVADA.** API autenticada, implementação/aceite dos adapters, recuperação/idempotência e homologação Chrome/VM/soak pertencem às próximas etapas, conforme [gates de produção](PRODUCTION_READINESS.md). Este fechamento não fecha issues automaticamente, não libera novos envios e não promove AUTO.

Data: 2026-10-02, America/Sao_Paulo (sessão atravessa 2026-10-03 UTC). Continuação do [relatório inicial](BROWSER_RECON_REPORT.md), com autorizações posteriores do operador. Este é o **documento vigente para consumo na revisão/criação de issues**. As observações E-* anteriores continuam evidência histórica; esta versão supersede seus estados pendentes quando indicado.

## Resultado

Entradas e percursos futuros: [guia de URLs para discovery](DISCOVERY_URL_GUIDE.md), com separação de hosts, documentação/API, ferramentas manuais e promoções temporárias.

Complementos posteriores: [site público/ofertas relâmpago](SHOPEE_PUBLIC_FINDINGS.md) e [checklist de aprovação para produção](PRODUCTION_READINESS.md). Home/lista/filtro de beleza foram investigados sem challenge visível nesta visita; supersede a pendência de investigação inicial dessa superfície citada abaixo. Estabilidade recorrente e aceite de adapter permanecem pendentes.

Atualização crítica: filtro Casa e Cozinha confirmado (categoryId=20); detalhe público da lixeira exibiu **Verifique para continuar** depois do carregamento inicial, E-SP-PUB-07. Proteção não é exclusiva do portal afiliado. Não aprovar revalidação automática pública com base no funcionamento da lista; parada/HumanAction obrigatórias, sem bypass. Guia contém URLs públicas para ambos os filtros.

Após resolução manual, preço card/detalhe coincidiu em R$63,70 com opção 12L selecionada; troca de opção preta teve timeout e não foi confirmada, E-SP-PUB-08/09. Sem prova de que extensão causa proteção ou de acesso garantido sem CAPTCHA. Recomendação: API para operações documentadas, cache/TTL/dedupe e uso assistido limitado; dados sem revalidação atual bloqueiam envio.

Geração ML pelo gerador e pela barra, formatos curto/completo, cópia ML, destino público ML, conversão Shopee com tracking e fluxo padrão/avançado de oferta foram investigados. Cinco Sub IDs retornaram no redirecionamento. Documentação oficial dos oito métodos API foi lida. Uma mensagem técnica foi enviada uma única vez ao grupo sandbox após autorização explícita, com evidência pós-envio `Enviada`.

**Reconnaissance funcional avançou; não é aceite de adapter nem homologação de produção.** API autenticada, auth expirada, recuperação persistente/MV3/reboot/rede, guards de adapter e Chrome/VM continuam gates de implementação/homologação. Não provocar logout, outage ou publicação comercial só para completar o checklist de investigação.

A decisão do usuário é **WhatsApp em grupo, não Channels**. Isso altera o escopo descrito nos SDDs atuais. A investigação do grupo foi autorizada; a arquitetura/contratos normativos não foram reescritos nesta task. Revisar docs e issues antes de implementar publisher de grupo. Sem AUTO.

## Shopee: separar portal de afiliados e site público

**Portal `affiliate.shopee.com.br`: evitar extensão como fluxo operacional recorrente.** Além dos estados de proteção observados em E-SP-14/E-SP-20, o operador relatou ter resolvido CAPTCHA manualmente cerca de três vezes durante a investigação. Esse número é `USER_REPORTED`, não uma contagem instrumental do agente. A geração de links funcionou tecnicamente, mas não demonstra confiabilidade operacional. Priorizar a API oficial para ofertas afiliadas, links, tracking e relatórios; deixar o portal para consulta/configuração manual. Não adotar retry automático ou navegador como fallback para contornar proteção da API/portal.

**Site público Shopee: avaliação separada.** O operador relatou que páginas de produtos, ofertas relâmpago e outras áreas do site normal parecem utilizáveis e sem antibot durante seu uso. Registrar como `USER_REPORTED`, não como ausência comprovada de proteção. Os destinos públicos dos links foram abertos nesta sessão, mas não houve investigação completa da superfície de ofertas relâmpago, estabilidade entre sessões ou limites de captura. Uma futura investigação de captura assistida visível no site público pode permanecer no escopo, com fixtures, identidade de produto e parada diante de challenge; sem crawling massivo ou endpoints privados. Os problemas do portal não provam inviabilidade do site público, e o relato do site público não libera automação recorrente.

Impacto: dividir RDR-098..102 por host/finalidade antes de implementar. Separar diagnóstico/manual do portal, provider API oficial e eventual captura pública assistida. Não aceitar um único estado READY como aprovação de todas as superfícies Shopee.

## Autorização e efeitos executados

O usuário autorizou gerar os links após ser informado do efeito ML em Minhas recomendações. Posteriormente declarou “Vai ser em grupo mesmo, nao vamos usar o Channels” e autorizou “Pode enviar” para a mensagem concreta preparada em `CASA EM ORDEM | PROMOS #1`.

- ML: produto público Principia, catálogo MLB43187757/anúncio MLB5178681714; geração com etiqueta já em uso, sem criar ou trocar etiqueta/configuração. Link repetido pela barra para validar fallback; mesmo valor curto observado, sem prova de idempotência de todos os efeitos remotos.
- Shopee: produto público Eudora, shop_id 1487590844/item_id 22193956904; links padrão e de teste. Tracking sem PII: `recon20261002`, `sandbox`, `technical`, `beauty`, `test01`.
- WhatsApp: um envio técnico, sem link comercial, sem mídia, sem compra. Grupo aberto pelo operador e com um membro na observação. Mensagens temporárias em sete dias estavam ativas; não alteradas.
- Abrir links gerados para validar destino pode registrar cliques nas métricas de afiliado. Esses cliques de QA não são tráfego comercial; não usar como conversão/score.
- Nenhum acesso API solicitado, secret coletado, token/cookie extraído, CAPTCHA resolvido pelo agente ou endpoint privado usado. Nenhuma issue criada/editada/fechada; alterações paralelas do repo preservadas.

## Novas evidências

| ID | Ação / superfície | Resultado observado |
|---|---|---|
| E-ML-08 | Gerar produto no linkbuilder | Mensagem “O link foi gerado e copiado corretamente”; seção resultado com `Link curto`, `Link completo`, `Copiar`, `Pré-visualizar no meu perfil`; confirmação de adição a Minhas recomendações |
| E-ML-09 | Selecionar formato completo | Short em `https://meli.la/<code>`; full em `https://www.mercadolivre.com.br/social/<affiliate>` com `matt_word`, `matt_tool`, `forceInApp`, `ref` opaco. Não sintetizar/editar parâmetros. Etiqueta externa no matt_word coincidiu com seleção atual; valor privado omitido dos artefatos |
| E-ML-10 | Abrir link completo gerado | Perfil social destacou exatamente o produto esperado e link para MLB43187757, com anúncio MLB5178681714 no contexto. Landing é perfil social com outras recomendações, não produto direto. Não validar affiliate link apenas por path de produto |
| E-ML-11 | Compartilhar pela barra do produto | Dialog `Gerar link / ID de produto`; resultado curto **igual** ao do gerador, ID pesquisável do produto e texto sugerido; etiqueta em uso; testids específicos de resultado/cópia. ID P0-1 usado em múltiplos contextos; não tratá-lo como seletor universal |
| E-ML-12 | Cópia / fechamento | ML full no clipboard coincidiu após atualização; barra short coincidiu após trim de whitespace. Leituras imediatas do host chegaram stale; não confundir com falha permanente do site. Dialog fechado e barra recolhida |
| E-ML-13 | Gerar `nao-e-url` | Erro “Não foi possível gerar o link.”; aria-invalid do input não foi observado. A seção Copie/curto/completo/Copiar ainda apareceu junto ao erro. Presença da seção de resultado não prova sucesso da tentativa atual; correlacionar input/etiqueta/ação/resultado e rejeitar erro. Campo posteriormente restaurado, sem novo clique |
| E-SP-15 | Link personalizado, produto + dois Sub IDs | Resultado textarea disabled sem label, `Por favor, copie o link`, button `Copiar Link`, short `https://s.shopee.com.br/<code>` |
| E-SP-16 | Abrir short de conversão | Redirect ao produto `/product/1487590844/22193956904`, título Eudora confirmado; `utm_content=recon20261002-sandbox---`; demais identificadores/assinaturas de tracking omitidos. Roundtrip dos dois campos comprovado na URL pública; não comprova atribuição em relatório financeiro |
| E-SP-17 | Obter link no detalhe verificado | Dialog `Link de Oferta de Produto`; radios Padrão/Avançado; padrão produz short sem preencher Sub IDs; campo e Copiar inicialmente disabled/loading, depois resultado disponível |
| E-SP-18 | Modo Avançado com cinco Sub IDs | IDs `getLinkModal_sub_id1..5`; button `Adicionar ao Link` atualiza short, diferente do padrão. Redirect em `/opaanlp/1487590844/22193956904`, título Eudora confirmado, `utm_content=recon20261002-sandbox-technical-beauty-test01` |
| E-SP-19 | Clicar Copiar Link | Botão localizado/clicado e resultado continuou visível. Clipboard do host permaneceu com conteúdo anterior; **cópia Shopee não confirmada nesta sessão**. Não concluir bug do marketplace sem reprodução humana/browser de homologação. Adapter deve ler resultado DOM diretamente e não depender do clipboard |
| E-SP-20 | Retornar ao conversor para teste de URL inválida | Página “Tente Novamente Mais Tarde — A verificação falhou. Tente novamente em alguns minutos.”, button Tentar Novamente. Input não localizado porque havia proteção; nenhum valor inválido submetido. Interação Shopee interrompida e operador avisado para resolução humana; sem bypass/retry automático |
| E-SP-21 | Retomada após validação manual pelo operador | Portal custom_link READY novamente. `nao-e-url` e `https://example.com/radar-recon` preenchidos e ação Obter link clicada em cada caso; não apareceu resultado short nem erro visível/alert no DOM inspecionado. Não há prova de resposta do servidor ou rejeição formal; classificar no-result/feedback inconclusivo, com prevalidation local obrigatória. Não repetir clique em loop |
| E-API-01 | Biblioteca oficial reaberta | Operações antes interrompidas pela verificação agora acessíveis; productOfferV2, shopeeOfferV2, shopOfferV2, generateShortLink, listItemFeeds, getItemFeedData, conversionReport, validatedReport lidos. E-SP-14 permanece histórico de falha; não é bloqueio permanente da documentação |
| E-API-02 | Request and Response oficial | POST `https://open-api.affiliate.shopee.com.br/graphql`, Content-Type application/json; query obrigatório, operationName/variables opcionais (nome obrigatório com múltiplas operações); HTTP 200 pode conter errors. Detalhes em [API_DOCUMENTATION_FINDINGS.md](API_DOCUMENTATION_FINDINGS.md) |
| E-WA-01 | Grupo sandbox aberto | Header nome + Você; compositor aria-label “Digite uma mensagem para o grupo …”; sidebar Canais não selecionada; destino é grupo, não Channel. Dados de conversas pessoais não persistidos |
| E-WA-02 | Compositor multiline | contenteditable, role textbox, testid `conversation-compose-box-input`; três parágrafos DOM. innerText introduz linhas em branco entre blocos; textContent concatena sem separadores. Serializer de mensagem/hashes precisa ser explícito; não usar qualquer uma dessas strings ingenuamente |
| E-WA-03 | URL no draft | Preview example.com observado, botão Cancelar, botão Enviar único no escopo main; com compositor vazio era Mensagem de voz. Nenhum upload ou preview comercial |
| E-WA-04 | Preflight e envio autorizado | Header esperado, três blocos de texto com join newline igual ao draft esperado, um Send. Um clique Enviar. Compositor esvaziou, mensagem apareceu às 22:57 com preview e marcador DOM |
| E-WA-05 | Pós-envio | Bubble tem data-id e testid `conv-msg-<message-id>`; label `Enviada`, indicação mensagem temporária. Não houve prova de Entregue/Lida. Marcador foi observado nesta sessão; persistência após reload/reconnect não testada; valor real omitido dos artefatos |
| E-WA-06 | Identidade do destino | Header testid `conversation-header`; botão `conversation-info-header`; nenhum identificador persistente de destino exposto no header inspecionado. Nome isolado admite grupos homônimos. Não usar mensagem data-id como group_id. Gate de identidade/reconciliação ainda necessário |

## Mensagem e guardrails do sandbox

Texto aprovado e enviado uma única vez:

```text
RADAR RECON 20261002
Teste técnico no grupo sandbox.
https://example.com/radar-recon
```

Preflight de reconnaissance comparou destino e texto observados e cardinalidade antes do clique. Não é implementação do hash guard de produção. Hash SHA256 e fixture dos blocos foram calculados offline, sem IA, no pacote de validação.

Fixtures/mutações offline cobrem destino diferente, texto diferente, botão ausente/duplicado e data-id/estado pós-envio ausentes. Não abrir outro grupo nem enviar texto errado para testar bloqueio. Suite de adapter futura deve demonstrar **zero clique** em todos esses casos e HumanAction quando resultado remoto desconhecido, conforme Decision Log/ADR.

O grupo observado tem somente um membro; portanto `Enviada` não comprova entrega a outras pessoas nem estabilidade em grupo real com atividade/participantes. Reenvio automático proibido em resultado desconhecido. A mensagem temporária impede usar disponibilidade eterna do bubble como dedupe.

## Cobertura atual do roteiro

| Etapa | Investigação nesta sessão | Limite restante |
|---|---|---|
| ML-01/02 | Central, gerador, vazio, disabled e formatos pós-geração observados | Selector stability/Chrome pendentes |
| ML-03 | Produto elegível gerou; texto inválido produziu erro | `/up/`, anúncio direto, batch/mixed errors e ausência barra não exercitados |
| ML-04 | Short/full, resultado, copy e landing social observados | Short redirect próprio não testado separadamente; variante/vendedor ainda precisa de guard |
| ML-05 | Charset/30/seleção atual e associação matt_word observados | Nenhuma etiqueta criada/alterada; quota e nova seleção/persistência pendentes |
| ML-06 | Barra, dialog, ID, short igual, copy e close observados | Ausência da barra/fallback em outro produto não exercitada |
| SP-01/02 | Dashboard/card/detalhe observados | Não é crawl/checkout/revalidação de estoque/variante |
| SP-03/04/05 | Modal padrão/avançado, conversor, resultados, redirects e inputs negativos observados | Copiar Shopee não confirmado; inputs negativos sem resultado/feedback conclusivo |
| SP-06 | Cinco posições, charset e roundtrip comprovados | Limite por campo desconhecido; guardar rótulos de cada posição e não inferir do tamanho DOM |
| SP-07/08 | Listas loja/campanhas e exclusivas vazias observadas | Links de loja/campanha, adesão e regras detalhadas não executados |
| SP-09/10 | Conta sem acesso; documentação oficial de oito operações e transporte lida | API live depende de entitlement/secret provisionado pelo operador |
| WA-01 | Sessão READY observada | Auth/offline/reconnect não provocados |
| WA-02 | Grupo sandbox e header observados | Identificador persistente/homônimos ainda sem prova |
| WA-03 | Compositor/multiline/preview/send observados | Mídia, transformação final serializer/hash e selector suite futuros |
| WA-04 | Um envio autorizado, bubble, Enviada e message marker observados | Delivery/read, reload, crash/reconcile, retenção/dedupe não testados |

## Alteração de escopo — WhatsApp Groups

Decision: em mensagem desta sessão, o usuário decidiu usar grupos e não WhatsApp Channels.

Evidence: superfície aberta é grupo sandbox; compositor e pós-envio reais coletados, com autorização de um envio técnico.

Affected contracts/docs: SDD Master, Browser Bridge capability `PUBLISH_WHATSAPP_CHANNEL`, PublishingDestination, Publishing/Tracking, QA Matrix, Error Catalog, SPEC-06, roteiro WA e RDR-103..110. O texto atual proíbe grupos arbitrários; manter allowlist e destinos registrados na revisão, embora o tipo autorizado passe a ser GROUP.

Options: atualizar explicitamente destino/capability/contratos para grupos configurados; ou manter Channels, o que contradiz a direção atual do usuário. Não implementar grupo escondido atrás do nome CHANNEL.

Recommended option: revisão documental e das issues para `GROUP` com identidade validada, marca/destino/tracking, aprovação ASSISTED, hash/preview determinísticos, nonce/idempotência, reconciliação de resultado desconhecido e retenção. Nome exato é sinal auxiliar, não identidade suficiente. Novo nome de capability é proposta, não contrato aprovado automaticamente.

Tests/experiments performed: inspeção do grupo autorizado, draft/preview, preflight de leitura, um envio técnico, `Enviada`/bubble/data-id. Não existe prova de inviabilidade técnica, logo não redesenhar Core/publishing. Alteração de escopo solicitada pelo usuário, não conflito inferido de screenshot.

## Implicações concretas para as issues

| IDs locais | Revisão recomendada / AC |
|---|---|
| RDR-076 | Consumir estes dois relatórios + fixtures; separar reconnaissance funcional de aceite de adapter. Checklist cobre falhas reais (URL ML/proteção Shopee) sem prometer todos estados live |
| RDR-077 | Planejamento API **autorizado pela documentação**; não esperar entitlement para contratos/fixtures Fake. Entitlement e chamada autenticada são gate de execução, não bloqueio para planejar |
| RDR-095/096 | Contratos oficiais V2; productOfferV2 por shop/item; priceMin/Max e comissão decimal String; deprecações; não converter Int64 para Number com perda. Sem crawler browser como substituto de API |
| RDR-097 | generateShortLink é mutation, originUrl + até 5 subIds; preserve retorno literal, não sintetize affiliate_url. Idempotência/reconciliação pertencem ao Core; API não mostrou chave de idempotência |
| RDR-090..094 | ML social landing é formato legítimo; validar produto destacado/anúncio sem aceitar outro recomendado. Não clicar botão Compartilhar genérico; testids scoped; falha atual invalida seção stale. Tracking lowercase/30 precisa de decisão de contrato |
| RDR-098..102 | Dividir por superfície: portal afiliado com proteção recorrente fica manual/diagnóstico; operação recorrente de links/ofertas afiliadas via API oficial. Captura assistida no site público é candidata a investigação própria, incluindo ofertas relâmpago ainda não avaliadas. Evidência do portal preserva IDs customLink/getLinkModal, extração DOM e roundtrip de cinco posições; `/opaanlp/` exige contexto verificado |
| RDR-103..110 | Revisar de CHANNEL para GROUP após formalizar decisão; destino registrado, homônimos/identity, serializer multiline/preview/hash, única ação Enviar, Enviada/message marker, unknown result sem retry; expiração sete dias não pode romper dedupe persistente |
| Nova QA copy | Reproduzir Copiar Link Shopee manualmente/Chrome, distinguir host clipboard de falha UI; não bloquear extração de link DOM correta por dependência desnecessária de clipboard |
| Nova QA API | HTTP 200 + errors/partial data; códigos 10020 variantes/10030/10035; paginação específica por método (page vs scroll vs offset); campos MCN/budget/comissão sem misturar estimado/validado |

Ordem: formalizar Groups/tracking → contracts/Fake/fixture guards → adapters → SAFE_LIVE Chrome/VM → API live com acesso → SIDE_EFFECT sandbox controlado → homologação/recovery. Autorização deste teste não libera envios futuros/comerciais nem AUTO.

## Gates restantes, sem bloquear investigação independente

- API real: acesso/segredo futuros sob responsabilidade do operador; chamada oficial authenticated e fixture de resposta sanitizada antes de executar.
- Proteção Shopee: portal interrompido e retomado somente após validação humana; operador relatou cerca de três CAPTCHAs. Evitar extensão operacional no portal afiliado; site público requer investigação distinta. Inputs negativos sem resultado/feedback conclusivo; confirmação de copy permanece limitação objetiva.
- Identidade do grupo: resolver por superfície/API oficial permitida ou pareamento humano explícito com evidência persistente; nunca ler storage interno/cookies para inventar ID.
- Adapter: fixtures completas/schema/versioning/fallback/ambiguidade/security/recovery/idempotência ainda não implementados. Testes offline deste pacote não substituem o aceite.
- Homologação: Chrome dedicado VM, locale/DOM cross-session, rede/reboot/soak pendentes. Não ativar AUTO.

## Entrega e validação

Pacote: relatório inicial + este consolidado; API_DOCUMENTATION_FINDINGS; maps/matrices atualizados; registry/fixtures novos em `FOLLOWUP_EVIDENCE.json`; verificador offline e VALIDATION; SHOPEE_CAPABILITY_REPORT atualizado.

Testes executados e resultados serão listados em [VALIDATION.md](VALIDATION.md). Sem alteração de código de produto, migrations, runtime config ou contratos normativos. Efeitos externos autorizados detalhados acima; nenhuma mensagem comercial ou destino não autorizado. Gaps reais permanecem explicitados; não fechar automaticamente issues a partir da presença deste documento.
