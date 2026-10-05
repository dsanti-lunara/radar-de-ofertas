# Browser Reconnaissance, roteiro obrigatório para o Codex

## Status da execução registrada

**Investigação FINALIZADA** na sessão de 2026-10-02 America/Sao_Paulo (2026-10-03 UTC), por autorização do operador. Resultado vigente: [avaliação consolidada](recon/2026-10-02/BROWSER_RECON_COMPLETION.md), incluindo ML, Shopee API/portal/site público e WhatsApp **Groups**, conforme decisão do usuário. Evidências, URLs, limitações e gaps estão no pacote; 14 verificações offline passaram.

Fechamento da investigação não aprova adapters ou produção. Pendências de implementação, API autenticada e homologação estão nos [gates de produção](recon/2026-10-02/PRODUCTION_READINESS.md). O roteiro abaixo continua sendo referência; seus contratos foram reconciliados para Groups em 2026-10-03; identidade/fixtures/adapter/Chrome VM continuam gates antes do envio.

Este arquivo existe exclusivamente para a investigação real das superfícies autenticadas antes da implementação de adapters.

## Objetivo

Descobrir, com evidência real:
- superfícies;
- page states;
- auth behavior;
- elementos interativos;
- seletores estáveis;
- fallbacks;
- modais;
- navegação SPA;
- resultado das ações;
- failure states;
- side effects;
- limites reais das capabilities.

## Regras

Antes de começar:
1. colocar capability afetada em `BROWSER_RECON_MODE`;
2. garantir publicação automática desligada;
3. não alterar configuração comercial de conta;
4. não automatizar login, senha, 2FA ou CAPTCHA;
5. não extrair cookie/token/session;
6. não reproduzir endpoint privado observado no DevTools;
7. não executar side effect real sem autorização explícita;
8. usar sandbox quando side effect de publicação for necessário.

## O que pode ser coletado

- screenshots técnicos revisados;
- outerHTML de regiões necessárias;
- roles;
- labels;
- aria attributes;
- stable ids/data-testid;
- DOM relativo;
- URLs sanitizadas;
- textos de botão;
- estados loading/ready/error;
- timings aproximados;
- fixtures sanitizadas.

## O que não pode ir para fixtures/Git

- secrets;
- tokens;
- cookies;
- QR codes de autenticação;
- telefone/e-mail pessoal;
- dados desnecessários da conta;
- histórico privado de WhatsApp;
- dados de pagamento.

## Mercado Livre

Investigar:

### ML-01, Central de Afiliados
- URL/caminho;
- auth state;
- navegação para Gerador de Links.

### ML-02, Gerador de Links vazio
- URL input;
- etiqueta/tracking;
- opções short/full link;
- botão gerar;
- estados disabled/loading.

### ML-03, após preencher produto
- validações;
- erros de URL;
- diferenças por tipo de página.

### ML-04, resultado
- local do affiliate URL;
- copy button;
- formato;
- indicadores de sucesso/erro.

### ML-05, etiquetas
- caracteres;
- limites;
- quantidade;
- persistência;
- associação ao link.

### ML-06, produto com Barra de Afiliados
- page detector;
- botão Compartilhar;
- modal;
- resultado;
- condição em que a barra não aparece.

### Estados
- READY
- AUTH_REQUIRED
- CHALLENGE
- UNSUPPORTED
- DOM_CHANGED

Produzir:
- `ML_BROWSER_SURFACE_MAP.md`
- `ML_CAPABILITY_MATRIX.md`
- selector registry candidate
- fixtures
- gap report

## Shopee

Investigar:

### SP-01, Dashboard de afiliados
### SP-02, Oferta de Produto
### SP-03, fluxo Obter link
### SP-04, Link de Conversão
### SP-05, resultado de link
### SP-06, Sub IDs
### SP-07, Oferta da Loja
### SP-08, Campanhas/Ofertas Exclusivas
### SP-09, Abrir API
### SP-10, capabilities/credenciais documentadas para a conta

Não fazer crawling massivo.

Produzir:
- `SP_BROWSER_SURFACE_MAP.md`
- `SP_CAPABILITY_MATRIX.md`
- selector registry candidate
- fixtures
- gap report
- atualizar `SHOPEE_CAPABILITY_REPORT.md`

## WhatsApp Groups

Consumir E-WA-01..06 e registrar gaps sem refazer ou inferir experimento. Nome/header não comprova identidade persistente; investigar pareamento/reverificação permitidos, sem storage/tokens. Fixtures/fallbacks/Chrome VM/unknown result são aceites próprios; nenhum novo envio é autorizado pelo roteiro.

Investigar somente grupos cadastrados/grupo sandbox.

### WA-01, WhatsApp Web carregado
- logged-in;
- offline;
- loading;
- reconnect.

### WA-02, seleção do grupo
- como identificar o destino de forma estável;
- se há identificador persistente melhor que texto;
- estado de grupo/vínculo correto.

### WA-03, compositor
- contenteditable;
- multiline behavior;
- link preview;
- texto final;
- botão Send;
- loading.

### WA-04, pós-envio
- evidência de sucesso;
- possível reference/message marker;
- erros.

### Guardrails
Testar:
- destination mismatch;
- message hash mismatch;
- auth required;
- DOM changed;
- send button ambiguity.

Produzir:
- `WA_BROWSER_SURFACE_MAP.md`
- `WA_CAPABILITY_MATRIX.md`
- selector registry candidate
- fixtures
- gap report

## Selector review

Para cada elemento:

```text
Capability:
Page:
Element:
Primary selector:
Why stable:
Fallback 1:
Fallback 2:
Ambiguity risk:
Observed states:
Screenshot/fixture:
```

Preferência:
1. semantic role;
2. stable attribute;
3. aria-label/label;
4. stable data-testid;
5. relative structure;
6. CSS específico.

Não aprovar coordenadas ou `nth-child` como estratégia principal.

## Gate para implementação

Capability só pode virar issue de adapter real quando houver:
- surface confirmed;
- state map;
- auth behavior;
- primary selector candidates;
- fallbacks;
- ambiguity behavior;
- fixture;
- expected errors;
- safe live evidence.

Se a UI real contradizer o SDD, emitir `CAPABILITY_CONFLICT`.
