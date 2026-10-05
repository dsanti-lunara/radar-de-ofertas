# 07, Radar Browser Bridge

## Definição

O Browser Bridge é um executor autenticado de operações que dependem da sessão do navegador. Não é crawler genérico e não contém lógica de scoring/publicação.

## Princípio API first

```text
Official API disponível e suficiente
→ usar API

API insuficiente
→ Browser Bridge, se capability permitida

Operação não validada
→ manual/assisted
```

## Chrome

- Manifest V3
- TypeScript
- perfil dedicado
- permissões mínimas
- nenhum `chrome.debugger`
- nenhuma interceptação ampla de tráfego
- nenhum `EXECUTE_JS` remoto

## Arquitetura

```text
Popup
 ↓
Service Worker
 ↓
Content Scripts
 ├── Mercado Livre
 ├── Shopee
 └── WhatsApp
```

Service worker:
- polling de jobs;
- persistência de job state em `chrome.storage`;
- heartbeat;
- orchestration;
- pairing.

Content script:
- detecta página;
- extrai informação necessária;
- executa capability explicitamente permitida;
- nunca interpreta texto do site como comando.

## Modos

- MANUAL
- ASSISTED
- WORKER

Cada capability é promovida separadamente.

## Capabilities iniciais

- DETECT_PAGE
- CAPTURE_CURRENT_PRODUCT
- CAPTURE_VISIBLE_AFFILIATE_OFFER
- GENERATE_ML_AFFILIATE_LINK
- VALIDATE_AFFILIATE_LINK
- CHECK_MARKETPLACE_SESSION
- PUBLISH_WHATSAPP_GROUP
- RESUME_JOB

## Mercado Livre

TrackingContext interno é separado da etiqueta externa ML. `tracking_label` aceita somente `[a-z0-9]{1,30}`; mapear por configuração explícita e auditável, com unicidade e validação de associação. Não transformar silenciosamente maiúsculas, separadores ou truncar para caber; criação/configuração de etiqueta continua humana. `rbtgoffer` é exemplo sintático, não etiqueta já existente/autorizada.

Gerar link/ID ML adiciona o produto a Minhas recomendações e é side effect: somente após Opportunity aprovada, autorização/gates e auditoria. Correlacionar input, etiqueta, tentativa e resultado; erro atual invalida seção de resultado anterior ainda visível. Preservar link literal retornado. Aceitar formato social legítimo somente quando produto destacado, catálogo/anúncio e contexto esperado coincidirem; outra recomendação no perfil não comprova o link. Short redirect, variante/vendedor, ausência da barra e recuperação permanecem aceites distintos.

Superfícies a investigar:
- Central de Afiliados;
- Gerador de Links;
- etiquetas;
- resultado de link;
- Barra de Afiliados;
- produto.

Preferência:
1. Gerador de Links;
2. Barra como fallback, se validado.

Validar que a URL é de produto elegível antes de gerar link.

## Shopee

API oficial tem prioridade quando capability estiver disponível na conta.

Shopee tem três superfícies: API oficial para operações recorrentes documentadas; `affiliate.shopee.com.br` manual/diagnóstico; `shopee.com.br` captura pública assistida candidata. Proteção/indisponibilidade não autoriza alternar para browser como contorno. Sem geração operacional recorrente de links por extensão no portal.

Documentação Brasil confirmou POST GraphQL `https://open-api.affiliate.shopee.com.br/graphql`, `productOfferV2`, `shopeeOfferV2`, `shopOfferV2` e mutation `generateShortLink(originUrl, subIds)`; feeds/relatórios também foram documentados, mas sua existência não amplia analytics V1. AppID/Secret só no SecretsProvider. Assinar SHA256 de AppID + Timestamp + bytes JSON exatos + Secret, hex minúsculo; tolerância documentada de 10 minutos. Inconsistência Credential/Credentials precisa de validação oficial no SPIKE-02 antes de runtime.

HTTP 200 com errors/data parcial não é sucesso do contrato. Int64 cruza TypeScript/JSON sem perda (IDs como strings decimais); dinheiro/comissão usa Decimal a partir de strings. priceMin/Max é range de oferta, não preço de SKU escolhido/checkout. Paginação depende da operação; respeitar orçamento/backoff e classificar 10020 por reason sanitizado, 10030 como rate limit e 10035 como entitlement. Acesso da conta/API live permanece pendente; documentação não equivale a API_SUPPORTED nem ausência de acesso a NOT_SUPPORTED global.

