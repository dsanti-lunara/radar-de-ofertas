# 09, Publishing, Tracking and Offer Lifecycle

## Limites de autorização e recuperação

SHADOW registra avaliações e previews, sem envio comercial. Em ASSISTED, o envio exige aprovação humana explícita da publicação; a aprovação do Candidate não autoriza enviar. Toda autorização permanece sujeita à revalidação, compliance e Publishing Policy.

Implementação (TKT-17, RDR-043): o gate de autorização vive em
`POST /operations/authorize` e resolve a automation policy do slice brand ×
marketplace × channel × capability; SHADOW nunca envia (mesmo com aprovação de
publicação), ASSISTED exige `publication_approved=true` e AUTO só passa com
compliance vigente e integração operacional. `STOP_EXTERNAL_ACTIONS` bloqueia
publicação/browser/link autenticado mantendo leitura/diagnóstico/recovery. Os
publishers reais (RDR-071/RDR-108) consumirão esse gate; nenhum envio é feito
aqui. Ver `docs/08_WORKFLOW_ENGINE.md` e `docs/12_SECURITY_AND_COMPLIANCE.md`.

Se o resultado remoto de um envio for desconhecido, registrar essa condição, suspender a publicação afetada, bloquear reenvio automático e criar HumanAction de revisão. Não classificar a ausência de confirmação como falha confirmada. Concluir ou autorizar nova tentativa exige evidência suficiente; a oferta pode expirar durante a revisão. Ver `adr/0001-unknown-publication-result.md`.

## Publishers

```text
Publisher
├── TelegramPublisher
└── WhatsAppPublisher
```

Telegram usa Bot API.

WhatsApp usa Browser Bridge.

## Destinations

WhatsApp V1 usa grupos explicitamente cadastrados (`destination_type=GROUP`), pela capability `PUBLISH_WHATSAPP_GROUP`; `Channel.WHATSAPP` continua a plataforma. Channels não são a capability V1 deste fluxo. Nome de grupo e message-id não comprovam identidade persistente de destino.

Cada destino mantém identidade interna, marca, sandbox/produção e vínculo verificado ao grupo. O vínculo registra método/evidência, versão e revisão humana; somente pode habilitar envio após prova de identificação e reverificação segura. ID externo só é persistido se obtido por superfície permitida e validado; nunca inferido de storage/cookies/tokens. Sem essa prova, manter envio bloqueado e HumanAction/CAPABILITY_CONFLICT apenas para WA. Mudança de contexto, vínculo inválido ou grupo homônimo bloqueia antes do clique.

Serializer canônico define blocos e separadores de linha, aplica renderer determinístico e compara hash do conteúdo efetivamente preparado com o aprovado. Não usar `innerText`/`textContent` sem normalização especificada. Preview não autoriza envio. Preflight revalida destino, marca, conteúdo, oferta, compliance, nonce e aprovação da Publication imediatamente antes de um único Send.

`Enviada`/bubble/message marker são evidência de envio observado, não promessa de entrega/leitura. Receipt registra destino interno/vínculo, publication/revision, hash, correlation_id, observed_at e marcador externo quando disponível. Ausência de confirmação suficiente, timeout ou crash na janela de envio gera resultado desconhecido persistido, publicação suspensa e HumanAction, sem reenvio automático. Dedupe não depende de bubble: mensagens temporárias/reload/restore não apagam a proteção persistente (GRILL-002/003).

`PublishingDestination` contém:
- brand;
- platform;
- destination_type;
- external_id;
- enabled;
- automation_mode.

Destinos iniciais:
- Radar Beauty Telegram
- Casa em Ordem Telegram
- Radar Beauty WhatsApp Group
- Casa em Ordem WhatsApp Group
- sandboxes separados para testes

## Renderer

A IA entrega:
- headline;
- body;
- CTA.

Renderer adiciona deterministicamente:
- preço validado;
- affiliate URL;
- botão quando aplicável;
- disclosure;
- tracking.

IA nunca cria/edita URL.

Implementação (TKT-21, RDR-069): o renderer vive em `radar.domain.content` e lê
somente o preço sustentado pela claim `CURRENT_PRICE` (Evidence do backend) e o
`AffiliateLink.affiliate_url` **literal** já validado; `render_content` monta os
blocos determinísticos (disclosure, headline, body, preço, CTA, link) com
`renderer_version`. Nenhuma URL vinda da IA é aceita (a resposta do provider é
recusada com `RAD-AI-013`) e a URL persistida nunca é editada/sintetizada
(AUT-163/AUT-164). `generated_content` e `final_content` ficam separados com suas
versões. Ver `docs/04_DATA_CONTRACTS.md`.

## Telegram

- um bot operacional pode atender ambos os canais;
- `sendMessage`/edição por API;
- armazenar `chat_id/message_id`;
- idempotency obrigatória;
- lifecycle por revision.

## WhatsApp

- usa Browser Bridge;
- mesma VM/browser de ML/Shopee;
- destination allowlist;
- message hash verification;
- começa ASSISTED;
- AUTO somente após gate específico.

