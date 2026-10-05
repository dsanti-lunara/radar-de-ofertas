# SPEC-05: Publicação e recuperação

## Problem Statement

O operador pode duplicar mensagens quando um envio remoto não é confirmado localmente ou quando um backup perde registros de publicações posteriores.

## Solution

Entregar publicação e recuperação como parte da V1 aprovada, com contratos públicos verificáveis, caminhos de falha/recuperação auditáveis e gates das integrações externas preservados.

## User Stories

1. Como operador do Radar, quero renderizar preço, link, disclosure e tracking deterministicamente, para operar esta etapa de forma correta, segura e rastreável.
2. Como operador do Radar, quero usar somente destinos cadastrados por marca e canal, para operar esta etapa de forma correta, segura e rastreável.
3. Como operador do Radar, quero publicar Telegram por Bot API, para operar esta etapa de forma correta, segura e rastreável.
4. Como operador do Radar, quero persistir IDs externos e revisões, para operar esta etapa de forma correta, segura e rastreável.
5. Como operador do Radar, quero aplicar caps, burst, quiet hours e cooldown, para operar esta etapa de forma correta, segura e rastreável.
6. Como operador do Radar, quero revalidar antes de cada envio, para operar esta etapa de forma correta, segura e rastreável.
7. Como operador do Radar, quero editar ou expirar publicações com histórico, para operar esta etapa de forma correta, segura e rastreável.
8. Como operador do Radar, quero distinguir falha confirmada de resultado desconhecido, para operar esta etapa de forma correta, segura e rastreável.
9. Como operador do Radar, quero suspender envio desconhecido sem retry automático, para operar esta etapa de forma correta, segura e rastreável.
10. Como operador do Radar, quero receber HumanAction para revisar evidências, para operar esta etapa de forma correta, segura e rastreável.
11. Como operador do Radar, quero impedir nova tentativa sem evidência suficiente, para operar esta etapa de forma correta, segura e rastreável.
12. Como operador do Radar, quero aceitar expiração enquanto aguarda revisão, para operar esta etapa de forma correta, segura e rastreável.
13. Como operador do Radar, quero criar backup consistente sem secrets/sessions, para operar esta etapa de forma correta, segura e rastreável.
14. Como operador do Radar, quero restaurar explicitamente sem reenviar jobs antigos, para operar esta etapa de forma correta, segura e rastreável.
15. Como operador do Radar, quero manter novos envios bloqueados durante reconciliação pós-backup, para operar esta etapa de forma correta, segura e rastreável.
16. Como operador do Radar, quero retomar diagnóstico e processamento seguro, para operar esta etapa de forma correta, segura e rastreável.
17. Como operador do Radar, quero auditar a resolução e liberação de envios, para operar esta etapa de forma correta, segura e rastreável.

## Implementation Decisions

WhatsApp V1 usa grupos explicitamente cadastrados (`destination_type=GROUP`), pela capability `PUBLISH_WHATSAPP_GROUP`; `Channel.WHATSAPP` continua a plataforma. Channels não são a capability V1 deste fluxo. Nome de grupo e message-id não comprovam identidade persistente de destino.

Cada destino mantém identidade interna, marca, sandbox/produção e vínculo verificado ao grupo. O vínculo registra método/evidência, versão e revisão humana; somente pode habilitar envio após prova de identificação e reverificação segura. ID externo só é persistido se obtido por superfície permitida e validado; nunca inferido de storage/cookies/tokens. Sem essa prova, manter envio bloqueado e HumanAction/CAPABILITY_CONFLICT apenas para WA. Mudança de contexto, vínculo inválido ou grupo homônimo bloqueia antes do clique.

Serializer canônico define blocos e separadores de linha, aplica renderer determinístico e compara hash do conteúdo efetivamente preparado com o aprovado. Não usar `innerText`/`textContent` sem normalização especificada. Preview não autoriza envio. Preflight revalida destino, marca, conteúdo, oferta, compliance, nonce e aprovação da Publication imediatamente antes de um único Send.

`Enviada`/bubble/message marker são evidência de envio observado, não promessa de entrega/leitura. Receipt registra destino interno/vínculo, publication/revision, hash, correlation_id, observed_at e marcador externo quando disponível. Ausência de confirmação suficiente, timeout ou crash na janela de envio gera resultado desconhecido persistido, publicação suspensa e HumanAction, sem reenvio automático. Dedupe não depende de bubble: mensagens temporárias/reload/restore não apagam a proteção persistente (GRILL-002/003).

Todas as rotas Shopee, inclusive link manual, exigem revalidação atual; indisponibilidade/challenge não é superada por cache ou aprovação humana isolada. Tracking ML e Sub IDs seguem SDD-04/09.