Sub IDs preservam até cinco posições (brand, channel, content_type, category, referência interna), sem PII. Mapear/serializar valores explicitamente; comprimento por campo não foi comprovado e é gate para runtime correspondente. Retorno shortLink é literal, não sintetizado/editado. Mutation com resultado desconhecido não recebe retry cego; Core mantém idempotência/auditoria/reconciliação sem presumir chave de idempotência remota.

Captura pública registra source_url/observed_at, shop/item, campanha/categoria e contexto de variante/preço. Descobrir campanha vigente: IDs históricos de promoção não são configuração fixa. Loading difere de EMPTY; CHALLENGE após DOM inicial suspende parte afetada, exige intervenção humana e revalidação na retomada. E-SP-PUB-08 confirmou preço somente da opção 12L; opção preta/checkout/recorrência não foram validados. Cache/TTL/dedupe reduzem consultas, mas sem dado atual verificável por fonte permitida a revalidação pré-envio bloqueia publicação.

RDR-100 cobre validação de link manual; GENERATE_SHOPEE_AFFILIATE_LINK não é capability operacional do Bridge V1. Não implementar alias que automatize o portal. Sem crawling massivo.

## WhatsApp

WhatsApp V1 usa grupos explicitamente cadastrados (`destination_type=GROUP`), pela capability `PUBLISH_WHATSAPP_GROUP`; `Channel.WHATSAPP` continua a plataforma. Channels não são a capability V1 deste fluxo. Nome de grupo e message-id não comprovam identidade persistente de destino.

Cada destino mantém identidade interna, marca, sandbox/produção e vínculo verificado ao grupo. O vínculo registra método/evidência, versão e revisão humana; somente pode habilitar envio após prova de identificação e reverificação segura. ID externo só é persistido se obtido por superfície permitida e validado; nunca inferido de storage/cookies/tokens. Sem essa prova, manter envio bloqueado e HumanAction/CAPABILITY_CONFLICT apenas para WA. Mudança de contexto, vínculo inválido ou grupo homônimo bloqueia antes do clique.

Serializer canônico define blocos e separadores de linha, aplica renderer determinístico e compara hash do conteúdo efetivamente preparado com o aprovado. Não usar `innerText`/`textContent` sem normalização especificada. Preview não autoriza envio. Preflight revalida destino, marca, conteúdo, oferta, compliance, nonce e aprovação da Publication imediatamente antes de um único Send.

`Enviada`/bubble/message marker são evidência de envio observado, não promessa de entrega/leitura. Receipt registra destino interno/vínculo, publication/revision, hash, correlation_id, observed_at e marcador externo quando disponível. Ausência de confirmação suficiente, timeout ou crash na janela de envio gera resultado desconhecido persistido, publicação suspensa e HumanAction, sem reenvio automático. Dedupe não depende de bubble: mensagens temporárias/reload/restore não apagam a proteção persistente (GRILL-002/003).

Usa o mesmo Chrome/profile.

Somente destinos cadastrados:
- Radar Beauty Group
- Casa em Ordem Group
- grupo sandbox separado para testes

Antes de enviar:
- current destination == expected destination;
- rendered message hash == expected hash;
- brand/destination/tracking compatíveis.

Começa em ASSISTED.

## Auth

A extensão não:
- preenche login;
- lê password;
- resolve 2FA;
- resolve CAPTCHA;
- extrai cookies/tokens.

Estados:
- READY
- AUTH_REQUIRED
- CHALLENGE
- DOM_CHANGED
- UNSUPPORTED
- ERROR

## Job persistence

MV3 pode suspender service worker. Nunca depender apenas de memória.

Persistir:
- job_id;
- current_step;
- marketplace;
- started_at;
- state.

## Polling

Primeira versão usa polling simples do Core e sincronização manual. Sem WebSocket obrigatório.

## Selector strategy

Ordem:
1. semântica;
2. atributos estáveis;
3. role/label/text;
4. estrutura relativa;
5. CSS específico.

Evitar coordenadas e `nth-child`.

Cada adapter terá selector registry versionado:
- primary;
- fallbacks.

Se nenhum seletor confiável ou houver ambiguidade:
`DOM_CHANGED`, fail closed.

## Security

- allowlist de hosts;
- URL policy;
- redirect guard;
- pairing secret;
- nonce/timestamp;
- anti-replay;
- command allowlist;
- schema validation;
- page/product/destination context verification.

## Diagnostics

Falha de DOM gera snapshot sanitizado:
- page type;
- URL sanitizada;
- adapter version;
- expected/found elements;
- timestamp;
- screenshot opcional.

Retenção curta, sem backup padrão.

## Gate

Nenhum adapter real deve ser implementado antes de `BROWSER_RECONNAISSANCE.md`.
