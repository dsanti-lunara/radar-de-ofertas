# 04, Data Contracts

Todos os contratos externos devem ter `schema_version`.

## Browser Bridge, get job

O exemplo de etiqueta abaixo é sintático; não comprova que exista na conta. A revisão documental mantém `schema_version=1.0` para contratos ainda não implementados; schemas executáveis/versionamento final pertencem aos tickets, sem compatibilidade silenciosa de CHANNEL para GROUP.

Resposta conceitual:

```json
{
  "schema_version": "1.0",
  "job_id": "job_001",
  "type": "GENERATE_ML_AFFILIATE_LINK",
  "marketplace": "MERCADO_LIVRE",
  "payload": {
    "opportunity_id": "opp_001",
    "product_url": "https://...",
    "tracking_label": "rbtgoffer",
    "timeout_seconds": 60
  },
  "created_at": "..."
}
```

## Browser Bridge, job result

Sucesso:

```json
{
  "schema_version": "1.0",
  "status": "SUCCESS",
  "result": {
    "affiliate_url": "https://...",
    "source": "ML_LINK_GENERATOR"
  },
  "observed_at": "..."
}
```

Auth required:

```json
{
  "schema_version": "1.0",
  "status": "AUTH_REQUIRED",
  "error": {
    "code": "MARKETPLACE_SESSION_EXPIRED",
    "message": "Authentication required.",
    "retryable": false
  }
}
```

DOM failure:

```json
{
  "schema_version": "1.0",
  "status": "FAILED",
  "error": {
    "code": "AFFILIATE_UI_NOT_FOUND",
    "retryable": false
  }
}
```

## Manual capture

```json
{
  "schema_version": "1.0",
  "marketplace": "MERCADO_LIVRE",
  "source": "BROWSER_EXTENSION",
  "product": {
    "external_id": "MLB123",
    "title": "Produto",
    "url": "https://..."
  },
  "offer": {
    "current_price": "79.90",
    "original_price": "109.90",
    "sales_count": 2300,
    "seller": {"name": "Loja"}
  },
  "captured_at": "..."
}
```

Backend normaliza valores monetários. Extensão não executa regras de negócio.

### Manual capture, implementação (TKT-03)

Implementado em `POST /captures/manual` (`schema_version=1.0`) sobre a fronteira
pública. O contrato é estrito (`extra=forbid`): campos desconhecidos e nomes
sensíveis (`password`, `token`, `secret`, `cookie`, `authorization`, ...) são
recusados antes de qualquer escrita. Campos de texto são sanitizados (controle/
quebra de linha) e valores monetários exigem string decimal; `float` binário é
recusado. A URL deve ser `http(s)` absoluta e parâmetros de query sensíveis
(token/sessão) são recusados para não persistir credenciais.

`marketplace + external_id` é único: captura repetida reutiliza o
`MarketplaceProduct`/`Product` e acrescenta novo `Offer`, `RawCapture`,
`Evidence`, `DiscoveryEvent`, `Candidate` e `AuditEvent` na mesma transação.
`CapturedOffer` retorna ids distintos de Product, MarketplaceProduct, Offer e
Candidate.

```json
{
  "schema_version": "1.0",
  "status": "CAPTURED",
  "correlation_id": "cid-1",
  "candidate_id": "cand_...",
  "candidate_state": "NEW",
  "offer_id": "off_...",
  "product_id": "prd_...",
  "marketplace_product_id": "mkt_...",
  "raw_capture_id": "raw_...",
  "discovery_event_id": "disc_...",
  "audit_event_id": "aud_...",
  "marketplace": "MERCADO_LIVRE",
  "external_id": "MLB123",
  "source": "BROWSER_EXTENSION",
  "title": "Produto",
  "captured_at": "2026-10-05T12:00:00+00:00",
  "duplicate_identity": false
}
```

`GET /candidates/{candidate_id}` devolve o mesmo contrato (sem
`duplicate_identity`, que é um fato do momento da captura) e preserva o
`correlation_id` original da captura no corpo. Erros retornam
`{schema_version, status:"INVALID", correlation_id, error}` com códigos
`RAD-CAP-001..005` (ver `docs/ERROR_CATALOG.md`). `Evidence.confidence` fica
nula nesta etapa; a calibração pertence ao Confidence Engine (RDR-029). A
captura retorna também `price_observation_id`, a observação append-only criada ou
reutilizada.

## Price history, implementação (TKT-04)

Implementado em `GET /marketplace-products/{marketplace_product_id}/price-history`
(`schema_version=1.0`). Cada captura normalizada acrescenta uma
`PriceObservation` append-only na mesma transação do grafo de captura. A
identidade documentada é `(marketplace_product_id, source, observed_at)`; a
captura repetida com a mesma identidade reutiliza a observação existente, sem
sobrescrever o histórico e sem inventar novo preço. `price`/`original_price`/
`shipping_cost` são strings decimais (nunca float binário) e `observed_at` é
UTC. A série é retornada em ordem cronológica com proveniência.

