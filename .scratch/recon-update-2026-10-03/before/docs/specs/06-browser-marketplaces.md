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

SPEC-01 e SPEC-03; SPEC-05 para publicação. SPIKE-02, SPIKE-03 e SPIKE-04 antes dos adapters dependentes.

### Contracts

Usar entradas, saídas, estados e erros dos SDDs referenciados; schema_version e Correlation ID nos contratos aplicáveis. External providers permanecem não confiáveis. Formalizar campos/enums/migrations adicionais em cada issue antes de implementação; nenhuma lacuna autoriza inventar capability externa.

### Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. Não alterar arquitetura silenciosamente. Testes seguros por padrão; live opt-in, sandbox e autorização específica para side effect. Não publicar em destino real nesta spec. Não ignorar teste, validação, idempotência ou compliance para simplificar.

### Acceptance Criteria

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

Unit e contract relevantes; integration com dependências locais reais quando aplicável; segurança funcional e E2E do fluxo. Live/fixtures/sandbox somente nos gates descritos, nunca por padrão.

### Observability

Estado/saúde e erros acionáveis do fluxo, Correlation ID, eventos auditáveis e HumanActions quando necessária intervenção. Sem secrets/PII desnecessária em logs ou evidências.

### Documentation to update

SDDs referenciados, contratos afetados, QA traceability, Error Catalog/runbooks quando aplicáveis e Issue Map com links de execução. Registrar novas decisões difíceis de reverter em ADR quando justificadas.

### Completion report

Arquivos, testes/resultados, testes não executados/motivos, limitações, mudanças de contrato, migrations/config changes e riscos restantes. Atualizar a issue com evidência e critérios verificados; não ativar AUTO.

