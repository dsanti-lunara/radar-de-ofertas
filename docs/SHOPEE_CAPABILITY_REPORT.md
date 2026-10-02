# Shopee Capability Report

Status inicial: **PENDING SPIKE-02**

Este arquivo deve ser preenchido pelo Codex após investigar a área oficial de API da conta e a documentação acessível ao usuário.

## Regra

Não assumir capabilities a partir de documentação de outro país, package de terceiros ou engenharia reversa.

Confirmar aquilo que a conta Brasil realmente oferece.

## Informações a registrar

### Conta/API

- nome da área:
- método de autenticação:
- App ID / public identifiers:
- secret existe? sim/não, não registrar o valor
- environment:
- base URL oficial:
- GraphQL/REST:
- token/refresh behavior:
- rate limits:
- documentation source:

### Capabilities

| Capability | Supported | Method | Evidence | Notes |
|---|---:|---|---|---|
| Product discovery | TBD | TBD | | |
| Product details | TBD | TBD | | |
| Affiliate offers | TBD | TBD | | |
| Brand offers | TBD | TBD | | |
| Campaigns | TBD | TBD | | |
| Short/affiliate link | TBD | TBD | | |
| Sub IDs | TBD | TBD | | |
| Conversion report | TBD | TBD | | |
| Validated report | TBD | TBD | | |

## Decisão por capability

```text
API_SUPPORTED
BROWSER_ASSISTED
MANUAL
NOT_SUPPORTED
```

## Security

Não colocar secret, access token ou refresh token neste documento.

## Output

Ao final do spike:
1. atualizar tabela;
2. registrar gaps;
3. registrar rate/usage constraints;
4. listar quais issues RDR-095..RDR-102 precisam ser criadas, removidas ou divididas;
5. não implementar adapter nesta mesma task, a menos que a issue explicitamente autorize.