```json
{
  "schema_version": "1.0",
  "status": "OK",
  "correlation_id": "cid-history",
  "marketplace_product_id": "mkt_...",
  "marketplace": "MERCADO_LIVRE",
  "external_id": "MLB123",
  "observation_count": 2,
  "observations": [
    {
      "price_observation_id": "obs_...",
      "price": "79.90",
      "original_price": "109.90",
      "shipping_cost": null,
      "source": "BROWSER_EXTENSION",
      "observed_at": "2026-10-05T12:00:00+00:00",
      "correlation_id": "cid-1",
      "raw_capture_id": "raw_..."
    }
  ]
}
```

MarketplaceProduct inexistente retorna 404 com `RAD-CAP-005`. `shipping_cost`
permanece `null` até existir captura de frete (ticket próprio); a observação não
calcula frete, desconto nem score.


## AI Editorial Review input

```json
{
  "schema_version": "1.0",
  "task": "EDITORIAL_REVIEW",
  "brand": "RADAR_BEAUTY",
  "product": {},
  "offer": {},
  "evaluation": {
    "deal_score": 91,
    "monetization_score": 68,
    "confidence": "HIGH"
  },
  "allowed_claims": [],
  "warnings": []
}
```

## AI Editorial Review output

```json
{
  "decision": "APPROVE",
  "editorial_angle": "PRICE_OPPORTUNITY",
  "reason_codes": [
    "STRONG_BRAND_FIT",
    "GOOD_PRICE_CONTEXT"
  ],
  "warnings": []
}
```

Decisões permitidas:
- APPROVE
- REVIEW
- REJECT

A IA nunca retorna `AUTO_PUBLISH`.

## Content Generation output

```json
{
  "headline": "string",
  "body": "string",
  "cta": "string",
  "warnings": []
}
```

Affiliate URL, preço formatado e disclosure são adicionados pelo renderer determinístico.

## Error Contract

```json
{
  "error": {
    "code": "MARKETPLACE_SESSION_EXPIRED",
    "message": "Authentication required.",
    "retryable": false,
    "context": {
      "marketplace": "MERCADO_LIVRE"
    }
  }
}
```

## Enums principais

`Channel` identifica a plataforma; o destino WA V1 tem `destination_type=GROUP` e capability `PUBLISH_WHATSAPP_GROUP`. Não usar PUBLISH_WHATSAPP_CHANNEL como alias. Registro de destino/vínculo e receipt seguem o contrato abaixo; campos adicionais/migrations serão formalizados antes da implementação.

Marketplace:
- MERCADO_LIVRE
- SHOPEE

Brand:
- RADAR_BEAUTY
- CASA_EM_ORDEM

Channel:
- TELEGRAM
- WHATSAPP

Confidence:
- LOW
- MEDIUM
- HIGH

Decision:
- REJECT
- REVIEW
- APPROVE

AutomationMode:
- MANUAL
- SHADOW
- ASSISTED
- AUTO

## Configuration contract

Config operacional é JSON (`config/radar.json`, opcional; precedência `defaults < arquivo < env RADAR_*`) e validado por schema com `extra=forbid`. `radarctl config` e `GET /config` expõem o contrato sanitizado abaixo; secret *values* nunca aparecem, apenas referências por nome lógico (RDR-004, RDR-005). `config_hash` é SHA-256 do JSON canônico da configuração efetiva.

```json
{
  "schema_version": "1.0",
  "status": "VALID",
  "correlation_id": "...",
  "config": {
    "schema_version": "1.0",
    "environment": "development",
    "timezone": "America/Maceio",
    "log_level": "INFO",
    "automation_mode": "SHADOW",
    "data_dir": "/.../data",
    "database_url": "sqlite+pysqlite:////.../data/radar.db",
    "config_hash": "...",
    "source": "defaults",
    "secret_refs": ["telegram_bot_token"]
  },
  "secrets": {
    "declared": ["telegram_bot_token"],
    "status": {"telegram_bot_token": "present"}
  }
}
```

Config inválida bloqueia CLI/API com `RAD-CFG-001`/`RAD-CFG-002`. Secret ausente (`status=missing`) é reportado por nome e bloqueia somente a capability que o requer (`RAD-CFG-003`), sem persistir ou logar o valor.

## Idempotency

WhatsApp V1 usa grupos explicitamente cadastrados (`destination_type=GROUP`), pela capability `PUBLISH_WHATSAPP_GROUP`; `Channel.WHATSAPP` continua a plataforma. Channels não são a capability V1 deste fluxo. Nome de grupo e message-id não comprovam identidade persistente de destino.