- Telegram usa Bot API; publishers separados; idempotency_key por publicação/revision não prova resultado remoto.
- Resultado desconhecido deve persistir, suspender publicação afetada, impedir reenvio automático e gerar HumanAction.
- Evidência suficiente é exigida para concluir ou autorizar nova tentativa; autorização humana isolada não prova falha anterior.
- Restore nunca automático; todos os envios permanecem bloqueados até reconciliar intervalo posterior ao backup. Ausência de registro restaurado não autoriza reenvio.
- Backup SQLite consistente com config/knowledge/manifest/checksums; secrets, sessões, browser profile e diagnostics temporários excluídos.
- Manter lifecycle, revalidation/content staleness e políticas bloqueantes; nomes de novos estados/schemas devem ser documentados na implementação.

## Testing Decisions

- Fronteira aprovada: Comandos públicos de publicação/recovery/restore com SQLite real e Fake Publishers.
- Testar comportamento externo e resultados persistidos, nunca estrutura interna ou mocks que apenas repetem implementação.
- Prior art: matriz QA e contratos SDD; ainda não há código/testes versionados. Preferir as interfaces aprovadas ao criar as primeiras seams.
- crash após aceitação remota antes do commit local, zero reenvio automático.
- revisão sem evidência não libera envio; resolução auditável com evidência.
- restore anterior a publicação bloqueia jobs antigos e novos envios.
- diagnóstico/processamento seguro continuam; desconhecidos geram HumanAction.
- backup consistente, restore, revisions, idempotência e guardrails.

## Out of Scope

Consulta remota não validada, garantia de reconciliação automática universal, destinos reais sem autorização e ativação de AUTO.

## Further Notes

### Objective

Entregar o comportamento descrito com evidência de sucesso, falha, recuperação, auditoria, segurança e idempotência quando houver side effect.

### Context / SDD references

SDDs 04, 08, 09, 10, 12 e 13; GRILL-001..003; ADR 0001. Vocabulário de CONTEXT e ADRs vigentes; os SDDs e Decision Log continuam autoridade. SPEC-00 organiza a entrega, sem redefinir arquitetura.

### In scope

Histórias e decisões desta spec; rastreabilidade RDR-068..RDR-075; RDR-112..RDR-113; RDR-128; integração com RDR-020, RDR-042 e RDR-130. São IDs locais do Issue Map, não números GitHub. Não renumerar nem perder AC ao fundir itens inseparáveis.

### Dependencies

SPEC-01, SPEC-03 e SPEC-04; seleção de SPEC-02. WhatsApp usa SPEC-06.

### Contracts

Usar entradas, saídas, estados e erros dos SDDs referenciados; schema_version e Correlation ID nos contratos aplicáveis. External providers permanecem não confiáveis. Formalizar campos/enums/migrations adicionais em cada issue antes de implementação; nenhuma lacuna autoriza inventar capability externa.

### Implementation constraints

Correctness → Safety → Recoverability → Observability → Performance → Polish. Não alterar arquitetura silenciosamente. Testes seguros por padrão; live opt-in, sandbox e autorização específica para side effect. Não publicar em destino real nesta spec. Não ignorar teste, validação, idempotência ou compliance para simplificar.

### Acceptance Criteria

- [ ] Refinamentos RECON-001..005 aplicáveis demonstrados na fronteira pública; limitations/gates explícitos, sem alias CHANNEL, ID inventado ou fallback de proteção.
- [ ] Fixtures/Fake, SAFE_LIVE, API autenticada e SIDE_EFFECT sandbox têm evidências separadas; não marcar aceites reais por testes offline do recon.

- [ ] Evidência verificável para renderizar preço, link, disclosure e tracking deterministicamente.
- [ ] Evidência verificável para usar somente destinos cadastrados por marca e canal.
- [ ] Evidência verificável para publicar Telegram por Bot API.
- [ ] Evidência verificável para persistir IDs externos e revisões.
- [ ] Evidência verificável para aplicar caps, burst, quiet hours e cooldown.
- [ ] Evidência verificável para revalidar antes de cada envio.
- [ ] Evidência verificável para editar ou expirar publicações com histórico.
- [ ] Evidência verificável para distinguir falha confirmada de resultado desconhecido.
- [ ] Evidência verificável para suspender envio desconhecido sem retry automático.
- [ ] Evidência verificável para receber HumanAction para revisar evidências.
- [ ] Evidência verificável para impedir nova tentativa sem evidência suficiente.
- [ ] Evidência verificável para aceitar expiração enquanto aguarda revisão.
- [ ] Evidência verificável para criar backup consistente sem secrets/sessions.
- [ ] Evidência verificável para restaurar explicitamente sem reenviar jobs antigos.
- [ ] Evidência verificável para manter novos envios bloqueados durante reconciliação pós-backup.
- [ ] Evidência verificável para retomar diagnóstico e processamento seguro.
- [ ] Evidência verificável para auditar a resolução e liberação de envios.
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