Não enviar para contatos/grupos arbitrários.

## Tracking

### Shopee

Shopee tem três superfícies: API oficial para operações recorrentes documentadas; `affiliate.shopee.com.br` manual/diagnóstico; `shopee.com.br` captura pública assistida candidata. Proteção/indisponibilidade não autoriza alternar para browser como contorno. Sem geração operacional recorrente de links por extensão no portal.

Documentação Brasil confirmou POST GraphQL `https://open-api.affiliate.shopee.com.br/graphql`, `productOfferV2`, `shopeeOfferV2`, `shopOfferV2` e mutation `generateShortLink(originUrl, subIds)`; feeds/relatórios também foram documentados, mas sua existência não amplia analytics V1. AppID/Secret só no SecretsProvider. Assinar SHA256 de AppID + Timestamp + bytes JSON exatos + Secret, hex minúsculo; tolerância documentada de 10 minutos. Inconsistência Credential/Credentials precisa de validação oficial no SPIKE-02 antes de runtime.

HTTP 200 com errors/data parcial não é sucesso do contrato. Int64 cruza TypeScript/JSON sem perda (IDs como strings decimais); dinheiro/comissão usa Decimal a partir de strings. priceMin/Max é range de oferta, não preço de SKU escolhido/checkout. Paginação depende da operação; respeitar orçamento/backoff e classificar 10020 por reason sanitizado, 10030 como rate limit e 10035 como entitlement. Acesso da conta/API live permanece pendente; documentação não equivale a API_SUPPORTED nem ausência de acesso a NOT_SUPPORTED global.

Sub IDs preservam até cinco posições (brand, channel, content_type, category, referência interna), sem PII. Mapear/serializar valores explicitamente; comprimento por campo não foi comprovado e é gate para runtime correspondente. Retorno shortLink é literal, não sintetizado/editado. Mutation com resultado desconhecido não recebe retry cego; Core mantém idempotência/auditoria/reconciliação sem presumir chave de idempotência remota.

Captura pública registra source_url/observed_at, shop/item, campanha/categoria e contexto de variante/preço. Descobrir campanha vigente: IDs históricos de promoção não são configuração fixa. Loading difere de EMPTY; CHALLENGE após DOM inicial suspende parte afetada, exige intervenção humana e revalidação na retomada. E-SP-PUB-08 confirmou preço somente da opção 12L; opção preta/checkout/recorrência não foram validados. Cache/TTL/dedupe reduzem consultas, mas sem dado atual verificável por fonte permitida a revalidação pré-envio bloqueia publicação.

Sub IDs conceituais:
- brand
- channel
- content_type
- category
- publication/internal reference

Sem PII.

### Mercado Livre

TrackingContext interno é separado da etiqueta externa ML. `tracking_label` aceita somente `[a-z0-9]{1,30}`; mapear por configuração explícita e auditável, com unicidade e validação de associação. Não transformar silenciosamente maiúsculas, separadores ou truncar para caber; criação/configuração de etiqueta continua humana. `rbtgoffer` é exemplo sintático, não etiqueta já existente/autorizada.

Gerar link/ID ML adiciona o produto a Minhas recomendações e é side effect: somente após Opportunity aprovada, autorização/gates e auditoria. Correlacionar input, etiqueta, tentativa e resultado; erro atual invalida seção de resultado anterior ainda visível. Preservar link literal retornado. Aceitar formato social legítimo somente quando produto destacado, catálogo/anúncio e contexto esperado coincidirem; outra recomendação no perfil não comprova o link. Short redirect, variante/vendedor, ausência da barra e recuperação permanecem aceites distintos.

Usar etiquetas conforme capacidade real validada no Recon.

Sem redirect próprio na V1.

Implementação (TKT-20, RDR-018/RDR-070): o `AffiliateLink` é entidade própria e
só é gerado para Opportunity aprovada/linkável. O `TrackingContext` interno
(``tracking_context_id``/``internal_reference``) é separado da etiqueta externa e
resolvido por mapeamento versionado/hasheado (`config/tracking-labels.json`,
opcional; baseline vazio — nenhuma etiqueta é presumida). O provider Fake é
offline/determinístico e o link resultante é `productive=false`; o `affiliate_url`
retornado é validado (host/produto/contexto) e preservado literalmente, nunca
editado pela IA (AUT-078, AUT-164). A fronteira pública é
`POST /candidates/{id}/affiliate-link` + `GET /candidates/{id}/affiliate-links` +
`GET /affiliate-links/{id}` e a geração é idempotente por Opportunity + etiqueta.
A associação real ML/landing, a geração por adapter e a transição
`LINK_PENDING`→`LINK_READY` pertencem a #45/#46 e ao Workflow Engine. O adapter
real deve passar o gate de autorização `AUTHENTICATED_LINK` (TKT-17) antes do side
effect; o link Fake é offline, não produtivo e não consulta o gate. Ver
`docs/04_DATA_CONTRACTS.md`.