Cada destino mantém identidade interna, marca, sandbox/produção e vínculo verificado ao grupo. O vínculo registra método/evidência, versão e revisão humana; somente pode habilitar envio após prova de identificação e reverificação segura. ID externo só é persistido se obtido por superfície permitida e validado; nunca inferido de storage/cookies/tokens. Sem essa prova, manter envio bloqueado e HumanAction/CAPABILITY_CONFLICT apenas para WA. Mudança de contexto, vínculo inválido ou grupo homônimo bloqueia antes do clique.

Serializer canônico define blocos e separadores de linha, aplica renderer determinístico e compara hash do conteúdo efetivamente preparado com o aprovado. Não usar `innerText`/`textContent` sem normalização especificada. Preview não autoriza envio. Preflight revalida destino, marca, conteúdo, oferta, compliance, nonce e aprovação da Publication imediatamente antes de um único Send.

`Enviada`/bubble/message marker são evidência de envio observado, não promessa de entrega/leitura. Receipt registra destino interno/vínculo, publication/revision, hash, correlation_id, observed_at e marcador externo quando disponível. Ausência de confirmação suficiente, timeout ou crash na janela de envio gera resultado desconhecido persistido, publicação suspensa e HumanAction, sem reenvio automático. Dedupe não depende de bubble: mensagens temporárias/reload/restore não apagam a proteção persistente (GRILL-002/003).

TrackingContext interno é separado da etiqueta externa ML. `tracking_label` aceita somente `[a-z0-9]{1,30}`; mapear por configuração explícita e auditável, com unicidade e validação de associação. Não transformar silenciosamente maiúsculas, separadores ou truncar para caber; criação/configuração de etiqueta continua humana. `rbtgoffer` é exemplo sintático, não etiqueta já existente/autorizada.

Gerar link/ID ML adiciona o produto a Minhas recomendações e é side effect: somente após Opportunity aprovada, autorização/gates e auditoria. Correlacionar input, etiqueta, tentativa e resultado; erro atual invalida seção de resultado anterior ainda visível. Preservar link literal retornado. Aceitar formato social legítimo somente quando produto destacado, catálogo/anúncio e contexto esperado coincidirem; outra recomendação no perfil não comprova o link. Short redirect, variante/vendedor, ausência da barra e recuperação permanecem aceites distintos.

Shopee tem três superfícies: API oficial para operações recorrentes documentadas; `affiliate.shopee.com.br` manual/diagnóstico; `shopee.com.br` captura pública assistida candidata. Proteção/indisponibilidade não autoriza alternar para browser como contorno. Sem geração operacional recorrente de links por extensão no portal.

Documentação Brasil confirmou POST GraphQL `https://open-api.affiliate.shopee.com.br/graphql`, `productOfferV2`, `shopeeOfferV2`, `shopOfferV2` e mutation `generateShortLink(originUrl, subIds)`; feeds/relatórios também foram documentados, mas sua existência não amplia analytics V1. AppID/Secret só no SecretsProvider. Assinar SHA256 de AppID + Timestamp + bytes JSON exatos + Secret, hex minúsculo; tolerância documentada de 10 minutos. Inconsistência Credential/Credentials precisa de validação oficial no SPIKE-02 antes de runtime.

HTTP 200 com errors/data parcial não é sucesso do contrato. Int64 cruza TypeScript/JSON sem perda (IDs como strings decimais); dinheiro/comissão usa Decimal a partir de strings. priceMin/Max é range de oferta, não preço de SKU escolhido/checkout. Paginação depende da operação; respeitar orçamento/backoff e classificar 10020 por reason sanitizado, 10030 como rate limit e 10035 como entitlement. Acesso da conta/API live permanece pendente; documentação não equivale a API_SUPPORTED nem ausência de acesso a NOT_SUPPORTED global.

Sub IDs preservam até cinco posições (brand, channel, content_type, category, referência interna), sem PII. Mapear/serializar valores explicitamente; comprimento por campo não foi comprovado e é gate para runtime correspondente. Retorno shortLink é literal, não sintetizado/editado. Mutation com resultado desconhecido não recebe retry cego; Core mantém idempotência/auditoria/reconciliação sem presumir chave de idempotência remota.

Captura pública registra source_url/observed_at, shop/item, campanha/categoria e contexto de variante/preço. Descobrir campanha vigente: IDs históricos de promoção não são configuração fixa. Loading difere de EMPTY; CHALLENGE após DOM inicial suspende parte afetada, exige intervenção humana e revalidação na retomada. E-SP-PUB-08 confirmou preço somente da opção 12L; opção preta/checkout/recorrência não foram validados. Cache/TTL/dedupe reduzem consultas, mas sem dado atual verificável por fonte permitida a revalidação pré-envio bloqueia publicação.

Operações de side effect recebem `idempotency_key`.

Exemplo:
`publish:{brand}:{channel}:{opportunity}:{revision}`

## Correlation ID

Toda execução originada de uma descoberta deve manter o mesmo `correlation_id` até Publication e post-publication events.
