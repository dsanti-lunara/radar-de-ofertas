# SPEC-07: Operação e homologação

## Problem Statement

Mesmo um pipeline funcional não é operável sem diagnóstico acionável, controles humanos, backup visível e recuperação validada no ambiente real.

## Solution

Entregar operação e homologação como parte da V1 aprovada, com contratos públicos verificáveis, caminhos de falha/recuperação auditáveis e gates das integrações externas preservados.

## User Stories

1. Como operador do Radar, quero visualizar saúde sem consultar SQL, para operar esta etapa de forma correta, segura e rastreável.
2. Como operador do Radar, quero decidir oportunidades com score breakdown e Evidence, para operar esta etapa de forma correta, segura e rastreável.
3. Como operador do Radar, quero revisar Candidate e publicação separadamente, para operar esta etapa de forma correta, segura e rastreável.
4. Como operador do Radar, quero acompanhar publicações e revisões, para operar esta etapa de forma correta, segura e rastreável.
5. Como operador do Radar, quero resolver HumanActions, para operar esta etapa de forma correta, segura e rastreável.
6. Como operador do Radar, quero inspecionar jobs e Dead Jobs, para operar esta etapa de forma correta, segura e rastreável.
7. Como operador do Radar, quero alterar configurações operacionais frequentes, para operar esta etapa de forma correta, segura e rastreável.
8. Como operador do Radar, quero exigir confirmação em mudanças perigosas, para operar esta etapa de forma correta, segura e rastreável.
9. Como operador do Radar, quero visualizar elegibilidade AUTO sem promover automaticamente, para operar esta etapa de forma correta, segura e rastreável.
10. Como operador do Radar, quero executar radarctl doctor read-only, para operar esta etapa de forma correta, segura e rastreável.
11. Como operador do Radar, quero proteger operação contra disco crítico, para operar esta etapa de forma correta, segura e rastreável.
12. Como operador do Radar, quero instalar VM e serviços de forma reproduzível, para operar esta etapa de forma correta, segura e rastreável.
13. Como operador do Radar, quero iniciar Chrome pela sessão gráfica dedicada, para operar esta etapa de forma correta, segura e rastreável.
14. Como operador do Radar, quero validar reboot, browser restart e network outage, para operar esta etapa de forma correta, segura e rastreável.
15. Como operador do Radar, quero testar backup no host e restore, para operar esta etapa de forma correta, segura e rastreável.
16. Como operador do Radar, quero executar soak Shadow e audit de readiness, para operar esta etapa de forma correta, segura e rastreável.
17. Como operador do Radar, quero mostrar métricas comerciais somente com atribuição real, para operar esta etapa de forma correta, segura e rastreável.

## Implementation Decisions

Gates G1..G7 de PRODUCTION_READINESS permanecem NO-GO. Homologar GROUP/vínculo, receipts/dedupe após mensagens temporárias, crash/reconnect/MV3/reboot/restore, segurança e soak no Chrome dedicado/VM. Captura API/pública/manual e link API/manual têm aceites separados; nenhum build ou teste de artefato aprova produção. UI só habilita capacidades reais e vínculos verificados.

- Control Center React/TypeScript/Vite, REST e polling; UI compilada servida pelo radar-api, sem template genérico.
- UI não bloqueia Core e não cria capacidades que API não possui; distinguir Candidate approval e publication approval.
- VM Linux LTS desktop leve, systemd para Core/API; runtime dedicado sem root, portas públicas ou cloud.
- Retention/disk protection, upgrade com drain/backup/migrate/integrity e doctor read-only.
- Security/QA auditável por Requirement→Test→Acceptance→Evidence; produção inicial SHADOW/ASSISTED e promoção AUTO só humana.
- Gates reais não substituídos por build ou Fake E2E; compliance bloqueada impede execução comercial.

## Testing Decisions

- Fronteira aprovada: API operacional pública e acceptance do Radar Execution Node; UI E2E nos fluxos críticos.
- Testar comportamento externo e resultados persistidos, nunca estrutura interna ou mocks que apenas repetem implementação.
- Prior art: matriz QA e contratos SDD; ainda não há código/testes versionados. Preferir as interfaces aprovadas ao criar as primeiras seams.
- API/read models e ações humanas auditadas.
- UI fluxos críticos, guardrails e confirmação de ações perigosas.
- secret leakage, policy block e destination mismatch.
- reboot/restart/outage/abrupt termination com evidência real.
- soak 24h Shadow e estendido conforme QA, recursos/queues/duplicates.
- readiness com ausência de P0 e critérios de produção satisfeitos.

