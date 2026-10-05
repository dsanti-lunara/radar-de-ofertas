# Spec: autorização de publicação e recuperação sem duplicação

Status: fronteira de testes confirmada em 2026-10-02; conteúdo incorporado em SPEC-03 e SPEC-05, sob SPEC-00. Não publicar esta proposta como spec adicional duplicada.

## Problem Statement

O operador precisa avaliar ofertas sem publicar involuntariamente e recuperar o Radar sem repetir envios já realizados. Aprovar um Candidate não deve autorizar uma publicação. Um crash após envio remoto ou um restore de backup antigo pode deixar o banco sem confirmação de uma mensagem existente; repetir o job nessa situação pode duplicar uma publicação.

## Solution

Delimitar SHADOW e ASSISTED, exigir aprovação explícita da publicação em ASSISTED e suspender envios cujo resultado seja desconhecido. Após restore, permitir diagnóstico e processamento seguro, mantendo envios bloqueados até reconciliar o intervalo posterior ao backup. Evidência suficiente e auditoria são obrigatórias para resolver a incerteza; a oferta pode expirar enquanto aguarda revisão.

## User Stories

1. Como operador, quero avaliar ofertas em SHADOW, para comparar decisões sem envio comercial.
2. Como operador, quero visualizar previews em SHADOW, para revisar conteúdo com segurança.
3. Como operador, quero registrar aprovação e rejeição de Candidate, para calibrar a seleção de oportunidades.
4. Como operador, quero que aprovar um Candidate não autorize enviar, para separar seleção de distribuição.
5. Como operador, quero aprovar explicitamente uma publicação em ASSISTED, para controlar seu envio.
6. Como operador, quero que revalidação continue obrigatória após aprovação, para evitar publicar fatos desatualizados.
7. Como operador, quero que compliance e políticas continuem bloqueantes, para que minha aprovação não contorne guardrails.
8. Como operador, quero distinguir falha confirmada de resultado desconhecido, para não repetir um envio possivelmente concluído.
9. Como operador, quero que uma publicação incerta seja suspensa, para prevenir duplicação automática.
10. Como operador, quero uma HumanAction para revisar o envio incerto, para saber o que exige minha intervenção.
11. Como operador, quero registrar evidência na resolução, para justificar a conclusão ou uma nova tentativa.
12. Como operador, quero que aprovação sem evidência não libere reenvio incerto, para preservar segurança.
13. Como operador, quero aceitar a expiração de uma oferta durante a revisão, para priorizar não duplicar.
14. Como operador, quero recuperar diagnóstico e processamento seguro após restore, para investigar sem enviar.
15. Como operador, quero bloquear jobs restaurados e novas publicações até reconciliar, para evitar duplicações decorrentes de registros perdidos.
16. Como operador, quero que ausência de registro restaurado não seja prova de ausência de envio, para tratar corretamente backups antigos.
17. Como operador, quero auditar a reconciliação e a liberação de envios, para entender como a operação retomou.
18. Como operador, quero que recriar a VM preserve essas restrições, para que um desastre completo não contorne recuperação segura.

## Implementation Decisions

- Manter a arquitetura aprovada: Workflow Engine central, estados de domínio separados de jobs, persistência SQLite e publishers independentes.
- SHADOW registra avaliações, decisões e previews sem envio comercial. ASSISTED exige aprovação humana explícita da publicação. Aprovação de Candidate permite Opportunity, sem autorizar envio.
- Revalidação, compliance, Publishing Policy e demais guardrails permanecem obrigatórios.
- Persistir a condição de resultado desconhecido e a suspensão da publicação; impedir reenvio automático e criar HumanAction de revisão. Ausência de confirmação não equivale a falha confirmada.
- A resolução deve registrar evidência suficiente e decisão auditável. Autorização humana isolada não prova falha do envio anterior. Nova tentativa exige os guardrails vigentes.
- Restore mantém todos os envios bloqueados, incluindo jobs recuperados e novas publicações, até reconciliar o intervalo posterior ao backup. Diagnóstico e processamento seguro podem retomar.
- Resultados ainda desconhecidos seguem a suspensão e revisão humana; ausência de registro no banco restaurado não autoriza reenviar.
- O contrato comportamental é obrigatório; nomes novos de estados, schemas, campos e migrations devem ser explicitados na implementação, preservando compatibilidade. Não há decisão aprovada sobre nomes adicionais de enums ou endpoints.

## Testing Decisions

