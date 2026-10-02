# 04, Data Contracts

Todos os contratos externos devem ter `schema_version`.

## Browser Bridge, get job

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
    "tracking_label": "RB_TG_OFFER",
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

## Idempotency

Operações de side effect recebem `idempotency_key`.

Exemplo:
`publish:{brand}:{channel}:{opportunity}:{revision}`

## Correlation ID

Toda execução originada de uma descoberta deve manter o mesmo `correlation_id` até Publication e post-publication events.