## Out of Scope

Cloud, multiusuário, analytics V1.1, dashboard excessivo e promoção automática para AUTO.

## Further Notes

### Objective

Entregar o comportamento descrito com evidência de sucesso, falha, recuperação, auditoria, segurança e idempotência quando houver side effect.

### Context / SDD references

SDDs 02, 10, 11, 12, 13 e 14; Installation; Recovery Runbook. Vocabulário de CONTEXT e ADRs vigentes; os SDDs e Decision Log continuam autoridade. SPEC-00 organiza a entrega, sem redefinir arquitetura.

### In scope

Histórias e decisões desta spec; rastreabilidade RDR-056..RDR-067; RDR-114..RDR-121; RDR-126..RDR-127; RDR-129..RDR-134; integração com RDR-130. São IDs locais do Issue Map, não números GitHub. Não renumerar nem perder AC ao fundir itens inseparáveis.

### Dependencies

SPEC-01 para início da UI; demais specs conforme controles e acceptance. Homologação final depende dos fluxos validados.

### Contracts

Usar entradas, saídas, estados e erros dos SDDs referenciados; schema_version e Correlation ID nos contratos aplicáveis. External providers permanecem não confiáveis. Formalizar campos/enums/migrations adicionais em cada issue antes de implementação; nenhuma lacuna autoriza inventar capability externa.

### Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. Não alterar arquitetura silenciosamente. Testes seguros por padrão; live opt-in, sandbox e autorização específica para side effect. Não publicar em destino real nesta spec. Não ignorar teste, validação, idempotência ou compliance para simplificar.

### Acceptance Criteria

- [ ] Refinamentos RECON-001..005 aplicáveis demonstrados na fronteira pública; limitations/gates explícitos, sem alias CHANNEL, ID inventado ou fallback de proteção.
- [ ] Fixtures/Fake, SAFE_LIVE, API autenticada e SIDE_EFFECT sandbox têm evidências separadas; não marcar aceites reais por testes offline do recon.

- [ ] Evidência verificável para visualizar saúde sem consultar SQL.
- [ ] Evidência verificável para decidir oportunidades com score breakdown e Evidence.
- [ ] Evidência verificável para revisar Candidate e publicação separadamente.
- [ ] Evidência verificável para acompanhar publicações e revisões.
- [ ] Evidência verificável para resolver HumanActions.
- [ ] Evidência verificável para inspecionar jobs e Dead Jobs.
- [ ] Evidência verificável para alterar configurações operacionais frequentes.
- [ ] Evidência verificável para exigir confirmação em mudanças perigosas.
- [ ] Evidência verificável para visualizar elegibilidade AUTO sem promover automaticamente.
- [ ] Evidência verificável para executar radarctl doctor read-only.
- [ ] Evidência verificável para proteger operação contra disco crítico.
- [ ] Evidência verificável para instalar VM e serviços de forma reproduzível.
- [ ] Evidência verificável para iniciar Chrome pela sessão gráfica dedicada.
- [ ] Evidência verificável para validar reboot, browser restart e network outage.
- [ ] Evidência verificável para testar backup no host e restore.
- [ ] Evidência verificável para executar soak Shadow e audit de readiness.
- [ ] Evidência verificável para mostrar métricas comerciais somente com atribuição real.
- [ ] Falhas e recuperação cobertas na fronteira aprovada, com guardrails preservados.
- [ ] Docs e contratos atualizados; limitações e gates pendentes explícitos.

### Tests required

Cobrir os negativos e recuperação aplicáveis da revisão RECON-001..005 e QA Matrix: identidade/charset/precisão/contexto, resultado stale/partial/unknown e dedupe persistente; estados positivos, falha e retomada auditáveis. Runtime/live permanecem opt-in nos gates autorizados.

Unit e contract relevantes; integration com dependências locais reais quando aplicável; segurança funcional e E2E do fluxo. Live/fixtures/sandbox somente nos gates descritos, nunca por padrão.

### Observability

Estado/saúde e erros acionáveis do fluxo, Correlation ID, eventos auditáveis e HumanActions quando necessária intervenção. Sem secrets/PII desnecessária em logs ou evidências.

### Documentation to update

SDDs referenciados, contratos afetados, QA traceability, Error Catalog/runbooks quando aplicáveis e Issue Map com links de execução. Registrar novas decisões difíceis de reverter em ADR quando justificadas.

### Completion report

Arquivos, testes/resultados, testes não executados/motivos, limitações, mudanças de contrato, migrations/config changes e riscos restantes. Atualizar a issue com evidência e critérios verificados; não ativar AUTO.