## Publication states

- DRAFT
- READY
- PUBLISHING
- PUBLISHED
- UPDATED
- EXPIRED
- FAILED
- UNKNOWN (resultado de envio não confirmado; suspensa para revisão humana)
- DELETED

Implementação (TKT-23, RDR-020/RDR-072): a `Publication` é entidade própria,
separada de `ContentGeneration` e `Opportunity` (AUT-025/AUT-034), e vive em
`radar.domain.publication`. O caminho público é `POST
/opportunities/{opportunity_id}/publications` + `GET
/opportunities/{opportunity_id}/publications` + `GET /publications/{id}`. A
publicação só ocorre para uma Opportunity em `READY_TO_PUBLISH` com
`ContentGeneration` validada e **não-`STALE`** e `AffiliateLink` literal
correspondente; a revalidação (`REVALIDATION_REQUIRED`), o gate de autorização
TKT-17 (`SHADOW`/`ASSISTED`/compliance/kill switch) e a Publication Policy
(cap/burst/cooldown/quiet hours) bloqueiam **antes** do publisher. O publisher
Fake é offline e determinístico; `external_message_id` é evidência de envio
observado, não promessa de entrega/leitura. Repetir `idempotency_key` devolve a
Publication confirmada sem novo envio. O resultado desconhecido (crash após
aceitação remota) e a suspensão/HumanAction pertencem a TKT-24/ADR 0001. A
policy baseline usa apenas os limites de referência do SDD (`hard cap 12/dia/
marca`, `burst 2/15min`); cooldown e quiet hours são configuração versionada
(`config/publication-policy.json`, opcional; use
`config/publication-policy.example.json`; `RADAR_PUBLICATION_POLICY_FILE` força
um arquivo) e o baseline não inventa valores. Ver
`docs/04_DATA_CONTRACTS.md`.

Implementação (TKT-24, RDR-128, ADR 0001/GRILL-002): quando o publisher sinaliza
um envio que pode ter sido aceito sem confirmação local, a `Publication` fica
suspensa em `status=UNKNOWN` com o evento append-only `RESULT_UNKNOWN`
(destino, revisão, `content_hash` do conteúdo efetivamente preparado, Correlation
ID e `observed_at`; sem `external_message_id`) e uma `HumanAction`
(`REVIEW_PUBLICATION`, motivo `SEND_RESULT_UNKNOWN`) explica impacto e evidência
necessária. `POST /opportunities/{id}/publications` responde `RAD-PUB-006` (409)
e **nunca** reenvia automaticamente; repetir a `idempotency_key` ou tentar outra
chave da mesma Opportunity enquanto a suspensão estiver aberta também é
bloqueado. `POST /publications/{id}/resolve` exige evidência corroborante
(`MESSAGE_MARKER`, `PROVIDER_RECEIPT` ou `DESTINATION_AUDIT`); `OPERATOR_NOTE`
isolada retorna `RAD-PUB-007` (409) e não libera nova tentativa. Com evidência,
`CONFIRM_SENT` confirma o envio (`PUBLISHED`) e `CONFIRM_NOT_SENT` marca
`FAILED`; a nova tentativa mantém revalidação/guardrails e a oferta pode expirar
durante a revisão. O Fake simula o crash pós-aceitação (`crash_after_accept`); um
encerramento abrupto do processo antes de qualquer registro local depende do
publisher real persistir sua intenção de envio (RDR-071/RDR-108). Ver
`docs/04_DATA_CONTRACTS.md` e `docs/10_PERSISTENCE_AND_RECOVERY.md`.

## Revisions

Cada edição preserva revision history.

Exemplo:
- REV1 preço original;
- REV2 preço melhor;
- REV3 oferta encerrada.

Preferir editar/expirar a apagar automaticamente.

## Publication Policy

Controla:
- frequência;
- hard cap;
- burst;
- cooldown;
- diversidade;
- threshold por canal.

Cap não é meta.

Referência inicial:
- soft target Telegram 4-8 boas ofertas/dia/marca;
- hard cap inicial 12/dia/marca;
- burst inicial: no máximo 2 posts em 15 minutos.

Todos configuráveis.

WhatsApp deve ter threshold igual ou mais rigoroso que Telegram.

## Quiet Hours

Publishing pode pausar enquanto discovery continua.

Oferta aguardando janela deve revalidar antes de enviar.

## Lifecycle post-publication

Checks limitados, por exemplo:
- +30m
- +2h
- +6h

Configurável.

Tempo sozinho não prova que oferta terminou.

## Compliance

`ChannelCompliancePolicy` decide:
- affiliate_link_allowed;
- automatic_publication_allowed;
- disclosure_required;
- policy_version.

Se policy bloqueia:
- discovery/scoring/link podem continuar;
- side effect de publicação é bloqueado.

## Attribution

TrackingContext deve permitir:
`conversion report → publication → opportunity → candidate`

Quando houver volume, conversões alimentam `ConversionEvidence`.
