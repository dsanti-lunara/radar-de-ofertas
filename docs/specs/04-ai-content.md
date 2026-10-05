# SPEC-04: IA e conteúdo

## Problem Statement

O operador precisa de conteúdo editorial sem permitir que a IA invente fatos, modifique links ou assuma decisões de segurança.

## Solution

Entregar ia e conteúdo como parte da V1 aprovada, com contratos públicos verificáveis, caminhos de falha/recuperação auditáveis e gates das integrações externas preservados.

## User Stories

1. Como operador do Radar, quero versionar Knowledge Pack por marca e canal, para operar esta etapa de forma correta, segura e rastreável.
2. Como operador do Radar, quero selecionar contexto mínimo por tarefa, para operar esta etapa de forma correta, segura e rastreável.
3. Como operador do Radar, quero usar FakeAIProvider em desenvolvimento, para operar esta etapa de forma correta, segura e rastreável.
4. Como operador do Radar, quero validar elegibilidade real do provider no spike, para operar esta etapa de forma correta, segura e rastreável.
5. Como operador do Radar, quero separar Editorial Review de Content Generation, para operar esta etapa de forma correta, segura e rastreável.
6. Como operador do Radar, quero validar respostas estruturadas, para operar esta etapa de forma correta, segura e rastreável.
7. Como operador do Radar, quero bloquear números comerciais sem Evidence, para operar esta etapa de forma correta, segura e rastreável.
8. Como operador do Radar, quero bloquear claims proibidos ou não sustentados, para operar esta etapa de forma correta, segura e rastreável.
9. Como operador do Radar, quero tratar conteúdo de marketplace como dado não confiável, para operar esta etapa de forma correta, segura e rastreável.
10. Como operador do Radar, quero impedir URLs geradas pela IA, para operar esta etapa de forma correta, segura e rastreável.
11. Como operador do Radar, quero preservar generated e final content e decisões humanas, para operar esta etapa de forma correta, segura e rastreável.
12. Como operador do Radar, quero cachear apenas entradas equivalentes e versionadas, para operar esta etapa de forma correta, segura e rastreável.
13. Como operador do Radar, quero tratar timeout, refusal e rate limit sem publicação cega, para operar esta etapa de forma correta, segura e rastreável.
14. Como operador do Radar, quero avaliar Golden Dataset e casos adversariais, para operar esta etapa de forma correta, segura e rastreável.

## Implementation Decisions

- Interface evaluate_candidate/generate_content/review_content/classify_product quando necessário; provider isola autenticação.
- Não presumir capability técnica pela assinatura ChatGPT; sem integração pela interface web do ChatGPT; API paga é alternativa futura opcional.
- IA nunca calcula scores, decide compliance ou gera/altera links; backend insere URL, preço renderizado e disclosure.
- Schema, Numeric Guard, Claim Guard e regras de canal precedem conteúdo utilizável; falhas podem abrir circuit breaker.
- Knowledge/prompt/model e ai_input_hash preservam contexto de cache; feedback não muda regras automaticamente.

## Testing Decisions

- Fronteira aprovada: Contrato AIProvider e validação pública de conteúdo gerado.
- Testar comportamento externo e resultados persistidos, nunca estrutura interna ou mocks que apenas repetem implementação.
- Prior art: matriz QA e contratos SDD; ainda não há código/testes versionados. Preferir as interfaces aprovadas ao criar as primeiras seams.
- schema inválido, enum inválido, timeout, refusal e rate limit.
- prompt injection, números falsos, claims proibidos e URL inventada.
- cache invalidado por mudanças relevantes.
- Golden/adversarial dataset por propriedades, sem frase exata.

## Out of Scope

Automação web do ChatGPT, treinamento/ML e ativação automática de provider sem spike.

## Further Notes

### Objective

Entregar o comportamento descrito com evidência de sucesso, falha, recuperação, auditoria, segurança e idempotência quando houver side effect.

### Context / SDD references

SDDs 04, 06, 12 e 13. Vocabulário de CONTEXT e ADRs vigentes; os SDDs e Decision Log continuam autoridade. SPEC-00 organiza a entrega, sem redefinir arquitetura.

### In scope

Histórias e decisões desta spec; rastreabilidade RDR-045..RDR-055; RDR-122..RDR-123. São IDs locais do Issue Map, não números GitHub. Não renumerar nem perder AC ao fundir itens inseparáveis.

### Dependencies

SPEC-01, SPEC-02 e SPEC-03; provider real condicionado a SPIKE-01/RDR-048.

### Contracts

Usar entradas, saídas, estados e erros dos SDDs referenciados; schema_version e Correlation ID nos contratos aplicáveis. External providers permanecem não confiáveis. Formalizar campos/enums/migrations adicionais em cada issue antes de implementação; nenhuma lacuna autoriza inventar capability externa.

### Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. Não alterar arquitetura silenciosamente. Testes seguros por padrão; live opt-in, sandbox e autorização específica para side effect. Não publicar em destino real nesta spec. Não ignorar teste, validação, idempotência ou compliance para simplificar.

### Acceptance Criteria

- [ ] Evidência verificável para versionar Knowledge Pack por marca e canal.
- [ ] Evidência verificável para selecionar contexto mínimo por tarefa.
- [ ] Evidência verificável para usar FakeAIProvider em desenvolvimento.
- [ ] Evidência verificável para validar elegibilidade real do provider no spike.
- [ ] Evidência verificável para separar Editorial Review de Content Generation.
- [ ] Evidência verificável para validar respostas estruturadas.
- [ ] Evidência verificável para bloquear números comerciais sem Evidence.
- [ ] Evidência verificável para bloquear claims proibidos ou não sustentados.
- [ ] Evidência verificável para tratar conteúdo de marketplace como dado não confiável.
- [ ] Evidência verificável para impedir URLs geradas pela IA.
- [ ] Evidência verificável para preservar generated e final content e decisões humanas.
- [ ] Evidência verificável para cachear apenas entradas equivalentes e versionadas.
- [ ] Evidência verificável para tratar timeout, refusal e rate limit sem publicação cega.
- [ ] Evidência verificável para avaliar Golden Dataset e casos adversariais.
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

