# 12, Security, Compliance and Failure Boundaries

## Trust model

Trusted:
- Radar Core;
- deterministic rules;
- trusted storage/config/knowledge.

Untrusted:
- browser pages;
- marketplace content;
- AI output;
- external services.

## Regra principal

Marketplace content é dado, nunca instrução.

Fluxo:
`external → extract → sanitize → normalize → validate → rules → action`

HTML bruto nunca é enviado para IA.

## Prompt injection

Campos externos livres devem ser explicitamente tratados como untrusted.

A IA não recebe secrets.

Pseudo-system prompts em título/descrição/seller devem ser ignorados e cobertos por testes adversariais.

## Browser security

- host allowlist;
- URL canonicalization;
- https only para jobs normais;
- bloquear javascript:/data:/file:/chrome:;
- redirect guard;
- command allowlist;
- schema validation;
- nonce/timestamp;
- replay protection;
- pairing secret;
- content script como fronteira;
- página não acessa diretamente privilégios do service worker.

## Context verification

Antes de side effect:
- expected marketplace == actual;
- expected product == actual;
- expected brand/destination == actual;
- expected message hash == actual;
- validated link.

Mismatch bloqueia.

## WhatsApp

Somente destinos explicitamente cadastrados.

Não:
- ler conversas pessoais;
- procurar contatos arbitrários;
- enviar para grupos/listas não cadastrados.

## AI output

Pipeline:
`AI → schema → numeric guard → claim guard → compliance → renderer`

AI output é não confiável até passar por todos os validators.

## Compliance

`Compliance Engine` é determinístico e precede:
- AI;
- Workflow side effects;
- Publishing Policy.

Policy contém:
- version;
- effective_from;
- last_reviewed_at;
- review_due_at;
- source reference;
- status.

Status:
- ACTIVE
- REVIEW_REQUIRED
- BLOCKED
- UNKNOWN

Policy vencida/unknown pode desabilitar automação externa.

## Media

V1 é text + link.

Não reutilizar automaticamente imagens/vídeos de listings.

## Secrets

Least privilege por componente.

Exemplo:
- TelegramPublisher acessa somente telegram token;
- AI provider acessa somente auth dele;
- Shopee API adapter acessa somente suas credenciais;
- Browser auth acessa pairing secret.

## VM/browser

- VM dedicada;
- browser dedicado;
- sem navegação pessoal;
- sem extensões desnecessárias;
- sem `chrome.debugger`;
- sem clipboardRead/downloads/webRequest amplo sem necessidade demonstrada.

## Circuit breakers

Independentes por integração.

Exemplos:
- vários DOM_CHANGED → abrir circuito do browser daquele marketplace;
- várias falhas inesperadas de publicação → suspender AUTO do publisher;
- challenge/security review do marketplace → SECURITY_REVIEW_REQUIRED.

## Failure isolation

Domínios:
- DATABASE
- AI
- BROWSER
- ML
- SHOPEE
- WHATSAPP
- TELEGRAM
- BACKUP
- CONFIG

Falha de uma integração não derruba outras se não houver necessidade.

Falha de integridade do banco bloqueia side effects globais.

## Emergency control

`STOP_EXTERNAL_ACTIONS` bloqueia:
- publicação;
- ações de browser;
- geração autenticada de links;

mas mantém:
- UI;
- diagnóstico;
- leitura;
- recovery.

## Security events

Exemplos:
- AUTH_FAILURE
- INVALID_BRIDGE_TOKEN
- REPLAY_BLOCKED
- UNTRUSTED_HOST
- DESTINATION_MISMATCH
- PROMPT_INJECTION_DETECTED
- SECRET_REDACTED
- POLICY_BLOCK

## Browser Recon Mode

Durante reconnaissance:
- AUTO_PUBLISH off;
- side effects irreversíveis exigem autorização;
- diagnostics mais detalhados;
- fixtures devem ser sanitizadas antes de Git.
