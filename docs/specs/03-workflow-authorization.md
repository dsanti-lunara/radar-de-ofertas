# SPEC-03: Workflow e autorização

## Problem Statement

Jobs sem limites claros de autorização, lease e recuperação podem executar ações indevidas ou ficar presos após falhas.

## Solution

Entregar workflow e autorização como parte da V1 aprovada, com contratos públicos verificáveis, caminhos de falha/recuperação auditáveis e gates das integrações externas preservados.

## User Stories

1. Como operador do Radar, quero persistir jobs com prioridade, attempts e disponibilidade, para operar esta etapa de forma correta, segura e rastreável.
2. Como operador do Radar, quero claimar jobs com lease expirável, para operar esta etapa de forma correta, segura e rastreável.
3. Como operador do Radar, quero impedir execução sobreposta com locks, para operar esta etapa de forma correta, segura e rastreável.
4. Como operador do Radar, quero aplicar retry apenas a falhas transient, para operar esta etapa de forma correta, segura e rastreável.
5. Como operador do Radar, quero pausar AUTH_REQUIRED sem retry contínuo, para operar esta etapa de forma correta, segura e rastreável.
6. Como operador do Radar, quero encaminhar tentativas esgotadas à Dead Job Queue, para operar esta etapa de forma correta, segura e rastreável.
7. Como operador do Radar, quero criar schedules sem executar negócio no Scheduler, para operar esta etapa de forma correta, segura e rastreável.
8. Como operador do Radar, quero coalescer ticks perdidos quando apropriado, para operar esta etapa de forma correta, segura e rastreável.
9. Como operador do Radar, quero centralizar HumanActions, para operar esta etapa de forma correta, segura e rastreável.
10. Como operador do Radar, quero transicionar domínio pelo Workflow Engine, para operar esta etapa de forma correta, segura e rastreável.
11. Como operador do Radar, quero avaliar em SHADOW sem envio comercial, para operar esta etapa de forma correta, segura e rastreável.
12. Como operador do Radar, quero exigir aprovação explícita da publicação em ASSISTED, para operar esta etapa de forma correta, segura e rastreável.
13. Como operador do Radar, quero aprovar Candidate sem autorizar envio, para operar esta etapa de forma correta, segura e rastreável.
14. Como operador do Radar, quero revalidar entidades envelhecidas, para operar esta etapa de forma correta, segura e rastreável.
15. Como operador do Radar, quero pausar, drenar e interromper ações externas, para operar esta etapa de forma correta, segura e rastreável.
16. Como operador do Radar, quero isolar falhas por integração, para operar esta etapa de forma correta, segura e rastreável.

## Implementation Decisions

- Workflow Engine central, workers não chamam workers; estados de domínio separados de estados de Job.
- Filas GENERAL, AI, BROWSER e PUBLISHING; concorrência conservadora configurável; browser assíncrono.
- Policies variam por brand × marketplace × channel × capability; AUTO nunca ativado pelo agente.
- SHADOW registra avaliações e previews sem envio comercial; ASSISTED exige aprovação humana explícita da publicação.
- TTL, revalidação e conteúdo STALE preservam guardrails; recuperação de envio desconhecido é definida em SPEC-05.

## Testing Decisions

- Fronteira aprovada: Comandos públicos da Application para workflow, aprovação e controles operacionais.
- Testar comportamento externo e resultados persistidos, nunca estrutura interna ou mocks que apenas repetem implementação.
- Prior art: matriz QA e contratos SDD; ainda não há código/testes versionados. Preferir as interfaces aprovadas ao criar as primeiras seams.
- lease expiry, locks, retry/backoff e Dead Jobs.
- no retry para AUTH_REQUIRED e isolamento de falhas.
- missed schedules, TTL e staleness com relógio controlável.
- SHADOW zero envio e Candidate aprovado insuficiente em ASSISTED.
- pause/drain/kill switches sem contornar compliance.

## Out of Scope

DSL, broker, execução distribuída e promoção automática para AUTO.

## Further Notes

### Objective

Entregar o comportamento descrito com evidência de sucesso, falha, recuperação, auditoria, segurança e idempotência quando houver side effect.

### Context / SDD references

SDDs 03, 04, 08, 11, 12 e 13; GRILL-001. Vocabulário de CONTEXT e ADRs vigentes; os SDDs e Decision Log continuam autoridade. SPEC-00 organiza a entrega, sem redefinir arquitetura.

### In scope

Histórias e decisões desta spec; rastreabilidade RDR-034..RDR-044; integração com RDR-060, RDR-066 e RDR-108. São IDs locais do Issue Map, não números GitHub. Não renumerar nem perder AC ao fundir itens inseparáveis.

### Dependencies

SPEC-01; SPEC-02 para transições de seleção.

### Contracts

Usar entradas, saídas, estados e erros dos SDDs referenciados; schema_version e Correlation ID nos contratos aplicáveis. External providers permanecem não confiáveis. Formalizar campos/enums/migrations adicionais em cada issue antes de implementação; nenhuma lacuna autoriza inventar capability externa.

### Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. Não alterar arquitetura silenciosamente. Testes seguros por padrão; live opt-in, sandbox e autorização específica para side effect. Não publicar em destino real nesta spec. Não ignorar teste, validação, idempotência ou compliance para simplificar.

### Acceptance Criteria

- [ ] Evidência verificável para persistir jobs com prioridade, attempts e disponibilidade.
- [ ] Evidência verificável para claimar jobs com lease expirável.
- [ ] Evidência verificável para impedir execução sobreposta com locks.
- [ ] Evidência verificável para aplicar retry apenas a falhas transient.
- [ ] Evidência verificável para pausar AUTH_REQUIRED sem retry contínuo.
- [ ] Evidência verificável para encaminhar tentativas esgotadas à Dead Job Queue.
- [ ] Evidência verificável para criar schedules sem executar negócio no Scheduler.
- [ ] Evidência verificável para coalescer ticks perdidos quando apropriado.
- [ ] Evidência verificável para centralizar HumanActions.
- [ ] Evidência verificável para transicionar domínio pelo Workflow Engine.
- [ ] Evidência verificável para avaliar em SHADOW sem envio comercial.
- [ ] Evidência verificável para exigir aprovação explícita da publicação em ASSISTED.
- [ ] Evidência verificável para aprovar Candidate sem autorizar envio.
- [ ] Evidência verificável para revalidar entidades envelhecidas.
- [ ] Evidência verificável para pausar, drenar e interromper ações externas.
- [ ] Evidência verificável para isolar falhas por integração.
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

