# SPEC-01: Fundação e domínio

## Problem Statement

Sem configuração validada, entidades distintas e persistência íntegra, o operador não consegue confiar na continuidade e na proveniência do pipeline.

## Solution

Entregar fundação e domínio como parte da V1 aprovada, com contratos públicos verificáveis, caminhos de falha/recuperação auditáveis e gates das integrações externas preservados.

## User Stories

1. Como operador do Radar, quero iniciar o monorepo com a stack congelada, para operar esta etapa de forma correta, segura e rastreável.
2. Como operador do Radar, quero validar configuração antes de executar workers, para operar esta etapa de forma correta, segura e rastreável.
3. Como operador do Radar, quero acessar segredos pelo SecretsProvider sem persistência comum, para operar esta etapa de forma correta, segura e rastreável.
4. Como operador do Radar, quero identificar saúde de sistema e dependências, para operar esta etapa de forma correta, segura e rastreável.
5. Como operador do Radar, quero preservar Product e MarketplaceProduct como identidades distintas, para operar esta etapa de forma correta, segura e rastreável.
6. Como operador do Radar, quero capturar Offer sem confundir produto e condição comercial, para operar esta etapa de forma correta, segura e rastreável.
7. Como operador do Radar, quero preservar RawCapture sanitizada e Evidence, para operar esta etapa de forma correta, segura e rastreável.
8. Como operador do Radar, quero registrar DiscoveryEvent e Candidate, para operar esta etapa de forma correta, segura e rastreável.
9. Como operador do Radar, quero guardar PriceObservation append-only, para operar esta etapa de forma correta, segura e rastreável.
10. Como operador do Radar, quero guardar Evaluation imutável e versionada, para operar esta etapa de forma correta, segura e rastreável.
11. Como operador do Radar, quero criar Opportunity somente após aprovação, para operar esta etapa de forma correta, segura e rastreável.
12. Como operador do Radar, quero separar AffiliateLink, ContentGeneration e Publication, para operar esta etapa de forma correta, segura e rastreável.
13. Como operador do Radar, quero registrar eventos auditáveis com Correlation ID, para operar esta etapa de forma correta, segura e rastreável.
14. Como operador do Radar, quero executar migrations desde banco vazio e entre versões, para operar esta etapa de forma correta, segura e rastreável.

## Implementation Decisions

- Python 3.13+ com versão exata fixada, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, SQLite WAL, uv; TypeScript strict, pnpm e Node LTS fixado.
- Domínio independente de framework, ORM e serviços externos; schema_version nos contratos externos.
- Constraint marketplace + external_id, FK habilitadas, transações e precisão monetária sem float binário.
- Configuração e Knowledge distintos; segredos excluídos de Git, banco comum, logs, fixtures e backup.
- Observabilidade estruturada, radarctl inicial e health model; armazenamento de código separado dos dados.

## Testing Decisions

- Fronteira aprovada: Contratos públicos da Application com SQLite temporário real.
- Testar comportamento externo e resultados persistidos, nunca estrutura interna ou mocks que apenas repetem implementação.
- Prior art: matriz QA e contratos SDD; ainda não há código/testes versionados. Preferir as interfaces aprovadas ao criar as primeiras seams.
- constraints e rollback com SQLite real.
- migrations empty→latest e N→N+1.
- append-only, versionamento e proveniência.
- config inválida bloqueia execução e leakage com secrets falsos.

## Out of Scope

Adapters reais, UI completa, scoring completo e operação comercial.

## Further Notes

### Objective

Entregar o comportamento descrito com evidência de sucesso, falha, recuperação, auditoria, segurança e idempotência quando houver side effect.

### Context / SDD references

SDDs 00, 02, 03, 04, 10, 12 e 13. Vocabulário de CONTEXT e ADRs vigentes; os SDDs e Decision Log continuam autoridade. SPEC-00 organiza a entrega, sem redefinir arquitetura.

### In scope

Histórias e decisões desta spec; rastreabilidade RDR-001..RDR-021. São IDs locais do Issue Map, não números GitHub. Não renumerar nem perder AC ao fundir itens inseparáveis.

### Dependencies

Nenhuma spec funcional; primeira entrega executável.

### Contracts

Usar entradas, saídas, estados e erros dos SDDs referenciados; schema_version e Correlation ID nos contratos aplicáveis. External providers permanecem não confiáveis. Formalizar campos/enums/migrations adicionais em cada issue antes de implementação; nenhuma lacuna autoriza inventar capability externa.

### Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. Não alterar arquitetura silenciosamente. Testes seguros por padrão; live opt-in, sandbox e autorização específica para side effect. Não publicar em destino real nesta spec. Não ignorar teste, validação, idempotência ou compliance para simplificar.

### Acceptance Criteria

- [ ] Evidência verificável para iniciar o monorepo com a stack congelada.
- [ ] Evidência verificável para validar configuração antes de executar workers.
- [ ] Evidência verificável para acessar segredos pelo SecretsProvider sem persistência comum.
- [ ] Evidência verificável para identificar saúde de sistema e dependências.
- [ ] Evidência verificável para preservar Product e MarketplaceProduct como identidades distintas.
- [ ] Evidência verificável para capturar Offer sem confundir produto e condição comercial.
- [ ] Evidência verificável para preservar RawCapture sanitizada e Evidence.
- [ ] Evidência verificável para registrar DiscoveryEvent e Candidate.
- [ ] Evidência verificável para guardar PriceObservation append-only.
- [ ] Evidência verificável para guardar Evaluation imutável e versionada.
- [ ] Evidência verificável para criar Opportunity somente após aprovação.
- [ ] Evidência verificável para separar AffiliateLink, ContentGeneration e Publication.
- [ ] Evidência verificável para registrar eventos auditáveis com Correlation ID.
- [ ] Evidência verificável para executar migrations desde banco vazio e entre versões.
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

