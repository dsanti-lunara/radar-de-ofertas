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
- GENERATE_SHOPEE_AFFILIATE_LINK
- VALIDATE_AFFILIATE_LINK
- CHECK_MARKETPLACE_SESSION
- PUBLISH_WHATSAPP_CHANNEL
- RESUME_JOB

## Mercado Livre

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

Browser pode ser usado de forma assistida/fallback nas superfícies validadas:
- Link de Conversão;
- Oferta de Produto;
- Oferta da Loja;
- campanhas;
- outras encontradas no Recon.

Sem crawling massivo.

## WhatsApp

Usa o mesmo Chrome/profile.

Somente destinos cadastrados:
- Radar Beauty Channel
- Casa em Ordem Channel
- sandbox channel para testes

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