- Fronteira proposta: comandos públicos da camada Application responsáveis por aprovação, publicação, recovery e restore, exercitando o Workflow Engine e observando efeitos externos e estado persistido.
- Usar SQLite temporário real e Fake Publishers com registro de envios e injeção de falha após aceitação remota e antes da confirmação local; relógio controlável para expiração.
- Verificar comportamento externo: quantidade de envios, bloqueios, HumanActions, evidência e auditoria persistidas. Não testar chamadas internas, organização de classes ou texto exato de copy.
- Cobrir SHADOW, ASSISTED, falha confirmada, resultado desconhecido, revisão sem evidência, resolução sustentada por evidência, crash/restart e restore anterior a publicação.
- Cobrir bloqueio de jobs restaurados e novos envios, continuidade de processamento seguro, expiração durante revisão e guardrails após autorização.
- O repo não possui testes implementados. O precedente é a matriz de QA: SQLite real, failure injection, idempotência, recuperação pós-crash, segurança e Fake Providers. Os testes devem integrar essas camadas quando disponíveis.
- Nenhum teste live, envio real ou sessão de marketplace é necessário ou autorizado por esta spec.

## Out of Scope

- Ativar AUTO, redesenhar a arquitetura ou implementar adapters reais de navegador.
- Automatizar login, extrair sessões ou publicar em destinos reais.
- Definir mecanismo de consulta remota não validado ou prometer recuperação automática de qualquer envio desconhecido.
- Criar novas funcionalidades de analytics, scoring ou atribuição.

## Further Notes

### Objective / Context / SDD references

Objetivo: tornar verificáveis os limites de autorização e recuperação aceitos no pequeno grill de 2026-10-02.

Referências: CONTEXT.md; ADR 0001; GRILL-001, GRILL-002 e GRILL-003 no Decision Log; SDDs 02, 03, 04, 08, 09, 10, 11, 12 e 13; Recovery Runbook. Os SDDs e Decision Log continuam sendo autoridade.

### In scope

Contratos comportamentais de autorização, suspensão de resultado desconhecido, reconciliação pós-restore, HumanAction, auditoria e testes seguros correspondentes.

### Dependencies

Foundation, Domain/Persistence, Workflow, Fake Publishers e mecanismo de backup/restore. Integrar com as issues RDR existentes de idempotência e crash reconciliation; esta spec não substitui nem renumera o Issue Map.

### Contracts

Inputs: modo operacional, Candidate/publicação, aprovação humana explícita quando aplicável, resultado do publisher, contexto de recovery/restore e evidência de reconciliação.

Outputs: autorização ou bloqueio de envio, resultado desconhecido persistido, publicação suspensa, HumanAction e trilha de auditoria.

States/errors: distinguir falha confirmada de resultado desconhecido; bloqueio pós-restore não pode desaparecer com simples retomada dos workers. Identificadores concretos devem ser documentados antes de implementar os contratos correspondentes.

### Implementation constraints

Side effects falham fechados; IA não decide compliance nem publica; idempotência local não é prova de envio remoto; segredos não entram em banco comum, logs ou fixtures. Preservar isolamento de falhas e arquitetura aprovada.

### Acceptance Criteria

- [ ] SHADOW não envia comercialmente após aprovação de Candidate ou publicação.
- [ ] ASSISTED não envia sem aprovação explícita da publicação; aprovar Candidate é insuficiente.
- [ ] Revalidação e guardrails bloqueantes continuam efetivos após aprovação.
- [ ] Crash após aceitação remota e antes de confirmação local não causa reenvio automático.
- [ ] Resultado desconhecido persiste como condição suspensa e gera HumanAction.
- [ ] Revisão sem evidência suficiente não libera nova tentativa.
- [ ] Resolução com evidência registra decisão auditável; nova tentativa permanece sujeita à elegibilidade atual.
- [ ] Expiração durante revisão não é contornada para enviar.
- [ ] Restore anterior a envio bloqueia jobs recuperados e novos envios até reconciliar.
- [ ] Diagnóstico e processamento seguro continuam durante bloqueio pós-restore.
- [ ] Ausência de registro restaurado não autoriza reenvio; incerteza segue revisão humana.
- [ ] Recriação da VM segue os mesmos limites de restore.

### Tests required

Unit para regras determinísticas, contract para comandos/resultados públicos, integration com SQLite e Fake Publishers, segurança funcional e recovery com failure injection. FIXTURE de browser, SAFE_LIVE e sandbox side effect não se aplicam a esta spec.

### Observability

Expor autorização negada, publicação suspensa por resultado desconhecido, bloqueio pós-restore e andamento/decisão de reconciliação. HumanAction deve explicar impacto e evidência necessária; eventos e decisões relevantes são auditáveis sem dados sensíveis.

### Documentation to update

Glossário, Decision Log, ADR de resultado desconhecido, SDDs de publicação e persistência, Recovery Runbook, matriz de QA e contratos concretos alterados durante implementação.

### Completion report

Reportar arquivos, testes e resultados, testes não executados e motivos, limitações, mudanças de contratos, migrations/config changes e riscos. Não promover capabilities para AUTO.
